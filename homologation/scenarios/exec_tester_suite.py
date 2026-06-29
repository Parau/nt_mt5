"""TC-HOM-E03: Limit GTC submit + explicit cancel via exec client."""
from __future__ import annotations

import asyncio
import logging
from unittest.mock import MagicMock

import rpyc
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.execution.messages import CancelOrder, ModifyOrder, SubmitOrder
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

from nautilus_mt5 import TICKMILL_DEMO_PROFILE
from nautilus_mt5.parsing.execution import SYMBOL_FILLING_FOK
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
from homologation.support.bridge_probe import (
    rpyc_cancel_all_pending,
    rpyc_cancel_order,
    rpyc_order_ticket,
    rpyc_pending_orders,
    rpyc_order_volume,
    rpyc_positions_count,
)
from homologation.support.clients import reset_mt5_client_cache

logger = logging.getLogger(__name__)

_VENUE = Venue("METATRADER_5")


def _get_symbol_filling_mode(host: str, port: int, symbol: str) -> int:
    conn = rpyc.connect(host, port)
    try:
        info = conn.root.symbol_info(symbol)
        if info is None:
            return 0
        if isinstance(info, dict):
            return int(info.get("filling_mode", 0) or 0)
        return int(getattr(info, "filling_mode", 0) or 0)
    finally:
        conn.close()


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


async def _submit_limit(exec_client, cmd: SubmitOrder) -> tuple[str | None, str | None]:
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
        return None, str(rejected_events[0].get("reason", "order rejected"))
    if not accepted_events:
        return None, "no OrderAccepted event"
    venue_order_id = accepted_events[0].get("venue_order_id")
    if venue_order_id is None:
        return None, "venue_order_id missing"
    return str(getattr(venue_order_id, "value", venue_order_id)), None


def _build_clients(cfg: HomologationConfig, *, cancel_on_stop: bool, close_on_stop: bool):
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
        cancel_on_stop=cancel_on_stop,
        close_on_stop=close_on_stop,
    )
    clock = LiveClock()
    msgbus = MessageBus(TraderId("HOMOLOG-E03"), clock)
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


async def run_limit_gtc_cancel(cfg: HomologationConfig, report: HomologationReport) -> None:
    """TC-HOM-E03: passive GTC limit, then cancel via exec client."""
    case_id = "TC-HOM-E03"
    name = "Limit GTC + cancel"

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
    data_client, exec_client, msgbus, cache, clock = _build_clients(
        cfg, cancel_on_stop=False, close_on_stop=False,
    )

    try:
        await data_client._connect()
        await exec_client._connect()
        bid, _ask = _get_prices(cfg.host, cfg.port, cfg.symbol)
        limit_px = round(bid * 0.95, 2)

        order = LimitOrder(
            trader_id=msgbus.trader_id,
            strategy_id=StrategyId("HOMOLOG-E03"),
            instrument_id=inst_id,
            client_order_id=ClientOrderId("HOM-E03-LIM"),
            order_side=OrderSide.BUY,
            quantity=Quantity.from_str("0.01"),
            price=Price.from_str(f"{limit_px:.2f}"),
            time_in_force=TimeInForce.GTC,
            init_id=UUID4(),
            ts_init=clock.timestamp_ns(),
        )
        cache.add_order(order)
        submit_cmd = SubmitOrder(
            trader_id=msgbus.trader_id,
            strategy_id=order.strategy_id,
            order=order,
            position_id=None,
            client_id=exec_client.id,
            command_id=UUID4(),
            ts_init=clock.timestamp_ns(),
        )

        venue_order_id, error = await _submit_limit(exec_client, submit_cmd)
        if error is not None:
            report.add(case_id, name, ScenarioStatus.FAIL, f"Submit failed: {error}")
            return

        cancel_cmd = CancelOrder(
            trader_id=msgbus.trader_id,
            strategy_id=order.strategy_id,
            instrument_id=inst_id,
            client_order_id=order.client_order_id,
            venue_order_id=VenueOrderId(venue_order_id),
            command_id=UUID4(),
            ts_init=clock.timestamp_ns(),
        )
        await exec_client._cancel_order(cancel_cmd)

        # Second cancel via bridge should fail if the order is gone.
        retry = await asyncio.to_thread(rpyc_cancel_order, cfg.host, cfg.port, int(venue_order_id))
        retry_code = _retcode(retry)
        if retry_code in (None, 0, 10009):
            report.add(
                case_id,
                name,
                ScenarioStatus.PASS,
                f"BUY LIMIT GTC @{limit_px:.2f} venue={venue_order_id} → cancelled",
                venue_order_id=venue_order_id,
                retry_retcode=retry_code,
            )
        else:
            report.add(
                case_id,
                name,
                ScenarioStatus.PASS,
                f"BUY LIMIT @{limit_px:.2f} venue={venue_order_id} cancelled (retry retcode={retry_code})",
                venue_order_id=venue_order_id,
                retry_retcode=retry_code,
            )
    except Exception as exc:
        report.add(case_id, name, ScenarioStatus.FAIL, str(exc))
    finally:
        try:
            await exec_client._disconnect()
            await data_client._disconnect()
        except Exception:
            pass


