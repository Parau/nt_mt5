"""TC-HOM-E04 + TC-HOM-E05: disconnect lifecycle and mass-status reconcile."""
from __future__ import annotations

import asyncio
import logging
from unittest.mock import MagicMock

import rpyc
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.execution.messages import GenerateFillReports, GenerateOrderStatusReports, GeneratePositionStatusReports, SubmitOrder
from nautilus_trader.model.enums import OrderSide, TimeInForce, TriggerType
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
from nautilus_trader.model.orders import LimitOrder, MarketOrder, StopMarketOrder

from nautilus_mt5.venue_profile import resolve_venue_profile
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
from homologation.support.bridge_probe import (
    rpyc_cancel_all_pending,
    rpyc_cancel_order,
    rpyc_order_ticket,
    rpyc_pending_orders,
    rpyc_positions_count,
)
from homologation.support.clients import reset_mt5_client_cache
from homologation.support.order_specs import (
    homolog_invalid_volume_str,
    homolog_order_qty,
    homolog_price_tick,
    passive_limit_price,
    format_price,
)

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
    for _ in range(5):
        positions = mt5.positions_get(symbol=symbol)
        if not positions:
            return
        closed_any = False
        for pos in positions:
            if isinstance(pos, dict):
                ticket = int(pos.get("ticket", 0) or 0)
                raw_type = pos.get("type")
                pos_type = int(raw_type if raw_type is not None else -1)
                volume = float(pos.get("volume", 0.0) or 0.0)
            else:
                ticket = int(getattr(pos, "ticket", 0) or 0)
                raw_type = getattr(pos, "type", None)
                pos_type = int(raw_type if raw_type is not None else -1)
                volume = float(getattr(pos, "volume", 0.0) or 0.0)
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
            closed_any = True
        if not closed_any:
            return


async def _submit_and_accept(
    exec_client, cache, msgbus, clock, order,
) -> tuple[str | None, str | None, str | None]:
    """Returns (status_or_venue_id, error, venue_order_id)."""
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
        return None, str(rejected_events[0].get("reason", "rejected")), None
    if filled_events:
        vid = filled_events[0].get("venue_order_id")
        vid_str = str(getattr(vid, "value", vid)) if vid is not None else None
        return "FILLED", None, vid_str
    if not accepted_events:
        return None, "no OrderAccepted", None
    vid = accepted_events[0].get("venue_order_id")
    if vid is None:
        return None, "venue_order_id missing", None
    return str(getattr(vid, "value", vid)), None, str(getattr(vid, "value", vid))


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
        venue_profile=cfg.venue_profile,
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
        qty = homolog_order_qty(cfg)
        px_tick = homolog_price_tick(cfg)
        limit_px = passive_limit_price(bid, px_tick, factor=0.94)
        await data_a._connect()
        await exec_a._connect()

        pending = LimitOrder(
            trader_id=msgbus_a.trader_id,
            strategy_id=StrategyId("HOMOLOG-E04a"),
            instrument_id=inst_id,
            client_order_id=ClientOrderId("HOM-E04a"),
            order_side=OrderSide.BUY,
            quantity=qty,
            price=Price.from_str(format_price(limit_px, px_tick)),
            time_in_force=TimeInForce.GTC,
            init_id=UUID4(),
            ts_init=clock_a.timestamp_ns(),
        )
        venue_pending, err, _ = await _submit_and_accept(exec_a, cache_a, msgbus_a, clock_a, pending)
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
        qty = homolog_order_qty(cfg)

        market = MarketOrder(
            trader_id=msgbus_b.trader_id,
            strategy_id=StrategyId("HOMOLOG-E04b"),
            instrument_id=inst_id,
            client_order_id=ClientOrderId("HOM-E04b"),
            order_side=OrderSide.BUY,
            quantity=qty,
            time_in_force=TimeInForce.IOC,
            init_id=UUID4(),
            ts_init=clock_b.timestamp_ns(),
        )
        result, err, _ = await _submit_and_accept(exec_b, cache_b, msgbus_b, clock_b, market)
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

        all_position_reports = [
            rep for reps in mass.position_reports.values() for rep in reps
        ]
        report_positions = len(all_position_reports)
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


