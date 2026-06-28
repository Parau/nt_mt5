"""TC-HOM-E04 + TC-HOM-E05: disconnect lifecycle and mass-status reconcile."""
from __future__ import annotations

import asyncio
import logging
from unittest.mock import MagicMock

import rpyc
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.execution.messages import SubmitOrder
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.events import OrderAccepted, OrderSubmitted
from nautilus_trader.model.identifiers import (
    ClientOrderId,
    InstrumentId,
    StrategyId,
    Symbol,
    TraderId,
    Venue,
    VenueOrderId,
)
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.model.orders import LimitOrder, MarketOrder

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
from nautilus_mt5.metatrader5.MetaTrader5 import MetaTrader5

from homologation.config import HomologationConfig
from homologation.report import HomologationReport, ScenarioStatus
from homologation.support.bridge_probe import rpyc_cancel_order, rpyc_positions_count
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


def _retcode(result) -> int | None:
    if result is None:
        return None
    if isinstance(result, dict):
        return int(result.get("retcode", 0) or 0)
    return int(getattr(result, "retcode", 0) or 0)


def _apply_accepted(order, cache, account_id, venue_order_id: str, clock) -> None:
    ts = clock.timestamp_ns()
    submitted = OrderSubmitted(
        trader_id=order.trader_id,
        strategy_id=order.strategy_id,
        instrument_id=order.instrument_id,
        client_order_id=order.client_order_id,
        account_id=account_id,
        event_id=UUID4(),
        ts_event=ts,
        ts_init=ts,
    )
    order.apply(submitted)
    cache.update_order(order)
    accepted = OrderAccepted(
        trader_id=order.trader_id,
        strategy_id=order.strategy_id,
        instrument_id=order.instrument_id,
        client_order_id=order.client_order_id,
        venue_order_id=VenueOrderId(venue_order_id),
        account_id=account_id,
        event_id=UUID4(),
        ts_event=ts,
        ts_init=ts,
    )
    order.apply(accepted)
    cache.update_order(order)


def _close_symbol_positions(host: str, port: int, symbol: str) -> None:
    mt5 = MetaTrader5(host=host, port=port)
    positions = mt5.positions_get(symbol=symbol)
    if not positions:
        return
    for pos in positions:
        ticket = int(getattr(pos, "ticket", 0))
        pos_type = int(getattr(pos, "type", -1))
        volume = float(getattr(pos, "volume", 0.0))
        if not ticket or volume <= 0:
            continue
        close_type = 1 if pos_type == 0 else 0
        mt5.order_send({
            "action": 1,
            "symbol": symbol,
            "volume": volume,
            "type": close_type,
            "position": ticket,
            "deviation": 20,
            "type_filling": 1,
        })


async def _submit_and_accept(exec_client, cache, msgbus, clock, order) -> tuple[str | None, str | None]:
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
    accepted_events: list[dict] = []
    rejected_events: list[dict] = []
    filled_events: list[dict] = []

    orig_accepted = exec_client.generate_order_accepted
    orig_rejected = exec_client.generate_order_rejected
    orig_filled = exec_client.generate_order_filled

    exec_client.generate_order_accepted = MagicMock(
        side_effect=lambda *a, **kw: accepted_events.append(kw),
    )
    exec_client.generate_order_rejected = MagicMock(
        side_effect=lambda *a, **kw: rejected_events.append(kw),
    )
    exec_client.generate_order_filled = MagicMock(
        side_effect=lambda *a, **kw: filled_events.append(kw),
    )

    try:
        await exec_client._submit_order(cmd)
    finally:
        exec_client.generate_order_accepted = orig_accepted
        exec_client.generate_order_rejected = orig_rejected
        exec_client.generate_order_filled = orig_filled

    if rejected_events:
        return None, str(rejected_events[0].get("reason", "rejected"))
    if filled_events:
        return "FILLED", None
    if not accepted_events:
        return None, "no OrderAccepted"
    vid = accepted_events[0].get("venue_order_id")
    if vid is None:
        return None, "venue_order_id missing"
    return str(getattr(vid, "value", vid)), None


def _exec_stack(cfg: HomologationConfig, client_id: int, *, cancel_on_stop: bool, close_on_stop: bool):
    rpyc_cfg = ExternalRPyCTerminalConfig(host=cfg.host, port=cfg.port, keep_alive=True)
    provider = MetaTrader5InstrumentProviderConfig(
        load_symbols=frozenset({MT5Symbol(symbol=cfg.symbol, broker=cfg.broker)}),
    )
    data_config = MetaTrader5DataClientConfig(
        client_id=client_id,
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=rpyc_cfg,
        instrument_provider=provider,
        venue_profile=TICKMILL_DEMO_PROFILE,
    )
    exec_config = MetaTrader5ExecClientConfig(
        client_id=client_id,
        account_id=cfg.account_number,
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=rpyc_cfg,
        instrument_provider=provider,
        cancel_on_stop=cancel_on_stop,
        close_on_stop=close_on_stop,
    )
    clock = LiveClock()
    msgbus = MessageBus(TraderId(f"HOMOLOG-E0{client_id}"), clock)
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
    return data_client, exec_client, msgbus, cache, clock


