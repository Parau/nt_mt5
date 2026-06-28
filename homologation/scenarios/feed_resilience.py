"""
TC-HOM-D06: WS feed resilience — gateway restart + optional Service stop/start dedup.

Phase 1: collect QuoteTick ts_event keys via feed.
Phase 2: restart Python InboundFeedGateway (automated).
Phase 3 (optional): prompt for NT5TickFeedService stop/start when
``HOMOLOG_D06_REQUIRE_SERVICE_RESTART=1``.
Phase 4: collect more ticks; fail on duplicate ts_event or missing resume.
"""
from __future__ import annotations

import asyncio
import os
import time

from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.data.messages import SubscribeQuoteTicks
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.identifiers import InstrumentId, Symbol, TraderId, Venue

from nautilus_mt5 import TICKMILL_DEMO_PROFILE
from nautilus_mt5.client.types import MT5TerminalAccessMode
from nautilus_mt5.config import (
    ExternalRPyCTerminalConfig,
    FeedGatewayConfig,
    MetaTrader5DataClientConfig,
    MetaTrader5InstrumentProviderConfig,
)
from nautilus_mt5.data_types import MT5Symbol
from nautilus_mt5.factories import MT5LiveDataClientFactory

from homologation.config import HomologationConfig
from homologation.report import HomologationReport, ScenarioStatus
from homologation.support.clients import reset_mt5_client_cache

_VENUE = Venue("METATRADER_5")


def _phase_secs() -> float:
    return float(os.environ.get("HOMOLOG_D06_PHASE_SECS", "20"))


def _require_service_restart() -> bool:
    return os.environ.get("HOMOLOG_D06_REQUIRE_SERVICE_RESTART", "").strip() == "1"


def _data_client(cfg: HomologationConfig):
    rpyc_cfg = ExternalRPyCTerminalConfig(host=cfg.host, port=cfg.port, keep_alive=True)
    provider = MetaTrader5InstrumentProviderConfig(
        load_symbols=frozenset({MT5Symbol(symbol=cfg.symbol, broker=cfg.broker)}),
    )
    feed = FeedGatewayConfig(
        enabled=True,
        host=cfg.feed_host,
        port=cfg.feed_port,
        path=cfg.feed_path,
        hello_timeout_secs=cfg.feed_hello_timeout_secs,
    )
    config = MetaTrader5DataClientConfig(
        client_id=3,
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=rpyc_cfg,
        instrument_provider=provider,
        venue_profile=TICKMILL_DEMO_PROFILE,
        feed=feed,
    )
    loop = asyncio.get_running_loop()
    clock = LiveClock()
    msgbus = MessageBus(TraderId("HOMOLOG-D06"), clock)
    cache = Cache()
    client = MT5LiveDataClientFactory.create(
        loop=loop,
        name="MT5",
        config=config,
        msgbus=msgbus,
        cache=cache,
        clock=clock,
    )
    return client, cache, clock


async def _restart_feed_gateway(data_client) -> None:
    await data_client._restart_feed_gateway()
    await asyncio.sleep(1.0)


async def _wait_for_new_ticks(
    tick_count: list[int],
    baseline: int,
    timeout_secs: float,
) -> bool:
    deadline = time.monotonic() + timeout_secs
    while time.monotonic() < deadline:
        if tick_count[0] > baseline:
            return True
        await asyncio.sleep(0.5)
    return False


