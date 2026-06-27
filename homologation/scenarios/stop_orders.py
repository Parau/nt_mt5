"""TC-HOM-E02: Stop and stop-limit pending orders via exec client."""
from __future__ import annotations

import asyncio
import logging
from unittest.mock import MagicMock

import rpyc
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.execution.messages import SubmitOrder
from nautilus_trader.model.enums import OrderSide, TimeInForce, TriggerType
from nautilus_trader.model.identifiers import (
    ClientOrderId,
    InstrumentId,
    StrategyId,
    Symbol,
    TraderId,
    Venue,
)
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.model.orders import StopMarketOrder

from nautilus_mt5 import TICKMILL_DEMO_PROFILE
from nautilus_mt5.client.types import MT5TerminalAccessMode
from nautilus_mt5.config import (
    ExternalRPyCTerminalConfig,
    MetaTrader5DataClientConfig,
    MetaTrader5ExecClientConfig,
    MetaTrader5InstrumentProviderConfig,
)
from nautilus_mt5.data_types import MT5Symbol
from nautilus_mt5.factories import MT5LiveDataClientFactory, MT5LiveExecClientFactory

from homologation.config import HomologationConfig
from homologation.report import HomologationReport, ScenarioStatus
from homologation.support.clients import reset_mt5_client_cache

logger = logging.getLogger(__name__)

_VENUE = Venue("METATRADER_5")


def _get_prices(host: str, port: int, symbol: str) -> tuple[float, float]:
    conn = rpyc.connect(host, port)
    try:
        tick = conn.root.symbol_info_tick(symbol)
        if tick is None:
            raise RuntimeError(f"No tick for {symbol}")
        if isinstance(tick, dict):
            return float(tick["bid"]), float(tick["ask"])
        return float(tick.bid), float(tick.ask)
    finally:
        conn.close()


async def _cancel_pending(exec_client, venue_order_id: str) -> None:
    mt5 = exec_client._client._mt5_client["mt5"]
    req = {"action": 8, "order": int(venue_order_id)}
    result = await asyncio.to_thread(mt5.order_send, req)
    logger.info("Cancel order %s: %s", venue_order_id, result)


async def _submit_stop_order(exec_client, cmd: SubmitOrder) -> tuple[str | None, str | None]:
    """
    Submit a stop order and return ``(venue_order_id, error)``.

    Standalone exec clients have no ExecEngine endpoint, so events are captured
    directly from the client generators (same pattern as the live acceptance test).
    """
    accepted_events: list[dict] = []
    rejected_events: list[dict] = []

    orig_accepted = exec_client.generate_order_accepted
    orig_rejected = exec_client.generate_order_rejected

    exec_client.generate_order_accepted = MagicMock(
        side_effect=lambda *args, **kwargs: accepted_events.append(kwargs),
    )
    exec_client.generate_order_rejected = MagicMock(
        side_effect=lambda *args, **kwargs: rejected_events.append(kwargs),
    )

    try:
        await exec_client._submit_order(cmd)
    finally:
        exec_client.generate_order_accepted = orig_accepted
        exec_client.generate_order_rejected = orig_rejected

    if rejected_events:
        reason = rejected_events[0].get("reason", "order rejected")
        return None, str(reason)

    if not accepted_events:
        return None, "no OrderAccepted event"

    venue_order_id = accepted_events[0].get("venue_order_id")
    if venue_order_id is None:
        return None, "venue_order_id missing from OrderAccepted"

    return str(getattr(venue_order_id, "value", venue_order_id)), None