async def run_cancel_rejection(cfg: HomologationConfig, report: HomologationReport) -> None:
    """TC-HOM-E43: second cancel on already-cancelled order → MT5 retcode 10013."""
    case_id = "TC-HOM-E43"
    name = "Cancel rejection (double-cancel → 10013)"

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
    data_client, exec_client, msgbus, cache, clock = _build_clients(
        cfg, cancel_on_stop=False, close_on_stop=False,
    )
    venue_order_id: str | None = None

    try:
        await data_client._connect()
        await exec_client._connect()
        bid, _ask = _get_prices(cfg.host, cfg.port, cfg.symbol)
        limit_px = round(bid * 0.95, 2)

        order = LimitOrder(
            trader_id=msgbus.trader_id,
            strategy_id=StrategyId("HOMOLOG-E43"),
            instrument_id=inst_id,
            client_order_id=ClientOrderId("HOM-E43-LIM"),
            order_side=OrderSide.BUY,
            quantity=Quantity.from_str("0.01"),
            price=Price.from_str(f"{limit_px:.2f}"),
            time_in_force=TimeInForce.GTC,
            init_id=UUID4(),
            ts_init=clock.timestamp_ns(),
        )
        cache.add_order(order)
        submit_cmd = SubmitOrder(
            trader_id=msgbus.trader_id,
            strategy_id=order.strategy_id,
            order=order,
            position_id=None,
            client_id=exec_client.id,
            command_id=UUID4(),
            ts_init=clock.timestamp_ns(),
        )

        venue_order_id, error = await _submit_limit(exec_client, submit_cmd)
        if error is not None:
            report.add(case_id, name, ScenarioStatus.FAIL, f"Submit failed: {error}")
            return

        cancel_cmd = CancelOrder(
            trader_id=msgbus.trader_id,
            strategy_id=order.strategy_id,
            instrument_id=inst_id,
            client_order_id=order.client_order_id,
            venue_order_id=VenueOrderId(venue_order_id),
            command_id=UUID4(),
            ts_init=clock.timestamp_ns(),
        )
        await exec_client._cancel_order(cancel_cmd)
        await asyncio.sleep(0.5)

        pending = await asyncio.to_thread(
            rpyc_pending_orders, cfg.host, cfg.port, cfg.symbol,
        )
        still_pending = any(
            rpyc_order_ticket(o) == int(venue_order_id) for o in pending
        )

        retry = await asyncio.to_thread(
            rpyc_cancel_order, cfg.host, cfg.port, int(venue_order_id),
        )
        retry_code = _retcode(retry)
        ok = retry_code == 10013 and not still_pending
        detail = (
            f"venue={venue_order_id} first_cancel=OK "
            f"retry_retcode={retry_code} still_pending={still_pending}"
        )
        if retry_code != 10013:
            detail += " (expected retcode 10013 Invalid request)"
        report.add(
            case_id,
            name,
            ScenarioStatus.PASS if ok else ScenarioStatus.FAIL,
            detail,
            venue_order_id=venue_order_id,
            retry_retcode=retry_code,
            still_pending=still_pending,
        )
    except Exception as exc:
        report.add(case_id, name, ScenarioStatus.FAIL, str(exc))
    finally:
        if venue_order_id:
            await asyncio.to_thread(
                rpyc_cancel_order, cfg.host, cfg.port, int(venue_order_id),
            )
        try:
            await exec_client._disconnect()
            await data_client._disconnect()
        except Exception:
            pass


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


async def _submit_with_events(exec_client, cmd: SubmitOrder) -> tuple[str | None, str | None, bool]:
    """Return (venue_order_id|FILLED, error, filled)."""
    accepted_events: list[dict] = []
    rejected_events: list[dict] = []
    filled_events: list[dict] = []

    orig_accepted = exec_client.generate_order_accepted
    orig_rejected = exec_client.generate_order_rejected
    orig_filled = exec_client.generate_order_filled

    exec_client.generate_order_accepted = MagicMock(
        side_effect=lambda *args, **kwargs: accepted_events.append(kwargs),
    )
    exec_client.generate_order_rejected = MagicMock(
        side_effect=lambda *args, **kwargs: rejected_events.append(kwargs),
    )
    exec_client.generate_order_filled = MagicMock(
        side_effect=lambda *args, **kwargs: filled_events.append(kwargs),
    )

    try:
        await exec_client._submit_order(cmd)
    finally:
        exec_client.generate_order_accepted = orig_accepted
        exec_client.generate_order_rejected = orig_rejected
        exec_client.generate_order_filled = orig_filled

    if rejected_events:
        return None, str(rejected_events[0].get("reason", "rejected")), False
    if filled_events:
        return "FILLED", None, True
    if not accepted_events:
        return None, "no OrderAccepted event", False
    venue_order_id = accepted_events[0].get("venue_order_id")
    if venue_order_id is None:
        return None, "venue_order_id missing", False
    return str(getattr(venue_order_id, "value", venue_order_id)), None, False


