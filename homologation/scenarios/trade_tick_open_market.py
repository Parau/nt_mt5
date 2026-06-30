"""
TC-HOM-D30 / TC-HOM-D31: live and historical TradeTicks (XP/B3 open market).

D30 — SubscribeTradeTicks via TradingNode (RPyC AllLast path).
D31 — RequestTradeTicks E2E via data client (copy_ticks_from → TradeTick).
"""
from __future__ import annotations

import asyncio
import os
import threading
import time
from collections.abc import Callable
from datetime import timedelta

import pandas as pd
from nautilus_trader.config import StrategyConfig
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.data.messages import RequestTradeTicks
from nautilus_trader.model.data import TradeTick
from nautilus_trader.trading.strategy import Strategy

from homologation.config import HomologationConfig, probe_symbol_tick
from homologation.node_factory import build_trading_node, instrument_id
from homologation.report import HomologationReport, ScenarioStatus
from homologation.scenarios.closed_market_suite import _make_data_client, _instrument_id
from homologation.scenarios.node_runner import NodeStopGate, run_node_until
from homologation.support.clients import reset_mt5_client_cache
from nautilus_trader.model.identifiers import Venue

_VENUE = Venue("METATRADER_5")


def _trade_symbols(cfg: HomologationConfig) -> tuple[str, ...]:
    raw = os.environ.get("HOMOLOG_TRADE_SYMBOLS", "").strip()
    if raw:
        return tuple(s.strip() for s in raw.split(",") if s.strip())
    # Nominal tradable contracts only — continuous WIN$/WDO$ are data-only (no bid/ask).
    for sym in ("WINQ26", "WDON26"):
        if sym in cfg.multi_symbols:
            return (sym,)
    return (cfg.symbol,)


class _TradeStreamConfig(StrategyConfig, frozen=True):
    instrument_id: object
    duration_secs: float
    min_ticks: int


