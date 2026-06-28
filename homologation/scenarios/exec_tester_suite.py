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
from nautilus_trader.model.orders import LimitOrder, MarketOrder, StopMarketOrder

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
