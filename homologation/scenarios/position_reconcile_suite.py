"""
TC-HOM-E10 / E10b / E10c / E10d: hedging position books and lifecycle.

E10  — 2× BUY + 1× SELL; ``generate_mass_status`` vs bridge.
E10b — ``close_on_stop`` clears two same-side BUY legs.
E10c — minimal mixed book: flat → SELL (short) → BUY (long); 1L + 1S.
E10d — ``close_on_stop`` clears a mixed L+S book (1L + 1S).
"""
from __future__ import annotations

import asyncio

from nautilus_trader.core.uuid import UUID4
from nautilus_trader.execution.messages import SubmitOrder
from nautilus_trader.model.enums import OrderSide, PositionSide, TimeInForce
from nautilus_trader.model.identifiers import (
    ClientOrderId,
    InstrumentId,
    StrategyId,
    Symbol,
    Venue,
)
from nautilus_trader.model.objects import Quantity
from nautilus_trader.model.orders import MarketOrder

from homologation.config import HomologationConfig
from homologation.report import HomologationReport, ScenarioStatus
from homologation.scenarios.exec_tester_suite import _submit_with_events
from homologation.scenarios.mt5_edges import _close_symbol_positions, _exec_stack
from homologation.support.bridge_probe import (
    rpyc_positions_count,
    rpyc_positions_volume_summary,
)
from homologation.support.clients import reset_mt5_client_cache

_VENUE = Venue("METATRADER_5")
_QTY = "0.01"


async def _flat_symbol(cfg: HomologationConfig) -> tuple[bool, str]:
    await asyncio.to_thread(_close_symbol_positions, cfg.host, cfg.port, cfg.symbol)
    await asyncio.sleep(1.0)
    remaining = await asyncio.to_thread(rpyc_positions_count, cfg.host, cfg.port, cfg.symbol)
    if remaining == 0:
        return True, "flat"
    return False, f"positions_get({cfg.symbol})={remaining} after cleanup"