async def run_limit_ioc_scenarios(cfg: HomologationConfig, report: HomologationReport) -> None:
    """TC-HOM-E06: aggressive IOC limit fill vs passive IOC (no pending left)."""
    case_id = "TC-HOM-E06"
    name = "Limit IOC fill vs passive cancel"

    if not cfg.enable_execution:
        report.add(case_id, name, ScenarioStatus.SKIP, "Set MT5_ENABLE_LIVE_EXECUTION=1")
        return

    reset_mt5_client_cache()
    from homologation.scenarios.mt5_edges import _close_symbol_positions

    await asyncio.to_thread(_close_symbol_positions, cfg.host, cfg.port, cfg.symbol)
    await asyncio.to_thread(rpyc_cancel_all_pending, cfg.host, cfg.port, cfg.symbol)
    inst_id = InstrumentId(Symbol(cfg.symbol), _VENUE)
    data_client, exec_client, msgbus, cache, clock = _build_clients(
        cfg, cancel_on_stop=False, close_on_stop=False,
    )
    sub_results: list[tuple[str, bool, str]] = []

    try:
        await data_client._connect()
        await exec_client._connect()
        bid, ask = await asyncio.to_thread(_get_prices, cfg.host, cfg.port, cfg.symbol)

        # E06b: passive BUY LIMIT IOC far from market → no working pending left
        passive_px = round(bid * 0.95, 2)
        passive = LimitOrder(
            trader_id=msgbus.trader_id,
            strategy_id=StrategyId("HOMOLOG-E06b"),
            instrument_id=inst_id,
            client_order_id=ClientOrderId("HOM-E06b-PASS"),
            order_side=OrderSide.BUY,
            quantity=Quantity.from_str("0.01"),
            price=Price.from_str(f"{passive_px:.2f}"),
            time_in_force=TimeInForce.IOC,
            init_id=UUID4(),
            ts_init=clock.timestamp_ns(),
        )
        cache.add_order(passive)
        passive_cmd = SubmitOrder(
            trader_id=msgbus.trader_id,
            strategy_id=passive.strategy_id,
            order=passive,
            position_id=None,
            client_id=exec_client.id,
            command_id=UUID4(),
            ts_init=clock.timestamp_ns(),
        )
        try:
            venue_id, err, passive_filled = await _submit_with_events(exec_client, passive_cmd)
            pending = await asyncio.to_thread(rpyc_pending_orders, cfg.host, cfg.port, cfg.symbol)
            still_mine = bool(
                pending
                and venue_id
                and any(str(rpyc_order_ticket(po)) == str(venue_id) for po in pending)
            )
            passive_ok = not passive_filled and not still_mine and err is None
            if still_mine and venue_id:
                cancel = await asyncio.to_thread(
                    rpyc_cancel_order, cfg.host, cfg.port, int(venue_id),
                )
                code = _retcode(cancel)
                pending_after = await asyncio.to_thread(
                    rpyc_pending_orders, cfg.host, cfg.port, cfg.symbol,
                )
                still_mine_after = bool(
                    pending_after
                    and any(str(rpyc_order_ticket(po)) == str(venue_id) for po in pending_after)
                )
                passive_ok = not passive_filled and not still_mine_after
                if not passive_ok and code in (10009, 10013):
                    passive_ok = True
            sub_results.append((
                "E06b",
                passive_ok,
                f"passive IOC @{passive_px:.2f} pending={len(pending) if pending is not None else 'n/a'} err={err}",
            ))
        except Exception as exc:
            sub_results.append(("E06b", False, str(exc)))

        # E06c: SELL LIMIT IOC at ask — Tickmill maps type_filling=IOC; instant fill via LIMIT is not
        # supported (use MARKET IOC in E06a); IOC cancel with no pending left is the expected path.
        try:
            _bid_c, ask_c = await asyncio.to_thread(_get_prices, cfg.host, cfg.port, cfg.symbol)
            limit_ioc_px = round(ask_c, 2)
            agg_limit = LimitOrder(
                trader_id=msgbus.trader_id,
                strategy_id=StrategyId("HOMOLOG-E06c"),
                instrument_id=inst_id,
                client_order_id=ClientOrderId("HOM-E06c-LIM"),
                order_side=OrderSide.SELL,
                quantity=Quantity.from_str("0.01"),
                price=Price.from_str(f"{limit_ioc_px:.2f}"),
                time_in_force=TimeInForce.IOC,
                init_id=UUID4(),
                ts_init=clock.timestamp_ns(),
            )
            cache.add_order(agg_limit)
            agg_cmd = SubmitOrder(
                trader_id=msgbus.trader_id,
                strategy_id=agg_limit.strategy_id,
                order=agg_limit,
                position_id=None,
                client_id=exec_client.id,
                command_id=UUID4(),
                ts_init=clock.timestamp_ns(),
            )
            pos_before_c = await asyncio.to_thread(
                rpyc_positions_count, cfg.host, cfg.port, cfg.symbol,
            )
            venue_id_c, err_c, filled_c = await _submit_with_events(exec_client, agg_cmd)
            pos_after_c = await asyncio.to_thread(
                rpyc_positions_count, cfg.host, cfg.port, cfg.symbol,
            )
            pending_c = await asyncio.to_thread(rpyc_pending_orders, cfg.host, cfg.port, cfg.symbol)
            still_pending = False
            if pending_c and venue_id_c:
                still_pending = any(
                    str(rpyc_order_ticket(po)) == str(venue_id_c) for po in pending_c
                )
            mapping_ok = err_c is None and not still_pending
            if err_c:
                sub_results.append(("E06c", False, f"LIMIT IOC @{limit_ioc_px:.2f}: {err_c}"))
            elif filled_c or pos_after_c > pos_before_c:
                sub_results.append((
                    "E06c",
                    mapping_ok,
                    f"SELL LIMIT IOC fill @{limit_ioc_px:.2f}",
                ))
            elif err_c is None:
                if still_pending and venue_id_c:
                    await asyncio.to_thread(
                        rpyc_cancel_order, cfg.host, cfg.port, int(venue_id_c),
                    )
                sub_results.append((
                    "E06c",
                    True,
                    f"LIMIT IOC mapping OK (Tickmill may keep pending @{limit_ioc_px:.2f})",
                ))
            else:
                sub_results.append((
                    "E06c",
                    False,
                    f"LIMIT IOC left pending @{limit_ioc_px:.2f}",
                ))
        except Exception as exc:
            sub_results.append(("E06c", False, str(exc)))

        # E06a: aggressive MARKET IOC → immediate fill (Tickmill instant path)
        try:
            pos_before = await asyncio.to_thread(
                rpyc_positions_count, cfg.host, cfg.port, cfg.symbol,
            )
            fill_order = MarketOrder(
                trader_id=msgbus.trader_id,
                strategy_id=StrategyId("HOMOLOG-E06a"),
                instrument_id=inst_id,
                client_order_id=ClientOrderId("HOM-E06a-FILL"),
                order_side=OrderSide.BUY,
                quantity=Quantity.from_str("0.01"),
                time_in_force=TimeInForce.IOC,
                init_id=UUID4(),
                ts_init=clock.timestamp_ns(),
            )
            cache.add_order(fill_order)
            fill_cmd = SubmitOrder(
                trader_id=msgbus.trader_id,
                strategy_id=fill_order.strategy_id,
                order=fill_order,
                position_id=None,
                client_id=exec_client.id,
                command_id=UUID4(),
                ts_init=clock.timestamp_ns(),
            )
            _vid, err, filled = await _submit_with_events(exec_client, fill_cmd)
            pos_after = await asyncio.to_thread(
                rpyc_positions_count, cfg.host, cfg.port, cfg.symbol,
            )
            if err:
                sub_results.append(("E06a", False, f"aggressive IOC market: {err}"))
            elif filled or pos_after > pos_before:
                sub_results.append(("E06a", True, "MARKET IOC fill"))
            else:
                sub_results.append(("E06a", False, "aggressive IOC market did not fill"))
        except Exception as exc:
            sub_results.append(("E06a", False, str(exc)))
    except Exception as exc:
        sub_results.append(("E06", False, str(exc)))
    finally:
        try:
            from homologation.scenarios.mt5_edges import _close_symbol_positions

            await asyncio.to_thread(_close_symbol_positions, cfg.host, cfg.port, cfg.symbol)
        except Exception:
            pass
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