class _TradeStreamStrategy(Strategy):
    def __init__(
        self,
        config: _TradeStreamConfig,
        done: threading.Event,
        outcome: dict,
        stop_node: Callable[[], None],
    ) -> None:
        super().__init__(config)
        self._done = done
        self._outcome = outcome
        self._stop_node = stop_node
        self.tick_count = 0
        self._timer: threading.Timer | None = None

    def on_start(self) -> None:
        if self.cache.instrument(self.config.instrument_id) is None:
            self._fail("Instrument not in cache")
            return
        self.subscribe_trade_ticks(instrument_id=self.config.instrument_id)
        self._timer = threading.Timer(self.config.duration_secs, self._finish)
        self._timer.daemon = True
        self._timer.start()

    def on_trade_tick(self, tick: TradeTick) -> None:
        self.tick_count += 1
        if self.tick_count == 1 or self.tick_count % 5 == 0:
            self.log.info(f"TradeTick #{self.tick_count}: price={tick.price} size={tick.size}")

    def on_stop(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
        self._stop_node()

    def _finish(self) -> None:
        if self.tick_count >= self.config.min_ticks:
            self._outcome["ok"] = True
            self._outcome["detail"] = f"Received {self.tick_count} trade tick(s)"
        else:
            self._outcome["ok"] = False
            self._outcome["detail"] = (
                f"Only {self.tick_count} trade tick(s) in {self.config.duration_secs:.0f}s "
                f"(min={self.config.min_ticks})"
            )
        self._done.set()
        self.stop()

    def _fail(self, detail: str) -> None:
        self._outcome["ok"] = False
        self._outcome["detail"] = detail
        self._done.set()
        self.stop()


async def run_trade_tick_stream(cfg: HomologationConfig, report: HomologationReport) -> None:
    """TC-HOM-D30: live SubscribeTradeTicks during open market."""
    case_id = "TC-HOM-D30"
    name = "Live TradeTick stream (SubscribeTradeTicks)"

    if cfg.venue_profile.name != "xp-b3":
        report.add(case_id, name, ScenarioStatus.SKIP, "XP/B3 profile required for trade ticks")
        return

    symbols = _trade_symbols(cfg)
    duration = float(os.environ.get("HOMOLOG_TRADE_STREAM_SECS", str(cfg.stream_duration_secs)))
    min_ticks = int(os.environ.get("HOMOLOG_TRADE_MIN_TICKS", "1"))
    passed_any = False
    skipped = 0

    for sym in symbols:
        tick = probe_symbol_tick(cfg.host, cfg.port, sym)
        if tick is None:
            report.add(
                f"{case_id}-{sym}",
                f"{name} ({sym})",
                ScenarioStatus.SKIP,
                f"{sym}: no bid/ask tick (continuous/data-only symbol?)",
                symbol=sym,
            )
            skipped += 1
            continue

        done = threading.Event()
        outcome: dict = {"ok": False, "detail": ""}
        stop_gate_holder: list[NodeStopGate | None] = [None]
        strategy_holder: list[_TradeStreamStrategy | None] = [None]

        def _build():
            node = build_trading_node(cfg, trader_id="HOMOLOG-D30", symbols=[sym])
            inst = instrument_id(sym)
            strat = _TradeStreamStrategy(
                config=_TradeStreamConfig(
                    strategy_id=f"HOMOLOG-D30-{sym}",
                    instrument_id=inst,
                    duration_secs=duration,
                    min_ticks=min_ticks,
                ),
                done=done,
                outcome=outcome,
                stop_node=lambda: (
                    stop_gate_holder[0].request_stop() if stop_gate_holder[0] else None
                ),
            )
            strategy_holder[0] = strat
            node.trader.add_strategy(strat)
            return node

        reset_mt5_client_cache()
        try:
            await run_node_until(_build, done, duration + 90.0, stop_gate_holder)
        except TimeoutError:
            ticks = strategy_holder[0].tick_count if strategy_holder[0] else 0
            report.add(
                f"{case_id}-{sym}",
                f"{name} ({sym})",
                ScenarioStatus.FAIL,
                f"Timeout after {duration + 90:.0f}s ticks={ticks}",
                symbol=sym,
            )
            return
        except Exception as exc:
            report.add(f"{case_id}-{sym}", f"{name} ({sym})", ScenarioStatus.FAIL, str(exc))
            return

        sub_id = f"{case_id}-{sym}"
        if outcome.get("ok"):
            passed_any = True
            report.add(
                sub_id,
                f"{name} ({sym})",
                ScenarioStatus.PASS,
                outcome.get("detail", "OK"),
                symbol=sym,
            )
        else:
            report.add(
                sub_id,
                f"{name} ({sym})",
                ScenarioStatus.FAIL,
                outcome.get("detail", "no trade ticks"),
                symbol=sym,
            )
            return

    if passed_any:
        report.add(case_id, name, ScenarioStatus.PASS, f"Live TradeTicks OK (symbols={','.join(symbols)})")
    elif skipped == len(symbols):
        report.add(case_id, name, ScenarioStatus.SKIP, "No symbols with live bid/ask for stream probe")
    else:
        report.add(case_id, name, ScenarioStatus.FAIL, "No symbol produced live trade ticks")


async def run_request_trade_ticks_open(cfg: HomologationConfig, report: HomologationReport) -> None:
    """TC-HOM-D31: RequestTradeTicks during open market (historical window)."""
    case_id = "TC-HOM-D31"
    name = "Historical TradeTicks (RequestTradeTicks)"

    if cfg.venue_profile.name != "xp-b3":
        report.add(case_id, name, ScenarioStatus.SKIP, "XP/B3 profile required")
        return

    lookback_days = int(os.environ.get("HOMOLOG_TRADE_LOOKBACK_DAYS", "7"))
    limit = int(os.environ.get("HOMOLOG_TRADE_REQUEST_LIMIT", "50"))

    for sym in _trade_symbols(cfg):
        sym_cfg = HomologationConfig(
            host=cfg.host,
            port=cfg.port,
            account_number=cfg.account_number,
            broker=cfg.broker,
            symbol=sym,
            venue_profile_name=cfg.venue_profile_name,
            enable_execution=cfg.enable_execution,
            min_quote_ticks=cfg.min_quote_ticks,
            scenario_timeout_secs=cfg.scenario_timeout_secs,
            stream_duration_secs=cfg.stream_duration_secs,
            stream_max_gap_secs=cfg.stream_max_gap_secs,
            stream_min_ticks=cfg.stream_min_ticks,
            skip_stream=cfg.skip_stream,
            feed_enabled=cfg.feed_enabled,
            feed_host=cfg.feed_host,
            feed_port=cfg.feed_port,
            feed_path=cfg.feed_path,
            feed_hello_timeout_secs=cfg.feed_hello_timeout_secs,
        )
        delivered: list = []
        data_client = None

        def _capture(instrument_id, ticks, correlation_id):
            delivered.extend(ticks)

        try:
            reset_mt5_client_cache()
            data_client, _, cache, clock = await _make_data_client(sym_cfg)
            await data_client._connect()
            iid = _instrument_id(sym)
            if cache.instrument(iid) is None:
                report.add(case_id, name, ScenarioStatus.FAIL, f"{sym}: not in cache")
                return
            data_client._handle_trade_ticks = _capture
            req = RequestTradeTicks(
                instrument_id=iid,
                start=pd.Timestamp.utcnow() - timedelta(days=lookback_days),
                end=None,
                limit=limit,
                client_id=data_client.id,
                venue=_VENUE,
                callback=None,
                request_id=UUID4(),
                ts_init=clock.timestamp_ns(),
                params=None,
            )
            await data_client._request_trade_ticks(req)
            if not delivered:
                report.add(case_id, name, ScenarioStatus.FAIL, f"{sym}: no TradeTicks")
                return
            last_px = float(delivered[-1].price)
            if last_px <= 0:
                report.add(case_id, name, ScenarioStatus.FAIL, f"{sym}: last price={last_px}")
                return
        except Exception as exc:
            report.add(case_id, name, ScenarioStatus.FAIL, f"{sym}: {exc}")
            return
        finally:
            if data_client is not None:
                await data_client._disconnect()
            reset_mt5_client_cache()
            await asyncio.sleep(0.5)

    report.add(
        case_id,
        name,
        ScenarioStatus.PASS,
        f"TradeTicks OK for {','.join(_trade_symbols(cfg))}",
    )