async def run_stop_orders(cfg: HomologationConfig, report: HomologationReport) -> None:
    case_id = "TC-HOM-E02"
    name = "Stop / stop-limit pending orders"

    if not cfg.enable_execution:
        report.add(
            case_id,
            name,
            ScenarioStatus.SKIP,
            "Set MT5_ENABLE_LIVE_EXECUTION=1 to run execution scenarios",
        )
        return

    reset_mt5_client_cache()
    inst_id = InstrumentId(Symbol(cfg.symbol), _VENUE)
    placed: list[str] = []
    sub_results: list[tuple[str, bool, str]] = []

    rpyc_cfg = ExternalRPyCTerminalConfig(host=cfg.host, port=cfg.port, keep_alive=True)
    provider = MetaTrader5InstrumentProviderConfig(
        load_symbols=frozenset({MT5Symbol(symbol=cfg.symbol, broker=cfg.broker)}),
    )

    data_config = MetaTrader5DataClientConfig(
        client_id=2,
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=rpyc_cfg,
        instrument_provider=provider,
        venue_profile=TICKMILL_DEMO_PROFILE,
    )
    exec_config = MetaTrader5ExecClientConfig(
        client_id=2,
        account_id=cfg.account_number,
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=rpyc_cfg,
        instrument_provider=provider,
        cancel_on_stop=False,
        close_on_stop=False,
    )

    clock = LiveClock()
    msgbus = MessageBus(TraderId("HOMOLOG-E02"), clock)
    cache = Cache()
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=data_config,
        msgbus=msgbus, cache=cache, clock=clock,
    )
    exec_client = MT5LiveExecClientFactory.create(
        loop=loop, name="MT5", config=exec_config,
        msgbus=msgbus, cache=cache, clock=clock,
    )

    try:
        bid, ask = _get_prices(cfg.host, cfg.port, cfg.symbol)
        buy_stop = round(ask * 1.02, 2)
        sell_stop = round(bid * 0.98, 2)

        await data_client._connect()
        await exec_client._connect()

        cases = [
            ("TC-HOM-E02a", "BUY STOP_MARKET", StopMarketOrder(
                trader_id=msgbus.trader_id,
                strategy_id=StrategyId("HOMOLOG-E02"),
                instrument_id=inst_id,
                client_order_id=ClientOrderId("HOM-E02a"),
                order_side=OrderSide.BUY,
                quantity=Quantity.from_str("0.01"),
                trigger_price=Price.from_str(f"{buy_stop:.2f}"),
                trigger_type=TriggerType.DEFAULT,
                time_in_force=TimeInForce.GTC,
                init_id=UUID4(),
                ts_init=clock.timestamp_ns(),
            )),
            ("TC-HOM-E02b", "SELL STOP_MARKET", StopMarketOrder(
                trader_id=msgbus.trader_id,
                strategy_id=StrategyId("HOMOLOG-E02"),
                instrument_id=inst_id,
                client_order_id=ClientOrderId("HOM-E02b"),
                order_side=OrderSide.SELL,
                quantity=Quantity.from_str("0.01"),
                trigger_price=Price.from_str(f"{sell_stop:.2f}"),
                trigger_type=TriggerType.DEFAULT,
                time_in_force=TimeInForce.GTC,
                init_id=UUID4(),
                ts_init=clock.timestamp_ns(),
            )),
        ]

        for sub_id, label, order in cases:
            cache.add_order(order)
            cmd = SubmitOrder(
                trader_id=msgbus.trader_id,
                strategy_id=order.strategy_id,
                order=order,
                position_id=None,
                client_id=exec_client.id,
                command_id=UUID4(),
                ts_init=clock.timestamp_ns(),
            )
            try:
                venue_order_id, error = await _submit_stop_order(exec_client, cmd)
                if error is not None:
                    sub_results.append((sub_id, False, f"{label}: {error}"))
                    continue
                placed.append(venue_order_id)
                sub_results.append((sub_id, True, f"{label} venue={venue_order_id}"))
            except Exception as exc:
                sub_results.append((sub_id, False, f"{label}: {exc}"))

        all_ok = all(ok for _, ok, _ in sub_results)
        detail = "; ".join(f"{sid}={'OK' if ok else msg}" for sid, ok, msg in sub_results)
        report.add(
            case_id,
            name,
            ScenarioStatus.PASS if all_ok else ScenarioStatus.FAIL,
            detail,
            sub_results=sub_results,
        )
    except Exception as exc:
        report.add(case_id, name, ScenarioStatus.FAIL, str(exc))
    finally:
        for vid in placed:
            try:
                await _cancel_pending(exec_client, vid)
            except Exception as exc:
                logger.warning("Cleanup cancel failed for %s: %s", vid, exc)
        try:
            await exec_client._disconnect()
            await data_client._disconnect()
        except Exception:
            pass