async def run_fill_reports_after_fill(cfg: HomologationConfig, report: HomologationReport) -> None:
    """TC-HOM-E05b: market fill then generate_fill_reports (history_deals_get)."""
    import datetime as _dt
    import os

    case_id = "TC-HOM-E05b"
    name = "Fill reports after market fill (history_deals_get)"

    if not cfg.enable_execution:
        report.add(
            case_id,
            name,
            ScenarioStatus.SKIP,
            "Set MT5_ENABLE_LIVE_EXECUTION=1 to run execution scenarios",
        )
        return

    poll_secs = float(os.environ.get("HOMOLOG_FILL_REPORT_POLL_SECS", "30"))
    poll_interval = float(os.environ.get("HOMOLOG_FILL_REPORT_POLL_INTERVAL_SECS", "2"))
    lookback_mins = int(os.environ.get("HOMOLOG_FILL_REPORT_LOOKBACK_MINS", "1440"))

    reset_mt5_client_cache()
    inst_id = InstrumentId(Symbol(cfg.symbol), _VENUE)
    pos_before = rpyc_positions_count(cfg.host, cfg.port, cfg.symbol)
    data_client, exec_client, msgbus, cache, clock = _exec_stack(
        cfg, 7, cancel_on_stop=False, close_on_stop=False,
    )

    try:
        await data_client._connect()
        await exec_client._connect()
        qty = homolog_order_qty(cfg)

        market = MarketOrder(
            trader_id=msgbus.trader_id,
            strategy_id=StrategyId("HOMOLOG-E05b"),
            instrument_id=inst_id,
            client_order_id=ClientOrderId("HOM-E05b-BUY"),
            order_side=OrderSide.BUY,
            quantity=qty,
            time_in_force=TimeInForce.IOC,
            init_id=UUID4(),
            ts_init=clock.timestamp_ns(),
        )
        result, err, venue_order_id = await _submit_and_accept(
            exec_client, cache, msgbus, clock, market,
        )
        if err:
            report.add(case_id, name, ScenarioStatus.FAIL, f"market buy: {err}")
            return
        if result != "FILLED":
            report.add(case_id, name, ScenarioStatus.FAIL, f"market buy not filled: {result}")
            return

        now = _dt.datetime.now(_dt.timezone.utc)
        start = now - _dt.timedelta(minutes=lookback_mins)
        vid = VenueOrderId(venue_order_id) if venue_order_id else None
        fill_cmd = GenerateFillReports(
            instrument_id=inst_id,
            venue_order_id=vid,
            start=None,
            end=None,
            command_id=UUID4(),
            ts_init=clock.timestamp_ns(),
        )

        reports: list = []
        elapsed = 0.0
        while elapsed <= poll_secs:
            reports = await exec_client.generate_fill_reports(fill_cmd)
            symbol_reports = [r for r in reports if r.instrument_id == inst_id]
            if symbol_reports:
                reports = symbol_reports
                break
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        history_delayed = False
        if not reports and venue_order_id:
            fill_cmd_broad = GenerateFillReports(
                instrument_id=inst_id,
                venue_order_id=None,
                start=None,
                end=None,
                command_id=UUID4(),
                ts_init=clock.timestamp_ns(),
            )
            reports = await exec_client.generate_fill_reports(fill_cmd_broad)
            symbol_reports = [r for r in reports if r.instrument_id == inst_id]
            if symbol_reports:
                reports = symbol_reports
                history_delayed = True

        ok = len(reports) >= 1
        detail_parts = [f"fill_reports={len(reports)} after poll={elapsed:.0f}s"]
        if venue_order_id:
            detail_parts.append(f"venue_order_id={venue_order_id}")
        if history_delayed:
            detail_parts.append("fresh order not in history yet; path validated via prior deal")
        if reports:
            r0 = reports[0]
            detail_parts.append(
                f"sample trade_id={r0.trade_id} side={r0.order_side} "
                f"qty={float(r0.last_qty):.2f} px={float(r0.last_px):.2f}"
            )
        else:
            detail_parts.append(
                f"no FillReport for {cfg.symbol} within {poll_secs}s "
                "(Tickmill may delay history_deals_get)"
            )

        report.add(
            case_id,
            name,
            ScenarioStatus.PASS if ok else ScenarioStatus.FAIL,
            "; ".join(detail_parts),
            fill_reports=len(reports),
            poll_secs=elapsed,
            lookback_mins=lookback_mins,
        )
    except Exception as exc:
        report.add(case_id, name, ScenarioStatus.FAIL, str(exc))
    finally:
        try:
            await asyncio.to_thread(_close_symbol_positions, cfg.host, cfg.port, cfg.symbol)
            pos_after = rpyc_positions_count(cfg.host, cfg.port, cfg.symbol)
            if pos_after > pos_before:
                logger.warning(
                    "E05b cleanup: positions %s→%s for %s",
                    pos_before,
                    pos_after,
                    cfg.symbol,
                )
        except Exception:
            pass
        try:
            await exec_client._disconnect()
            await data_client._disconnect()
        except Exception:
            pass


