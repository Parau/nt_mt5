"""
run_xp_exec_homologation.py
============================

XP/B3 open-market **execution** homologation (container ``18813``).

Prerequisites: pregão aberto, NT5TickFeedService ativo (para D01/E01),
conta sem posição pendente, ``MT5_ENABLE_LIVE_EXECUTION=1``.

Data/feed scenarios (D02–D07) — use ``run_xp_open_market_feed.py``.

Usage (Windows CMD)
-------------------
    set MT5_HOST=127.0.0.1
    set MT5_PORT=18813
    set MT5_VENUE_PROFILE=xp_b3
    set MT5_ACCOUNT_NUMBER=56822578
    set MT5_SYMBOL=WDON26
    set MT5_BROKER=XPMT5-DEMO
    set MT5_FEED_ENABLED=1
    set MT5_ENABLE_LIVE_EXECUTION=1
    set HOMOLOG_REPORT_JSON=homologation/last_xp_exec_report.json
    E:\\miniconda\\envs\\trading\\python.exe homologation\\run_xp_exec_homologation.py
"""
from __future__ import annotations

import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from homologation.config import HomologationConfig
from homologation.report import HomologationReport
from homologation.scenarios.exec_tester_suite import (
    run_cancel_rejection,
    run_hedging_positions,
    run_hedging_sell_positions,
    run_limit_fok_day_scenarios,
    run_limit_gtc_cancel,
    run_limit_ioc_scenarios,
    run_modify_stop_trigger,
    run_modify_volume,
)
from homologation.scenarios.mt5_edges import (
    run_cancel_close_on_stop,
    run_fill_reports_after_fill,
    run_open_on_start_reconcile,
    run_real_retcodes,
    run_reconcile_mass_status,
)
from homologation.scenarios.position_reconcile_suite import (
    run_close_on_stop_mixed,
    run_close_on_stop_multi,
    run_minimal_mixed_book,
    run_position_reconcile,
)
from homologation.scenarios.preflight import run_preflight
from homologation.scenarios.stop_orders import run_stop_orders
from homologation.scenarios.trading_node_suite import run_trading_node_suite
from homologation.support.clients import reset_mt5_client_cache

_XP_LOGIN = "56822578"


async def main() -> int:
    cfg = HomologationConfig.from_env()
    if not cfg.enable_execution:
        os.environ["MT5_ENABLE_LIVE_EXECUTION"] = "1"
        cfg = HomologationConfig.from_env()
    if cfg.feed_enabled is False and os.environ.get("MT5_FEED_ENABLED", "").strip() != "1":
        os.environ["MT5_FEED_ENABLED"] = "1"
        cfg = HomologationConfig.from_env()

    report = HomologationReport()

    print("=" * 64)
    print("  MT5 ADAPTER — XP/B3 EXEC HOMOLOGATION")
    print(f"  Gateway : {cfg.host}:{cfg.port}")
    print(f"  Account : {cfg.account_number}  (expected {_XP_LOGIN})")
    print(f"  Symbol  : {cfg.symbol}")
    print(f"  Feed    : {'ENABLED' if cfg.feed_enabled else 'DISABLED'}")
    print(f"  Exec    : {'ENABLED' if cfg.enable_execution else 'DISABLED'}")
    print("=" * 64)

    reset_mt5_client_cache()
    await run_preflight(cfg, report)
    if report.has_failures:
        report.print_summary()
        return 1

    steps = [
        ("d01_e01", run_trading_node_suite),
        ("e02_stops", run_stop_orders),
        ("e03_limit", run_limit_gtc_cancel),
        ("e04_cancel_close", run_cancel_close_on_stop),
        ("e05_mass", run_reconcile_mass_status),
        ("e05b_fills", run_fill_reports_after_fill),
        ("e06_ioc", run_limit_ioc_scenarios),
        ("e07_modify", run_modify_volume),
        ("e06de_fok_day", run_limit_fok_day_scenarios),
        ("e07b_stop_trigger", run_modify_stop_trigger),
        ("e08_hedge_buy", run_hedging_positions),
        ("e08b_hedge_sell", run_hedging_sell_positions),
        ("e09_retcodes", run_real_retcodes),
        ("e10_reconcile", run_position_reconcile),
        ("e10b_close_multi", run_close_on_stop_multi),
        ("e10c_mixed_min", run_minimal_mixed_book),
        ("e10d_close_mixed", run_close_on_stop_mixed),
        ("e81_open_reconcile", run_open_on_start_reconcile),
        ("e43_cancel_reject", run_cancel_rejection),
    ]

    for step_name, fn in steps:
        try:
            reset_mt5_client_cache()
            await fn(cfg, report)
        except Exception as exc:
            report.add(
                f"RUNNER-{step_name}",
                fn.__name__,
                ScenarioStatus.FAIL,
                f"Unhandled: {exc}",
            )

    report.print_summary()

    json_path = os.environ.get(
        "HOMOLOG_REPORT_JSON",
        "homologation/last_xp_exec_report.json",
    )
    report.write_json(json_path)
    print(f"  JSON report written to {json_path}")

    return 0 if report.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