async def run_feed_service_restart_dedup(
    cfg: HomologationConfig,
    report: HomologationReport,
) -> None:
    """TC-HOM-D06: feed gateway restart + optional Service stop/start dedup."""
    case_id = "TC-HOM-D06"
    name = "WS feed stop/start + cursor dedup"

    if not cfg.feed_enabled:
        report.add(
            case_id,
            name,
            ScenarioStatus.SKIP,
            "Set MT5_FEED_ENABLED=1 and start NT5TickFeedService",
        )
        return

    phase_secs = _phase_secs()
    require_service = _require_service_restart()
    reset_mt5_client_cache()

    seen_ts: set[int] = set()
    baseline_ts: set[int] = set()
    duplicates: list[int] = []
    tick_count = [0]
    phase = ["baseline"]
    data_client = None

    try:
        data_client, cache, clock = _data_client(cfg)
        inst_id = InstrumentId(Symbol(cfg.symbol), _VENUE)

        orig_handle_data = data_client._handle_data

        def _spy_handle_data(data) -> None:
            if isinstance(data, QuoteTick):
                tick_count[0] += 1
                if phase[0] == "post" and data.ts_event in baseline_ts:
                    duplicates.append(data.ts_event)
                seen_ts.add(data.ts_event)
            orig_handle_data(data)

        data_client._handle_data = _spy_handle_data

        await data_client._connect()
        if cache.instrument(inst_id) is None:
            report.add(case_id, name, ScenarioStatus.FAIL, "Instrument not in cache after connect")
            return

        sub_cmd = SubscribeQuoteTicks(
            instrument_id=inst_id,
            client_id=data_client.id,
            venue=_VENUE,
            command_id=UUID4(),
            ts_init=clock.timestamp_ns(),
        )
        await data_client._subscribe_quote_ticks(sub_cmd)

        await asyncio.sleep(phase_secs)
        baseline_ticks = tick_count[0]
        if baseline_ticks < 3:
            report.add(
                case_id,
                name,
                ScenarioStatus.FAIL,
                f"Baseline too quiet: {baseline_ticks} ticks in {phase_secs:.0f}s",
                baseline_ticks=baseline_ticks,
            )
            return

        baseline_ts.update(seen_ts)
        phase[0] = "post"

        await _restart_feed_gateway(data_client)
        if not await _wait_for_new_ticks(tick_count, baseline_ticks, timeout_secs=45.0):
            report.add(
                case_id,
                name,
                ScenarioStatus.FAIL,
                "No ticks after Python gateway restart within 45s",
                baseline_ticks=baseline_ticks,
            )
            return

        after_gateway = tick_count[0]

        if require_service:
            print(
                "\n>>> TC-HOM-D06: STOP then START NT5TickFeedService in MT5 (90s max) <<<\n",
                flush=True,
            )
            stall_deadline = time.monotonic() + 90.0
            stall_seen = False
            last_tick_at = time.monotonic()
            while time.monotonic() < stall_deadline:
                if tick_count[0] > after_gateway:
                    last_tick_at = time.monotonic()
                elif time.monotonic() - last_tick_at >= 3.0:
                    stall_seen = True
                if stall_seen and tick_count[0] > after_gateway:
                    break
                await asyncio.sleep(0.5)

        post_resume = tick_count[0]
        await asyncio.sleep(phase_secs)
        post_phase_ticks = tick_count[0] - post_resume

        if duplicates:
            report.add(
                case_id,
                name,
                ScenarioStatus.FAIL,
                f"Duplicate ts_event after restart: {len(duplicates)}",
                duplicates=len(duplicates),
                total_ticks=tick_count[0],
            )
            return

        if post_phase_ticks < 3:
            report.add(
                case_id,
                name,
                ScenarioStatus.FAIL,
                f"Post-restart stream too quiet: {post_phase_ticks} ticks in {phase_secs:.0f}s",
                post_phase_ticks=post_phase_ticks,
            )
            return

        detail = (
            f"baseline={baseline_ticks} after_gateway={after_gateway - baseline_ticks} "
            f"post={post_phase_ticks} unique_ts={len(seen_ts)} dup=0"
        )
        if require_service:
            detail += " service_restart=manual"
        report.add(
            case_id,
            name,
            ScenarioStatus.PASS,
            detail,
            baseline_ticks=baseline_ticks,
            post_phase_ticks=post_phase_ticks,
            unique_ts=len(seen_ts),
            gateway_restart=True,
            service_restart=require_service,
        )
    except Exception as exc:
        report.add(case_id, name, ScenarioStatus.FAIL, str(exc))
    finally:
        if data_client is not None:
            try:
                await data_client._disconnect()
            except Exception:
                pass
        reset_mt5_client_cache()