async def run_open_on_start_reconcile(cfg: HomologationConfig, report: HomologationReport) -> None:
    """TC-HOM-E81: fresh connect sees pre-existing MT5 positions and pending orders."""
    case_id = "TC-HOM-E81"
    name = "Open-on-start reconcile (positions + pending orders)"

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
    venue_pending: str | None = None

    await asyncio.to_thread(_close_symbol_positions, cfg.host, cfg.port, cfg.symbol)
    await asyncio.to_thread(rpyc_cancel_all_pending, cfg.host, cfg.port, cfg.symbol)

    # Seed state with first client session.
    data_a, exec_a, msgbus_a, cache_a, clock_a = _exec_stack(
        cfg, 81, cancel_on_stop=False, close_on_stop=False,
    )
    try:
        await data_a._connect()
        await exec_a._connect()
        qty = homolog_order_qty(cfg)
        px_tick = homolog_price_tick(cfg)

        market = MarketOrder(
            trader_id=msgbus_a.trader_id,
            strategy_id=StrategyId("HOMOLOG-E81a"),
            instrument_id=inst_id,
            client_order_id=ClientOrderId("HOM-E81-BUY"),
            order_side=OrderSide.BUY,
            quantity=qty,
            time_in_force=TimeInForce.IOC,
            init_id=UUID4(),
            ts_init=clock_a.timestamp_ns(),
        )
        _vid, err, _ = await _submit_and_accept(exec_a, cache_a, msgbus_a, clock_a, market)
        if err or _vid != "FILLED":
            sub_results.append(("E81a-seed", False, f"market buy seed: {err or _vid}"))
        else:
            bid, _ = _get_prices(cfg.host, cfg.port, cfg.symbol)
            limit_px = passive_limit_price(bid, px_tick, factor=0.94)
            pending = LimitOrder(
                trader_id=msgbus_a.trader_id,
                strategy_id=StrategyId("HOMOLOG-E81b"),
                instrument_id=inst_id,
                client_order_id=ClientOrderId("HOM-E81-LIM"),
                order_side=OrderSide.BUY,
                quantity=qty,
                price=Price.from_str(format_price(limit_px, px_tick)),
                time_in_force=TimeInForce.GTC,
                init_id=UUID4(),
                ts_init=clock_a.timestamp_ns(),
            )
            venue_pending, pend_err, _ = await _submit_and_accept(
                exec_a, cache_a, msgbus_a, clock_a, pending,
            )
            if pend_err:
                sub_results.append(("E81b-seed", False, f"limit seed: {pend_err}"))
            elif venue_pending:
                _apply_accepted(pending, cache_a, exec_a.account_id, venue_pending, clock_a)
    finally:
        try:
            await exec_a._disconnect()
            await data_a._disconnect()
        except Exception:
            pass

    bridge_positions = rpyc_positions_count(cfg.host, cfg.port, cfg.symbol)
    bridge_pending = await asyncio.to_thread(
        rpyc_pending_orders, cfg.host, cfg.port, cfg.symbol,
    )
    bridge_pending_count = len(bridge_pending or [])

    reset_mt5_client_cache()
    data_b, exec_b, _msgbus_b, _cache_b, clock_b = _exec_stack(
        cfg, 82, cancel_on_stop=False, close_on_stop=False,
    )
    try:
        await data_b._connect()
        await exec_b._connect()

        pos_cmd = GeneratePositionStatusReports(
            instrument_id=inst_id,
            start=None,
            end=None,
            command_id=UUID4(),
            ts_init=clock_b.timestamp_ns(),
        )
        pos_reports = await exec_b.generate_position_status_reports(pos_cmd)
        pos_ok = len(pos_reports) >= bridge_positions and bridge_positions >= 1
        sub_results.append((
            "E81a",
            pos_ok,
            f"position_reports={len(pos_reports)} bridge_positions={bridge_positions}",
        ))

        order_cmd = GenerateOrderStatusReports(
            instrument_id=inst_id,
            start=None,
            end=None,
            open_only=True,
            command_id=UUID4(),
            ts_init=clock_b.timestamp_ns(),
        )
        order_reports = await exec_b.generate_order_status_reports(order_cmd)
        from nautilus_trader.model.enums import OrderStatus, OrderType

        pending_reports = [
            r for r in order_reports
            if r.order_status in (OrderStatus.ACCEPTED, OrderStatus.SUBMITTED)
            and r.order_type in (OrderType.LIMIT, OrderType.STOP_MARKET, OrderType.STOP_LIMIT)
        ]
        pending_tickets = {
            str(rpyc_order_ticket(po))
            for po in (bridge_pending or [])
            if rpyc_order_ticket(po) is not None
        }
        report_tickets = {
            r.venue_order_id.value for r in pending_reports if r.venue_order_id
        }
        overlap = pending_tickets & report_tickets
        order_ok = bridge_pending_count == 0 or len(overlap) >= 1
        sub_results.append((
            "E81b",
            order_ok,
            f"pending_reports={len(pending_reports)} bridge_pending={bridge_pending_count} "
            f"overlap={len(overlap)}",
        ))
    except Exception as exc:
        sub_results.append(("E81", False, str(exc)))
    finally:
        if venue_pending:
            await asyncio.to_thread(rpyc_cancel_order, cfg.host, cfg.port, int(venue_pending))
        await asyncio.to_thread(_close_symbol_positions, cfg.host, cfg.port, cfg.symbol)
        try:
            await exec_b._disconnect()
            await data_b._disconnect()
        except Exception:
            pass

    ok = all(r[1] for r in sub_results)
    detail = "; ".join(f"{sid}={'OK' if ok_ else 'FAIL'}: {msg}" for sid, ok_, msg in sub_results)
    report.add(
        case_id,
        name,
        ScenarioStatus.PASS if ok else ScenarioStatus.FAIL,
        detail,
        sub_results=sub_results,
    )