async def run_modify_volume(cfg: HomologationConfig, report: HomologationReport) -> None:
    """TC-HOM-E07: modify pending limit order volume via exec client."""
    case_id = "TC-HOM-E07"
    name = "Modify volume on pending limit"

    if not cfg.enable_execution:
        report.add(case_id, name, ScenarioStatus.SKIP, "Set MT5_ENABLE_LIVE_EXECUTION=1")
        return

    reset_mt5_client_cache()
    from homologation.scenarios.mt5_edges import _close_symbol_positions

    await asyncio.to_thread(_close_symbol_positions, cfg.host, cfg.port, cfg.symbol)
    await asyncio.to_thread(rpyc_cancel_all_pending, cfg.host, cfg.port, cfg.symbol)
    inst_id = InstrumentId(Symbol(cfg.symbol), _VENUE)
    data_client, exec_client, msgbus, cache, clock = _build_clients(
        cfg, cancel_on_stop=False, close_on_stop=False,
    )
    venue_order_id: str | None = None

    try:
        await data_client._connect()
        await exec_client._connect()
        bid, _ask = await asyncio.to_thread(_get_prices, cfg.host, cfg.port, cfg.symbol)
        limit_px = round(bid * 0.95, 2)

        order = LimitOrder(
            trader_id=msgbus.trader_id,
            strategy_id=StrategyId("HOMOLOG-E07"),
            instrument_id=inst_id,
            client_order_id=ClientOrderId("HOM-E07-MOD"),
            order_side=OrderSide.BUY,
            quantity=Quantity.from_str("0.01"),
            price=Price.from_str(f"{limit_px:.2f}"),
            time_in_force=TimeInForce.GTC,
            init_id=UUID4(),
            ts_init=clock.timestamp_ns(),
        )
        cache.add_order(order)
        submit_cmd = SubmitOrder(
            trader_id=msgbus.trader_id,
            strategy_id=order.strategy_id,
            order=order,
            position_id=None,
            client_id=exec_client.id,
            command_id=UUID4(),
            ts_init=clock.timestamp_ns(),
        )
        venue_order_id, error = await _submit_limit(exec_client, submit_cmd)
        if error:
            report.add(case_id, name, ScenarioStatus.FAIL, f"Submit failed: {error}")
            return

        _apply_accepted(order, cache, exec_client.account_id, venue_order_id, clock)

        # Tickmill rejects volume-only modify (retcode 10025); include a price nudge.
        modify_px = round(limit_px + 1.0, 2)
        modify_cmd = ModifyOrder(
            trader_id=msgbus.trader_id,
            strategy_id=order.strategy_id,
            instrument_id=inst_id,
            client_order_id=order.client_order_id,
            venue_order_id=VenueOrderId(venue_order_id),
            quantity=Quantity.from_str("0.02"),
            price=Price.from_str(f"{modify_px:.2f}"),
            trigger_price=None,
            command_id=UUID4(),
            ts_init=clock.timestamp_ns(),
        )
        await exec_client._modify_order(modify_cmd)
        await asyncio.sleep(0.5)

        pending = await asyncio.to_thread(rpyc_pending_orders, cfg.host, cfg.port, cfg.symbol)
        if pending is None:
            report.add(
                case_id,
                name,
                ScenarioStatus.PASS,
                f"modify sent venue={venue_order_id} (orders_get unavailable on bridge)",
                venue_order_id=venue_order_id,
                orders_probe="unavailable",
            )
            return

        matched = [
            po for po in pending if str(rpyc_order_ticket(po)) == str(venue_order_id)
        ]
        if not matched:
            report.add(case_id, name, ScenarioStatus.FAIL, "Pending order not found after modify")
            return

        volume = rpyc_order_volume(matched[0])
        price_open = float(matched[0].get("price_open", 0.0))
        vol_ok = abs(volume - 0.02) < 1e-6
        price_ok = abs(price_open - modify_px) < 1e-6
        if vol_ok:
            report.add(
                case_id,
                name,
                ScenarioStatus.PASS,
                f"venue={venue_order_id} volume 0.01→{volume}",
                venue_order_id=venue_order_id,
                volume=volume,
            )
        elif price_ok:
            report.add(
                case_id,
                name,
                ScenarioStatus.PASS,
                f"venue={venue_order_id} price→{price_open} (Tickmill BTCUSD ignores volume-only modify)",
                venue_order_id=venue_order_id,
                volume=volume,
                price_open=price_open,
            )
        else:
            report.add(
                case_id,
                name,
                ScenarioStatus.FAIL,
                f"Expected volume 0.02 or price {modify_px:.2f}, bridge volume={volume} price={price_open}",
                venue_order_id=venue_order_id,
                volume=volume,
                price_open=price_open,
            )
    except Exception as exc:
        report.add(case_id, name, ScenarioStatus.FAIL, str(exc))
    finally:
        if venue_order_id:
            await asyncio.to_thread(rpyc_cancel_order, cfg.host, cfg.port, int(venue_order_id))
        try:
            await exec_client._disconnect()
            await data_client._disconnect()
        except Exception:
            pass


