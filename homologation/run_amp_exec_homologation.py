"""
run_amp_exec_homologation.py
=============================

AMP/CME open-market **execution** homologation (container ``18814``).

Netting account — hedging suites (E08/E08b/E10b/E10c/E10d) are excluded.
Includes netting-specific scenarios E11a/E11b.

Prerequisites: CME trade session open, NT5TickFeedService active,
flat account, ``MT5_ENABLE_LIVE_EXECUTION=1``.

Usage (Windows CMD)
-------------------
    set MT5_HOST=127.0.0.1
    set MT5_PORT=18814
    set MT5_VENUE_PROFILE=amp_us
    set MT5_ACCOUNT_NUMBER=1588658
    set MT5_SYMBOL=MESU26
    set MT5_BROKER=AMPGlobalUSA-Demo
    set MT5_FEED_ENABLED=1
    set MT5_ENABLE_LIVE_EXECUTION=1
    set HOMOLOG_REPORT_JSON=homologation/last_amp_exec_report.json
    E:\\miniconda\\envs\\trading\\python.exe homologation\\run_amp_exec_homologation.py
"""
from __future__ import annotations

import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from homologation.config import HomologationConfig
from homologation.report import HomologationReport, ScenarioStatus
from homologation.scenarios.exec_tester_suite import (
    run_cancel_rejection,
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
from homologation.scenarios.netting_suite import (
    run_netting_partial_close,
    run_netting_position_reconcile,
    run_netting_round_trip,
)
from homologation.scenarios.preflight import run_preflight
from homologation.scenarios.stop_orders import run_stop_orders
from homologation.scenarios.trading_node_suite import run_trading_node_suite
from homologation.support.clients import reset_mt5_client_cache

_AMP_LOGIN = "1588658"


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
    print("  MT5 ADAPTER — AMP/CME EXEC HOMOLOGATION (NETTING)")
    print(f"  Gateway : {cfg.host}:{cfg.port}")
    print(f"  Account : {cfg.account_number}  (expected {_AMP_LOGIN})")
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
        ("e09_retcodes", run_real_retcodes),
        ("e10_reconcile", run_netting_position_reconcile),
        ("e11a_netting_rt", run_netting_round_trip),
        ("e11b_netting_partial", run_netting_partial_close),
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
        "homologation/last_amp_exec_report.json",
    )
    report.write_json(json_path)
    print(f"  JSON report written to {json_path}")

    return 0 if report.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