async def run_cancel_close_on_stop(cfg: HomologationConfig, report: HomologationReport) -> None:
    """TC-HOM-E04: cancel_on_stop cancels pending; close_on_stop closes positions."""
    case_id = "TC-HOM-E04"
    name = "cancel_on_stop / close_on_stop on disconnect"

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
    sub_results: list[tuple[str, bool, str]] = []

    # --- E04a: cancel_on_stop ---
    data_a, exec_a, msgbus_a, cache_a, clock_a = _exec_stack(
        cfg, 4, cancel_on_stop=True, close_on_stop=False,
    )
    venue_pending: str | None = None
    try:
        bid, _ = _get_prices(cfg.host, cfg.port, cfg.symbol)
        limit_px = round(bid * 0.94, 2)
        await data_a._connect()
        await exec_a._connect()

        pending = LimitOrder(
            trader_id=msgbus_a.trader_id,
            strategy_id=StrategyId("HOMOLOG-E04a"),
            instrument_id=inst_id,
            client_order_id=ClientOrderId("HOM-E04a"),
            order_side=OrderSide.BUY,
            quantity=Quantity.from_str("0.01"),
            price=Price.from_str(f"{limit_px:.2f}"),
            time_in_force=TimeInForce.GTC,
            init_id=UUID4(),
            ts_init=clock_a.timestamp_ns(),
        )
        venue_pending, err = await _submit_and_accept(exec_a, cache_a, msgbus_a, clock_a, pending)
        if err:
            sub_results.append(("E04a", False, f"pending submit: {err}"))
        else:
            _apply_accepted(pending, cache_a, exec_a.account_id, venue_pending, clock_a)
            await exec_a._disconnect()
            retry = await asyncio.to_thread(
                rpyc_cancel_order, cfg.host, cfg.port, int(venue_pending),
            )
            code = _retcode(retry)
            ok = code not in (10008, 10009)  # not still placed / done
            sub_results.append((
                "E04a",
                ok,
                f"cancel_on_stop venue={venue_pending} retry_retcode={code}",
            ))
    except Exception as exc:
        sub_results.append(("E04a", False, str(exc)))
    finally:
        if venue_pending:
            await asyncio.to_thread(rpyc_cancel_order, cfg.host, cfg.port, int(venue_pending))
        try:
            await exec_a._disconnect()
            await data_a._disconnect()
        except Exception:
            pass

    reset_mt5_client_cache()

    # --- E04b: close_on_stop ---
    data_b, exec_b, msgbus_b, cache_b, clock_b = _exec_stack(
        cfg, 5, cancel_on_stop=False, close_on_stop=True,
    )
    try:
        pos_before = rpyc_positions_count(cfg.host, cfg.port, cfg.symbol)
        await data_b._connect()
        await exec_b._connect()

        market = MarketOrder(
            trader_id=msgbus_b.trader_id,
            strategy_id=StrategyId("HOMOLOG-E04b"),
            instrument_id=inst_id,
            client_order_id=ClientOrderId("HOM-E04b"),
            order_side=OrderSide.BUY,
            quantity=Quantity.from_str("0.01"),
            time_in_force=TimeInForce.IOC,
            init_id=UUID4(),
            ts_init=clock_b.timestamp_ns(),
        )
        result, err = await _submit_and_accept(exec_b, cache_b, msgbus_b, clock_b, market)
        if err:
            sub_results.append(("E04b", False, f"market buy: {err}"))
        elif result != "FILLED":
            sub_results.append(("E04b", False, f"market buy not filled: {result}"))
        else:
            await asyncio.sleep(1.0)
            await exec_b._disconnect()
            await asyncio.sleep(1.0)
            pos_after = rpyc_positions_count(cfg.host, cfg.port, cfg.symbol)
            ok = pos_after <= pos_before
            sub_results.append((
                "E04b",
                ok,
                f"close_on_stop positions {pos_before}→{pos_after}",
            ))
            if not ok:
                await asyncio.to_thread(_close_symbol_positions, cfg.host, cfg.port, cfg.symbol)
    except Exception as exc:
        sub_results.append(("E04b", False, str(exc)))
    finally:
        try:
            await exec_b._disconnect()
            await data_b._disconnect()
        except Exception:
            pass

    all_ok = all(ok for _, ok, _ in sub_results)
    detail = "; ".join(f"{sid}={'OK' if ok else msg}" for sid, ok, msg in sub_results)
    report.add(case_id, name, ScenarioStatus.PASS if all_ok else ScenarioStatus.FAIL, detail, sub_results=sub_results)


async def run_reconcile_mass_status(cfg: HomologationConfig, report: HomologationReport) -> None:
    """TC-HOM-E05: reconnect + generate_mass_status vs bridge positions."""
    case_id = "TC-HOM-E05"
    name = "Reconcile orders/positions on reconnect"

    if not cfg.enable_execution:
        report.add(
            case_id,
            name,
            ScenarioStatus.SKIP,
            "Set MT5_ENABLE_LIVE_EXECUTION=1 to run execution scenarios",
        )
        return

    reset_mt5_client_cache()
    data_client, exec_client, _msgbus, _cache, _clock = _exec_stack(
        cfg, 2, cancel_on_stop=False, close_on_stop=False,
    )

    try:
        bridge_positions = rpyc_positions_count(cfg.host, cfg.port, cfg.symbol)
        await data_client._connect()
        await exec_client._connect()

        mass = await exec_client.generate_mass_status(lookback_mins=60)
        if mass is None:
            report.add(case_id, name, ScenarioStatus.FAIL, "generate_mass_status returned None")
            return

        report_positions = len(mass.position_reports)
        ok = report_positions >= bridge_positions
        report.add(
            case_id,
            name,
            ScenarioStatus.PASS if ok else ScenarioStatus.FAIL,
            (
                f"mass_status positions={report_positions} "
                f"bridge.positions_get({cfg.symbol})={bridge_positions}"
            ),
            bridge_positions=bridge_positions,
            report_positions=report_positions,
            order_reports=len(mass.order_reports),
            fill_reports=len(mass.fill_reports),
        )
    except Exception as exc:
        report.add(case_id, name, ScenarioStatus.FAIL, str(exc))
    finally:
        try:
            await exec_client._disconnect()
            await data_client._disconnect()
        except Exception:
            pass