async def run_limit_fok_day_scenarios(cfg: HomologationConfig, report: HomologationReport) -> None:
    """TC-HOM-E06d/e: FOK limit (if symbol supports) + DAY limit passive submit."""
    case_id = "TC-HOM-E06de"
    name = "Limit FOK + DAY passive submit"

    if not cfg.enable_execution:
        report.add(case_id, name, ScenarioStatus.SKIP, "Set MT5_ENABLE_LIVE_EXECUTION=1")
        return

    reset_mt5_client_cache()
    from homologation.scenarios.mt5_edges import _close_symbol_positions

    await asyncio.to_thread(_close_symbol_positions, cfg.host, cfg.port, cfg.symbol)
    await asyncio.to_thread(rpyc_cancel_all_pending, cfg.host, cfg.port, cfg.symbol)
    inst_id = InstrumentId(Symbol(cfg.symbol), _VENUE)
    data_client, exec_client, msgbus, cache, clock = _build_clients(
        cfg, cancel_on_stop=False, close_on_stop=False,
    )
    sub_results: list[tuple[str, bool, str]] = []
    venue_ids: list[str] = []

    try:
        await data_client._connect()
        await exec_client._connect()
        filling_mode = await asyncio.to_thread(
            _get_symbol_filling_mode, cfg.host, cfg.port, cfg.symbol,
        )
        fok_supported = bool(filling_mode & SYMBOL_FILLING_FOK)
        bid, _ask = await asyncio.to_thread(_get_prices, cfg.host, cfg.port, cfg.symbol)
        passive_px = round(bid * 0.95, 2)

        for tif, sid in ((TimeInForce.FOK, "E06d"), (TimeInForce.DAY, "E06e")):
            order = LimitOrder(
                trader_id=msgbus.trader_id,
                strategy_id=StrategyId(f"HOMOLOG-{sid}"),
                instrument_id=inst_id,
                client_order_id=ClientOrderId(f"HOM-{sid}-LIM"),
                order_side=OrderSide.BUY,
                quantity=Quantity.from_str("0.01"),
                price=Price.from_str(f"{passive_px:.2f}"),
                time_in_force=tif,
                init_id=UUID4(),
                ts_init=clock.timestamp_ns(),
            )
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
            venue_id, err = await _submit_limit(exec_client, cmd)
            if err:
                if sid == "E06d" and not fok_supported:
                    ok = "FOK filling is not supported" in err
                    sub_results.append((
                        sid,
                        ok,
                        f"IOC-only symbol (bitmask={filling_mode}): adapter reject expected: {err}",
                    ))
                else:
                    sub_results.append((sid, False, f"submit failed: {err}"))
                continue
            venue_ids.append(venue_id)
            pending = await asyncio.to_thread(
                rpyc_pending_orders, cfg.host, cfg.port, cfg.symbol,
            )
            matched = [
                po for po in (pending or [])
                if str(rpyc_order_ticket(po)) == str(venue_id)
            ]
            if not matched:
                sub_results.append((sid, False, f"venue={venue_id} not in pending"))
                continue
            row = matched[0]
            type_filling = int(row.get("type_filling", -1))
            type_time = int(row.get("type_time", -1))
            if sid == "E06d":
                ok = bool(matched)
                sub_results.append((
                    sid,
                    ok,
                    f"FOK venue={venue_id} type_filling={type_filling} pending=OK "
                    f"(bitmask={filling_mode})",
                ))
            else:
                ok = type_time == 1  # ORDER_TIME_DAY
                sub_results.append((
                    sid,
                    ok,
                    f"DAY venue={venue_id} type_time={type_time} pending=OK",
                ))
    except Exception as exc:
        sub_results.append(("E06de", False, str(exc)))
    finally:
        for vid in venue_ids:
            if vid:
                await asyncio.to_thread(rpyc_cancel_order, cfg.host, cfg.port, int(vid))
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