async def _market_ioc(
    exec_client,
    cache,
    msgbus,
    clock,
    inst_id: InstrumentId,
    side: OrderSide,
    client_order_id: str,
    *,
    strategy_tag: str = "HOMOLOG-E10",
) -> tuple[bool, str]:
    order = MarketOrder(
        trader_id=msgbus.trader_id,
        strategy_id=StrategyId(strategy_tag),
        instrument_id=inst_id,
        client_order_id=ClientOrderId(client_order_id),
        order_side=side,
        quantity=Quantity.from_str(_QTY),
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
    if err:
        return False, f"{side} failed: {err}"
    if not filled:
        return False, f"{side} not filled"
    return True, "ok"


def _report_volumes(mass_position_reports, inst_id: InstrumentId) -> tuple[int, float, float]:
    reports = mass_position_reports.get(inst_id, [])
    long_vol = 0.0
    short_vol = 0.0
    count = 0
    for rep in reports:
        count += 1
        vol = float(rep.quantity.as_double())
        if rep.position_side == PositionSide.LONG:
            long_vol += vol
        elif rep.position_side == PositionSide.SHORT:
            short_vol += vol
    return count, long_vol, short_vol


async def run_position_reconcile(cfg: HomologationConfig, report: HomologationReport) -> None:
    """TC-HOM-E10: multi-leg mass_status vs bridge positions."""
    case_id = "TC-HOM-E10"
    name = "Multi-leg position reconcile (mass_status vs bridge)"

    if not cfg.enable_execution:
        report.add(case_id, name, ScenarioStatus.SKIP, "Set MT5_ENABLE_LIVE_EXECUTION=1")
        return

    reset_mt5_client_cache()
    inst_id = InstrumentId(Symbol(cfg.symbol), _VENUE)
    data_client, exec_client, msgbus, cache, clock = _exec_stack(
        cfg, 7, cancel_on_stop=False, close_on_stop=False,
    )

    try:
        flat, flat_detail = await _flat_symbol(cfg)
        if not flat:
            report.add(case_id, name, ScenarioStatus.FAIL, f"Pre-flight not flat: {flat_detail}")
            return

        await data_client._connect()
        await exec_client._connect()

        legs = [
            (OrderSide.BUY, "HOM-E10-BUY1"),
            (OrderSide.BUY, "HOM-E10-BUY2"),
            (OrderSide.SELL, "HOM-E10-SELL1"),
        ]
        for side, coid in legs:
            ok, detail = await _market_ioc(
                exec_client, cache, msgbus, clock, inst_id, side, coid,
            )
            if not ok:
                report.add(case_id, name, ScenarioStatus.FAIL, detail)
                return

        bridge_count, bridge_long, bridge_short = await asyncio.to_thread(
            rpyc_positions_volume_summary, cfg.host, cfg.port, cfg.symbol,
        )
        mass = await exec_client.generate_mass_status(lookback_mins=60)
        if mass is None:
            report.add(case_id, name, ScenarioStatus.FAIL, "generate_mass_status returned None")
            return

        rep_count, rep_long, rep_short = _report_volumes(mass.position_reports, inst_id)

        count_ok = bridge_count == rep_count == 3
        long_ok = abs(bridge_long - rep_long) < 1e-6 and abs(bridge_long - 0.02) < 1e-6
        short_ok = abs(bridge_short - rep_short) < 1e-6 and abs(bridge_short - 0.01) < 1e-6

        if count_ok and long_ok and short_ok:
            report.add(
                case_id,
                name,
                ScenarioStatus.PASS,
                (
                    f"bridge={bridge_count} L={bridge_long} S={bridge_short} "
                    f"reports={rep_count} L={rep_long} S={rep_short}"
                ),
                bridge_count=bridge_count,
                report_count=rep_count,
            )
        else:
            report.add(
                case_id,
                name,
                ScenarioStatus.FAIL,
                (
                    f"bridge={bridge_count} L={bridge_long} S={bridge_short} "
                    f"reports={rep_count} L={rep_long} S={rep_short}"
                ),
                bridge_count=bridge_count,
                report_count=rep_count,
            )
    except Exception as exc:
        report.add(case_id, name, ScenarioStatus.FAIL, str(exc))
    finally:
        await asyncio.to_thread(_close_symbol_positions, cfg.host, cfg.port, cfg.symbol)
        try:
            await exec_client._disconnect()
            await data_client._disconnect()
        except Exception:
            pass


async def run_close_on_stop_multi(cfg: HomologationConfig, report: HomologationReport) -> None:
    """TC-HOM-E10b: close_on_stop with multiple open legs."""
    case_id = "TC-HOM-E10b"
    name = "close_on_stop clears multi-leg book"

    if not cfg.enable_execution:
        report.add(case_id, name, ScenarioStatus.SKIP, "Set MT5_ENABLE_LIVE_EXECUTION=1")
        return

    reset_mt5_client_cache()
    inst_id = InstrumentId(Symbol(cfg.symbol), _VENUE)

    flat, flat_detail = await _flat_symbol(cfg)
    if not flat:
        report.add(case_id, name, ScenarioStatus.FAIL, f"Pre-flight not flat: {flat_detail}")
        return

    data_open, exec_open, msgbus, cache, clock = _exec_stack(
        cfg, 8, cancel_on_stop=False, close_on_stop=False,
    )
    try:
        await data_open._connect()
        await exec_open._connect()
        for coid in ("HOM-E10b-B1", "HOM-E10b-B2"):
            ok, detail = await _market_ioc(
                exec_open, cache, msgbus, clock, inst_id, OrderSide.BUY, coid,
            )
            if not ok:
                report.add(case_id, name, ScenarioStatus.FAIL, detail)
                return
        before = await asyncio.to_thread(rpyc_positions_count, cfg.host, cfg.port, cfg.symbol)
        if before < 2:
            report.add(
                case_id,
                name,
                ScenarioStatus.FAIL,
                f"Expected >=2 legs before close_on_stop, got {before}",
            )
            return
    finally:
        try:
            await exec_open._disconnect()
            await data_open._disconnect()
        except Exception:
            pass

    reset_mt5_client_cache()
    data_close, exec_close, _, _, _ = _exec_stack(
        cfg, 9, cancel_on_stop=False, close_on_stop=True,
    )
    try:
        await data_close._connect()
        await exec_close._connect()
        await exec_close._disconnect()
        await asyncio.sleep(2.0)
        after = await asyncio.to_thread(rpyc_positions_count, cfg.host, cfg.port, cfg.symbol)
        if after == 0:
            report.add(
                case_id,
                name,
                ScenarioStatus.PASS,
                f"positions {before}→{after} via close_on_stop",
                before=before,
                after=after,
            )
        else:
            report.add(
                case_id,
                name,
                ScenarioStatus.FAIL,
                f"close_on_stop left {after} position(s), was {before}",
                before=before,
                after=after,
            )
    except Exception as exc:
        report.add(case_id, name, ScenarioStatus.FAIL, str(exc))
    finally:
        await asyncio.to_thread(_close_symbol_positions, cfg.host, cfg.port, cfg.symbol)
        try:
            await exec_close._disconnect()
            await data_close._disconnect()
        except Exception:
            pass


async def _open_mixed_book_1l1s(
    exec_client,
    cache,
    msgbus,
    clock,
    inst_id: InstrumentId,
    *,
    strategy_tag: str,
    sell_coid: str,
    buy_coid: str,
) -> tuple[bool, str]:
    """Flat → SELL (short) → BUY (long) for a minimal hedging mixed book."""
    ok, detail = await _market_ioc(
        exec_client, cache, msgbus, clock, inst_id, OrderSide.SELL, sell_coid,
        strategy_tag=strategy_tag,
    )
    if not ok:
        return False, detail
    ok, detail = await _market_ioc(
        exec_client, cache, msgbus, clock, inst_id, OrderSide.BUY, buy_coid,
        strategy_tag=strategy_tag,
    )
    if not ok:
        return False, detail
    return True, "ok"


async def run_minimal_mixed_book(cfg: HomologationConfig, report: HomologationReport) -> None:
    """TC-HOM-E10c: flat → SELL → BUY yields independent 1L + 1S legs."""
    case_id = "TC-HOM-E10c"
    name = "Minimal mixed hedging book (1× SELL + 1× BUY)"

    if not cfg.enable_execution:
        report.add(case_id, name, ScenarioStatus.SKIP, "Set MT5_ENABLE_LIVE_EXECUTION=1")
        return

    reset_mt5_client_cache()
    inst_id = InstrumentId(Symbol(cfg.symbol), _VENUE)
    data_client, exec_client, msgbus, cache, clock = _exec_stack(
        cfg, 10, cancel_on_stop=False, close_on_stop=False,
    )

    try:
        flat, flat_detail = await _flat_symbol(cfg)
        if not flat:
            report.add(case_id, name, ScenarioStatus.FAIL, f"Pre-flight not flat: {flat_detail}")
            return

        await data_client._connect()
        await exec_client._connect()

        ok, detail = await _open_mixed_book_1l1s(
            exec_client, cache, msgbus, clock, inst_id,
            strategy_tag="HOMOLOG-E10c",
            sell_coid="HOM-E10c-SELL1",
            buy_coid="HOM-E10c-BUY1",
        )
        if not ok:
            report.add(case_id, name, ScenarioStatus.FAIL, detail)
            return

        bridge_count, bridge_long, bridge_short = await asyncio.to_thread(
            rpyc_positions_volume_summary, cfg.host, cfg.port, cfg.symbol,
        )
        count_ok = bridge_count == 2
        long_ok = abs(bridge_long - 0.01) < 1e-6
        short_ok = abs(bridge_short - 0.01) < 1e-6

        if count_ok and long_ok and short_ok:
            report.add(
                case_id,
                name,
                ScenarioStatus.PASS,
                f"bridge={bridge_count} L={bridge_long} S={bridge_short}",
                bridge_count=bridge_count,
            )
        else:
            report.add(
                case_id,
                name,
                ScenarioStatus.FAIL,
                f"Expected 2 legs L=0.01 S=0.01, got bridge={bridge_count} "
                f"L={bridge_long} S={bridge_short}",
                bridge_count=bridge_count,
            )
    except Exception as exc:
        report.add(case_id, name, ScenarioStatus.FAIL, str(exc))
    finally:
        await asyncio.to_thread(_close_symbol_positions, cfg.host, cfg.port, cfg.symbol)
        try:
            await exec_client._disconnect()
            await data_client._disconnect()
        except Exception:
            pass


async def run_close_on_stop_mixed(cfg: HomologationConfig, report: HomologationReport) -> None:
    """TC-HOM-E10d: close_on_stop clears a mixed 1L + 1S hedging book."""
    case_id = "TC-HOM-E10d"
    name = "close_on_stop clears mixed L+S book"

    if not cfg.enable_execution:
        report.add(case_id, name, ScenarioStatus.SKIP, "Set MT5_ENABLE_LIVE_EXECUTION=1")
        return

    reset_mt5_client_cache()
    inst_id = InstrumentId(Symbol(cfg.symbol), _VENUE)

    flat, flat_detail = await _flat_symbol(cfg)
    if not flat:
        report.add(case_id, name, ScenarioStatus.FAIL, f"Pre-flight not flat: {flat_detail}")
        return

    data_open, exec_open, msgbus, cache, clock = _exec_stack(
        cfg, 11, cancel_on_stop=False, close_on_stop=False,
    )
    try:
        await data_open._connect()
        await exec_open._connect()
        ok, detail = await _open_mixed_book_1l1s(
            exec_open, cache, msgbus, clock, inst_id,
            strategy_tag="HOMOLOG-E10d",
            sell_coid="HOM-E10d-SELL1",
            buy_coid="HOM-E10d-BUY1",
        )
        if not ok:
            report.add(case_id, name, ScenarioStatus.FAIL, detail)
            return

        before_count, before_long, before_short = await asyncio.to_thread(
            rpyc_positions_volume_summary, cfg.host, cfg.port, cfg.symbol,
        )
        if before_count != 2 or before_long < 0.01 or before_short < 0.01:
            report.add(
                case_id,
                name,
                ScenarioStatus.FAIL,
                f"Expected mixed 1L+1S before close, got {before_count} "
                f"L={before_long} S={before_short}",
            )
            return
    finally:
        try:
            await exec_open._disconnect()
            await data_open._disconnect()
        except Exception:
            pass

    reset_mt5_client_cache()
    data_close, exec_close, _, _, _ = _exec_stack(
        cfg, 12, cancel_on_stop=False, close_on_stop=True,
    )
    try:
        await data_close._connect()
        await exec_close._connect()
        await exec_close._disconnect()
        await asyncio.sleep(2.0)
        after = await asyncio.to_thread(rpyc_positions_count, cfg.host, cfg.port, cfg.symbol)
        if after == 0:
            report.add(
                case_id,
                name,
                ScenarioStatus.PASS,
                f"positions {before_count}→{after} via close_on_stop (was L={before_long} S={before_short})",
                before=before_count,
                after=after,
            )
        else:
            report.add(
                case_id,
                name,
                ScenarioStatus.FAIL,
                f"close_on_stop left {after} position(s), was {before_count}",
                before=before_count,
                after=after,
            )
    except Exception as exc:
        report.add(case_id, name, ScenarioStatus.FAIL, str(exc))
    finally:
        await asyncio.to_thread(_close_symbol_positions, cfg.host, cfg.port, cfg.symbol)
        try:
            await exec_close._disconnect()
            await data_close._disconnect()
        except Exception:
            pass