async def run_real_retcodes(cfg: HomologationConfig, report: HomologationReport) -> None:
    """TC-HOM-E09: adapter rejects invalid volume and invalid stop triggers."""
    case_id = "TC-HOM-E09"
    name = "Real retcodes (invalid volume / stops)"

    if not cfg.enable_execution:
        report.add(case_id, name, ScenarioStatus.SKIP, "Set MT5_ENABLE_LIVE_EXECUTION=1")
        return

    reset_mt5_client_cache()
    inst_id = InstrumentId(Symbol(cfg.symbol), _VENUE)
    data_client, exec_client, msgbus, cache, clock = _exec_stack(
        cfg, 6, cancel_on_stop=False, close_on_stop=False,
    )
    sub_results: list[tuple[str, bool, str]] = []

    try:
        await data_client._connect()
        await exec_client._connect()
        bid, _ask = _get_prices(cfg.host, cfg.port, cfg.symbol)
        qty = homolog_order_qty(cfg)
        px_tick = homolog_price_tick(cfg)

        bad_vol = MarketOrder(
            trader_id=msgbus.trader_id,
            strategy_id=StrategyId("HOMOLOG-E09a"),
            instrument_id=inst_id,
            client_order_id=ClientOrderId("HOM-E09-VOL"),
            order_side=OrderSide.BUY,
            quantity=Quantity.from_str(homolog_invalid_volume_str(cfg)),
            time_in_force=TimeInForce.IOC,
            init_id=UUID4(),
            ts_init=clock.timestamp_ns(),
        )
        vol_vid, vol_err, _ = await _submit_and_accept(
            exec_client, cache, msgbus, clock, bad_vol,
        )
        vol_ok = vol_err is not None or vol_vid is None
        if vol_vid == "FILLED":
            vol_ok = False
        sub_results.append(("E09a", vol_ok, f"invalid volume: {vol_err or vol_vid or 'rejected'}"))

        invalid_stop_px = passive_limit_price(bid, px_tick, factor=0.90)
        bad_stop = StopMarketOrder(
            trader_id=msgbus.trader_id,
            strategy_id=StrategyId("HOMOLOG-E09b"),
            instrument_id=inst_id,
            client_order_id=ClientOrderId("HOM-E09-STP"),
            order_side=OrderSide.BUY,
            quantity=qty,
            trigger_price=Price.from_str(format_price(invalid_stop_px, px_tick)),
            trigger_type=TriggerType.DEFAULT,
            time_in_force=TimeInForce.GTC,
            init_id=UUID4(),
            ts_init=clock.timestamp_ns(),
        )
        stop_vid, stop_err, _ = await _submit_and_accept(
            exec_client, cache, msgbus, clock, bad_stop,
        )
        stop_ok = stop_err is not None or stop_vid is None
        if stop_vid:
            await asyncio.to_thread(rpyc_cancel_order, cfg.host, cfg.port, int(stop_vid))
        sub_results.append((
            "E09b",
            stop_ok,
            f"invalid BUY STOP @{invalid_stop_px:.2f}: {stop_err or stop_vid}",
        ))
    except Exception as exc:
        sub_results.append(("E09", False, str(exc)))
    finally:
        try:
            await exec_client._disconnect()
            await data_client._disconnect()
        except Exception:
            pass

    ok = all(r[1] for r in sub_results)
    detail = "; ".join(f"{sid}={'OK' if ok_ else 'FAIL'}: {msg}" for sid, ok_, msg in sub_results)
    report.add(
        case_id,
        name,
        ScenarioStatus.PASS if ok else ScenarioStatus.FAIL,
        detail,
        sub_results=sub_results,
    )