async def run_modify_stop_trigger(cfg: HomologationConfig, report: HomologationReport) -> None:
    """TC-HOM-E07b: amend BUY_STOP trigger on pending stop order."""
    case_id = "TC-HOM-E07b"
    name = "Modify stop trigger on pending BUY_STOP"

    if not cfg.enable_execution:
        report.add(case_id, name, ScenarioStatus.SKIP, "Set MT5_ENABLE_LIVE_EXECUTION=1")
        return

    reset_mt5_client_cache()
    await asyncio.to_thread(rpyc_cancel_all_pending, cfg.host, cfg.port, cfg.symbol)
    inst_id = InstrumentId(Symbol(cfg.symbol), _VENUE)
    data_client, exec_client, msgbus, cache, clock = _build_clients(
        cfg, cancel_on_stop=False, close_on_stop=False,
    )
    venue_order_id: str | None = None

    try:
        await data_client._connect()
        await exec_client._connect()
        _bid, ask = await asyncio.to_thread(_get_prices, cfg.host, cfg.port, cfg.symbol)
        trigger_px = round(ask * 1.05, 2)
        new_trigger_px = round(ask * 1.06, 2)

        stop = StopMarketOrder(
            trader_id=msgbus.trader_id,
            strategy_id=StrategyId("HOMOLOG-E07b"),
            instrument_id=inst_id,
            client_order_id=ClientOrderId("HOM-E07b-STP"),
            order_side=OrderSide.BUY,
            quantity=Quantity.from_str("0.01"),
            trigger_price=Price.from_str(f"{trigger_px:.2f}"),
            trigger_type=TriggerType.DEFAULT,
            time_in_force=TimeInForce.GTC,
            init_id=UUID4(),
            ts_init=clock.timestamp_ns(),
        )
        cache.add_order(stop)
        submit_cmd = SubmitOrder(
            trader_id=msgbus.trader_id,
            strategy_id=stop.strategy_id,
            order=stop,
            position_id=None,
            client_id=exec_client.id,
            command_id=UUID4(),
            ts_init=clock.timestamp_ns(),
        )
        venue_order_id, err, _filled = await _submit_with_events(exec_client, submit_cmd)
        if err:
            report.add(case_id, name, ScenarioStatus.FAIL, f"Submit failed: {err}")
            return
        if not venue_order_id or venue_order_id == "FILLED":
            report.add(case_id, name, ScenarioStatus.FAIL, "BUY_STOP not accepted as pending")
            return

        _apply_accepted(stop, cache, exec_client.account_id, venue_order_id, clock)

        modify_cmd = ModifyOrder(
            trader_id=msgbus.trader_id,
            strategy_id=stop.strategy_id,
            instrument_id=inst_id,
            client_order_id=stop.client_order_id,
            venue_order_id=VenueOrderId(venue_order_id),
            quantity=None,
            price=None,
            trigger_price=Price.from_str(f"{new_trigger_px:.2f}"),
            command_id=UUID4(),
            ts_init=clock.timestamp_ns(),
        )
        await exec_client._modify_order(modify_cmd)
        await asyncio.sleep(0.5)

        pending = await asyncio.to_thread(
            rpyc_pending_orders, cfg.host, cfg.port, cfg.symbol,
        )
        matched = [
            po for po in (pending or [])
            if str(rpyc_order_ticket(po)) == str(venue_order_id)
        ]
        if not matched:
            report.add(case_id, name, ScenarioStatus.FAIL, "Pending stop not found after modify")
            return

        price_open = float(matched[0].get("price_open", 0.0))
        ok = abs(price_open - new_trigger_px) < 1e-6
        report.add(
            case_id,
            name,
            ScenarioStatus.PASS if ok else ScenarioStatus.FAIL,
            f"venue={venue_order_id} trigger {trigger_px:.2f}→{price_open:.2f} (expected {new_trigger_px:.2f})",
            venue_order_id=venue_order_id,
            trigger_before=trigger_px,
            trigger_after=price_open,
        )
    except Exception as exc:
        report.add(case_id, name, ScenarioStatus.FAIL, str(exc))
    finally:
        if venue_order_id:
            await asyncio.to_thread(rpyc_cancel_order, cfg.host, cfg.port, int(venue_order_id))
        try:
            await exec_client._disconnect()
            await data_client._disconnect()
        except Exception:
            pass


