"""
TC-HOM-E11: netting account position lifecycle (AMP / RETAIL_NETTING).

Flat → BUY → partial SELL → full close. Validates that opposite-side
market orders net the single position without hedge position tickets.
"""
from __future__ import annotations

import asyncio

from nautilus_trader.core.uuid import UUID4
from nautilus_trader.execution.messages import SubmitOrder
from nautilus_trader.model.enums import OrderSide, TimeInForce
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
from homologation.scenarios.position_reconcile_suite import _report_volumes
from homologation.support.bridge_probe import (
    rpyc_positions_count,
    rpyc_positions_volume_summary,
)
from homologation.support.clients import reset_mt5_client_cache
from homologation.support.order_specs import homolog_order_qty, homolog_order_qty_str

_VENUE = Venue("METATRADER_5")


def _double_qty_str(cfg: HomologationConfig) -> str:
    base = float(homolog_order_qty_str(cfg))
    return str(int(base * 2)) if base == int(base) else f"{base * 2:g}"


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
    qty: Quantity,
    client_order_id: str,
    *,
    strategy_tag: str = "HOMOLOG-E11",
) -> tuple[bool, str]:
    order = MarketOrder(
        trader_id=msgbus.trader_id,
        strategy_id=StrategyId(strategy_tag),
        instrument_id=inst_id,
        client_order_id=ClientOrderId(client_order_id),
        order_side=side,
        quantity=qty,
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


async def run_netting_round_trip(cfg: HomologationConfig, report: HomologationReport) -> None:
    """TC-HOM-E11a: flat → BUY → SELL → flat on a netting account."""
    case_id = "TC-HOM-E11a"
    name = "Netting round-trip (BUY → SELL → flat)"

    if not cfg.enable_execution:
        report.add(case_id, name, ScenarioStatus.SKIP, "Set MT5_ENABLE_LIVE_EXECUTION=1")
        return

    reset_mt5_client_cache()
    inst_id = InstrumentId(Symbol(cfg.symbol), _VENUE)
    data_client, exec_client, msgbus, cache, clock = _exec_stack(
        cfg, 11, cancel_on_stop=False, close_on_stop=False,
    )

    try:
        ok, detail = await _flat_symbol(cfg)
        if not ok:
            report.add(case_id, name, ScenarioStatus.FAIL, detail)
            return

        await data_client._connect()
        await exec_client._connect()
        qty = homolog_order_qty(cfg)

        ok, detail = await _market_ioc(
            exec_client, cache, msgbus, clock, inst_id,
            OrderSide.BUY, qty, "HOM-E11a-BUY",
        )
        if not ok:
            report.add(case_id, name, ScenarioStatus.FAIL, detail)
            return

        await asyncio.sleep(0.5)
        pos_count = await asyncio.to_thread(rpyc_positions_count, cfg.host, cfg.port, cfg.symbol)
        if pos_count != 1:
            report.add(
                case_id, name, ScenarioStatus.FAIL,
                f"Expected 1 net position after BUY, got {pos_count}",
            )
            return

        ok, detail = await _market_ioc(
            exec_client, cache, msgbus, clock, inst_id,
            OrderSide.SELL, qty, "HOM-E11a-SELL",
        )
        if not ok:
            report.add(case_id, name, ScenarioStatus.FAIL, detail)
            return

        await asyncio.sleep(0.5)
        pos_count = await asyncio.to_thread(rpyc_positions_count, cfg.host, cfg.port, cfg.symbol)
        if pos_count != 0:
            report.add(
                case_id, name, ScenarioStatus.FAIL,
                f"Expected flat after SELL, positions_get={pos_count}",
            )
            return

        report.add(case_id, name, ScenarioStatus.PASS, "BUY → SELL flattened netting position")
    finally:
        await data_client._disconnect()
        await exec_client._disconnect()


async def run_netting_partial_close(cfg: HomologationConfig, report: HomologationReport) -> None:
    """TC-HOM-E11b: BUY 2× min → SELL 1× → SELL 1× on netting account."""
    case_id = "TC-HOM-E11b"
    name = "Netting partial close (BUY 2 → SELL 1 → SELL 1)"

    if not cfg.enable_execution:
        report.add(case_id, name, ScenarioStatus.SKIP, "Set MT5_ENABLE_LIVE_EXECUTION=1")
        return

    reset_mt5_client_cache()
    inst_id = InstrumentId(Symbol(cfg.symbol), _VENUE)
    data_client, exec_client, msgbus, cache, clock = _exec_stack(
        cfg, 13, cancel_on_stop=False, close_on_stop=False,
    )

    try:
        ok, detail = await _flat_symbol(cfg)
        if not ok:
            report.add(case_id, name, ScenarioStatus.FAIL, detail)
            return

        await data_client._connect()
        await exec_client._connect()

        qty_one = homolog_order_qty(cfg)
        qty_two = Quantity.from_str(_double_qty_str(cfg))

        ok, detail = await _market_ioc(
            exec_client, cache, msgbus, clock, inst_id,
            OrderSide.BUY, qty_two, "HOM-E11b-BUY2",
        )
        if not ok:
            report.add(case_id, name, ScenarioStatus.FAIL, detail)
            return

        await asyncio.sleep(0.5)
        _count, long_vol, _short = await asyncio.to_thread(
            rpyc_positions_volume_summary, cfg.host, cfg.port, cfg.symbol,
        )
        expected_two = float(qty_two.as_double())
        if long_vol < expected_two:
            report.add(
                case_id, name, ScenarioStatus.FAIL,
                f"Expected long volume >= {expected_two}, bridge long={long_vol}",
            )
            return

        ok, detail = await _market_ioc(
            exec_client, cache, msgbus, clock, inst_id,
            OrderSide.SELL, qty_one, "HOM-E11b-SELL1",
        )
        if not ok:
            report.add(case_id, name, ScenarioStatus.FAIL, detail)
            return

        await asyncio.sleep(0.5)
        pos_count = await asyncio.to_thread(rpyc_positions_count, cfg.host, cfg.port, cfg.symbol)
        if pos_count != 1:
            report.add(
                case_id, name, ScenarioStatus.FAIL,
                f"Expected 1 position after partial SELL, got {pos_count}",
            )
            return

        ok, detail = await _market_ioc(
            exec_client, cache, msgbus, clock, inst_id,
            OrderSide.SELL, qty_one, "HOM-E11b-SELL2",
        )
        if not ok:
            report.add(case_id, name, ScenarioStatus.FAIL, detail)
            return

        await asyncio.sleep(0.5)
        pos_count = await asyncio.to_thread(rpyc_positions_count, cfg.host, cfg.port, cfg.symbol)
        if pos_count != 0:
            report.add(
                case_id, name, ScenarioStatus.FAIL,
                f"Expected flat after second SELL, positions_get={pos_count}",
            )
            return

        report.add(
            case_id, name, ScenarioStatus.PASS,
            "Partial then full close on single netting position",
        )
    finally:
        await data_client._disconnect()
        await exec_client._disconnect()


async def run_netting_position_reconcile(cfg: HomologationConfig, report: HomologationReport) -> None:
    """TC-HOM-E10: single net position reconcile (mass_status vs bridge) on netting account."""
    case_id = "TC-HOM-E10"
    name = "Netting position reconcile (mass_status vs bridge)"

    if not cfg.enable_execution:
        report.add(case_id, name, ScenarioStatus.SKIP, "Set MT5_ENABLE_LIVE_EXECUTION=1")
        return

    reset_mt5_client_cache()
    inst_id = InstrumentId(Symbol(cfg.symbol), _VENUE)
    data_client, exec_client, msgbus, cache, clock = _exec_stack(
        cfg, 12, cancel_on_stop=False, close_on_stop=False,
    )

    try:
        ok, detail = await _flat_symbol(cfg)
        if not ok:
            report.add(case_id, name, ScenarioStatus.FAIL, f"Pre-flight not flat: {detail}")
            return

        await data_client._connect()
        await exec_client._connect()
        qty = homolog_order_qty(cfg)

        ok, detail = await _market_ioc(
            exec_client, cache, msgbus, clock, inst_id,
            OrderSide.BUY, qty, "HOM-E10n-BUY",
            strategy_tag="HOMOLOG-E10n",
        )
        if not ok:
            report.add(case_id, name, ScenarioStatus.FAIL, detail)
            return

        await asyncio.sleep(0.5)
        bridge_count, bridge_long, bridge_short = await asyncio.to_thread(
            rpyc_positions_volume_summary, cfg.host, cfg.port, cfg.symbol,
        )
        mass = await exec_client.generate_mass_status(lookback_mins=60)
        if mass is None:
            report.add(case_id, name, ScenarioStatus.FAIL, "generate_mass_status returned None")
            return

        rep_count, rep_long, rep_short = _report_volumes(mass.position_reports, inst_id)
        expected = float(qty.as_double())
        count_ok = bridge_count == rep_count == 1
        long_ok = abs(bridge_long - rep_long) < 1e-6 and abs(bridge_long - expected) < 1e-6
        short_ok = bridge_short == 0.0 and rep_short == 0.0

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
        await data_client._disconnect()
        await exec_client._disconnect()
        await _flat_symbol(cfg)