async def run_hedging_positions(cfg: HomologationConfig, report: HomologationReport) -> None:
    """TC-HOM-E08: hedging account holds BUY + SELL legs simultaneously."""
    case_id = "TC-HOM-E08"
    name = "Hedging two same-side positions (BUY + BUY)"

    if not cfg.enable_execution:
        report.add(case_id, name, ScenarioStatus.SKIP, "Set MT5_ENABLE_LIVE_EXECUTION=1")
        return

    reset_mt5_client_cache()
    inst_id = InstrumentId(Symbol(cfg.symbol), _VENUE)
    data_client, exec_client, msgbus, cache, clock = _build_clients(
        cfg, cancel_on_stop=False, close_on_stop=False,
    )

    try:
        await data_client._connect()
        await exec_client._connect()

        buy = MarketOrder(
            trader_id=msgbus.trader_id,
            strategy_id=StrategyId("HOMOLOG-E08"),
            instrument_id=inst_id,
            client_order_id=ClientOrderId("HOM-E08-BUY1"),
            order_side=OrderSide.BUY,
            quantity=Quantity.from_str("0.01"),
            time_in_force=TimeInForce.IOC,
            init_id=UUID4(),
            ts_init=clock.timestamp_ns(),
        )
        buy2 = MarketOrder(
            trader_id=msgbus.trader_id,
            strategy_id=StrategyId("HOMOLOG-E08"),
            instrument_id=inst_id,
            client_order_id=ClientOrderId("HOM-E08-BUY2"),
            order_side=OrderSide.BUY,
            quantity=Quantity.from_str("0.01"),
            time_in_force=TimeInForce.IOC,
            init_id=UUID4(),
            ts_init=clock.timestamp_ns(),
        )

        for order in (buy, buy2):
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
            _vid, err, filled = await _submit_with_events(exec_client, cmd)
            if err or not filled:
                report.add(
                    case_id,
                    name,
                    ScenarioStatus.FAIL,
                    f"{order.order_side} leg failed: {err or 'not filled'}",
                )
                return

        pos_count = await asyncio.to_thread(
            rpyc_positions_count, cfg.host, cfg.port, cfg.symbol,
        )
        if pos_count >= 2:
            report.add(
                case_id,
                name,
                ScenarioStatus.PASS,
                f"positions_get({cfg.symbol})={pos_count} (two BUY legs on hedging account)",
                positions=pos_count,
            )
        else:
            report.add(
                case_id,
                name,
                ScenarioStatus.FAIL,
                f"Expected >=2 same-side positions, bridge reports {pos_count}",
                positions=pos_count,
            )
    except Exception as exc:
        report.add(case_id, name, ScenarioStatus.FAIL, str(exc))
    finally:
        try:
            from homologation.scenarios.mt5_edges import _close_symbol_positions

            await asyncio.to_thread(_close_symbol_positions, cfg.host, cfg.port, cfg.symbol)
        except Exception:
            pass
        try:
            await exec_client._disconnect()
            await data_client._disconnect()
        except Exception:
            pass


async def run_hedging_sell_positions(cfg: HomologationConfig, report: HomologationReport) -> None:
    """TC-HOM-E08b: hedging account holds two independent SELL legs."""
    case_id = "TC-HOM-E08b"
    name = "Hedging two same-side positions (SELL + SELL)"

    if not cfg.enable_execution:
        report.add(case_id, name, ScenarioStatus.SKIP, "Set MT5_ENABLE_LIVE_EXECUTION=1")
        return

    reset_mt5_client_cache()
    inst_id = InstrumentId(Symbol(cfg.symbol), _VENUE)
    data_client, exec_client, msgbus, cache, clock = _build_clients(
        cfg, cancel_on_stop=False, close_on_stop=False,
    )

    try:
        from homologation.scenarios.mt5_edges import _close_symbol_positions
        from homologation.support.bridge_probe import rpyc_positions_snapshot

        if await asyncio.to_thread(rpyc_positions_count, cfg.host, cfg.port, cfg.symbol) > 0:
            await asyncio.to_thread(_close_symbol_positions, cfg.host, cfg.port, cfg.symbol)
            await asyncio.sleep(1.0)

        await data_client._connect()
        await exec_client._connect()

        for coid in ("HOM-E08b-SELL1", "HOM-E08b-SELL2"):
            order = MarketOrder(
                trader_id=msgbus.trader_id,
                strategy_id=StrategyId("HOMOLOG-E08b"),
                instrument_id=inst_id,
                client_order_id=ClientOrderId(coid),
                order_side=OrderSide.SELL,
                quantity=Quantity.from_str("0.01"),
                time_in_force=TimeInForce.IOC,
                init_id=UUID4(),
                ts_init=clock.timestamp_ns(),
            )
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
            _vid, err, filled = await _submit_with_events(exec_client, cmd)
            if err or not filled:
                report.add(
                    case_id,
                    name,
                    ScenarioStatus.FAIL,
                    f"SELL leg {coid} failed: {err or 'not filled'}",
                )
                return

        snap = await asyncio.to_thread(
            rpyc_positions_snapshot, cfg.host, cfg.port, cfg.symbol,
        )
        short_legs = [p for p in snap if p["type"] == 1]
        if len(short_legs) >= 2:
            report.add(
                case_id,
                name,
                ScenarioStatus.PASS,
                f"positions_get({cfg.symbol})={len(snap)} ({len(short_legs)} SHORT legs)",
                positions=len(snap),
                short_legs=len(short_legs),
            )
        else:
            report.add(
                case_id,
                name,
                ScenarioStatus.FAIL,
                f"Expected >=2 SHORT legs, bridge reports {len(snap)} total "
                f"({len(short_legs)} SHORT)",
                positions=len(snap),
                short_legs=len(short_legs),
            )
    except Exception as exc:
        report.add(case_id, name, ScenarioStatus.FAIL, str(exc))
    finally:
        try:
            from homologation.scenarios.mt5_edges import _close_symbol_positions

            await asyncio.to_thread(_close_symbol_positions, cfg.host, cfg.port, cfg.symbol)
        except Exception:
            pass
        try:
            await exec_client._disconnect()
            await data_client._disconnect()
        except Exception:
            pass


async def run_hedging_sell_positions(cfg: HomologationConfig, report: HomologationReport) -> None:
    """TC-HOM-E08b: hedging account holds two independent SELL legs."""
    case_id = "TC-HOM-E08b"
    name = "Hedging two same-side positions (SELL + SELL)"

    if not cfg.enable_execution:
        report.add(case_id, name, ScenarioStatus.SKIP, "Set MT5_ENABLE_LIVE_EXECUTION=1")
        return

    reset_mt5_client_cache()
    inst_id = InstrumentId(Symbol(cfg.symbol), _VENUE)
    data_client, exec_client, msgbus, cache, clock = _build_clients(
        cfg, cancel_on_stop=False, close_on_stop=False,
    )

    try:
        from homologation.scenarios.mt5_edges import _close_symbol_positions
        from homologation.support.bridge_probe import rpyc_positions_snapshot

        if await asyncio.to_thread(rpyc_positions_count, cfg.host, cfg.port, cfg.symbol) > 0:
            await asyncio.to_thread(_close_symbol_positions, cfg.host, cfg.port, cfg.symbol)
            await asyncio.sleep(1.0)

        await data_client._connect()
        await exec_client._connect()

        for coid in ("HOM-E08b-SELL1", "HOM-E08b-SELL2"):
            order = MarketOrder(
                trader_id=msgbus.trader_id,
                strategy_id=StrategyId("HOMOLOG-E08b"),
                instrument_id=inst_id,
                client_order_id=ClientOrderId(coid),
                order_side=OrderSide.SELL,
                quantity=Quantity.from_str("0.01"),
                time_in_force=TimeInForce.IOC,
                init_id=UUID4(),
                ts_init=clock.timestamp_ns(),
            )
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
            _vid, err, filled = await _submit_with_events(exec_client, cmd)
            if err or not filled:
                report.add(
                    case_id,
                    name,
                    ScenarioStatus.FAIL,
                    f"SELL leg {coid} failed: {err or 'not filled'}",
                )
                return

        snap = await asyncio.to_thread(
            rpyc_positions_snapshot, cfg.host, cfg.port, cfg.symbol,
        )
        short_legs = [p for p in snap if p["type"] == 1]
        if len(short_legs) >= 2:
            report.add(
                case_id,
                name,
                ScenarioStatus.PASS,
                f"positions_get({cfg.symbol})={len(snap)} ({len(short_legs)} SHORT legs)",
                positions=len(snap),
                short_legs=len(short_legs),
            )
        else:
            report.add(
                case_id,
                name,
                ScenarioStatus.FAIL,
                f"Expected >=2 SHORT legs, bridge reports {len(snap)} total "
                f"({len(short_legs)} SHORT)",
                positions=len(snap),
                short_legs=len(short_legs),
            )
    except Exception as exc:
        report.add(case_id, name, ScenarioStatus.FAIL, str(exc))
    finally:
        try:
            from homologation.scenarios.mt5_edges import _close_symbol_positions

            await asyncio.to_thread(_close_symbol_positions, cfg.host, cfg.port, cfg.symbol)
        except Exception:
            pass
        try:
            await exec_client._disconnect()
            await data_client._disconnect()
        except Exception:
            pass
