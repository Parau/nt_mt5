"""
Run hedging homologation wave: E08b, E10c, E10d (+ optional E08/E10/E10b).

Targets Tickmill-Demo via Docker RPyC gateway (default 127.0.0.1:18812).

Usage (Windows CMD):
    set MT5_HOST=127.0.0.1
    set MT5_PORT=18812
    set MT5_SYMBOL=BTCUSD
    set MT5_ENABLE_LIVE_EXECUTION=1
    set HOMOLOG_REPORT_JSON=homologation/last_hedging_wave_report.json
    E:\\miniconda\\envs\\trading\\python.exe homologation\\run_hedging_wave_homologation.py
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
    run_hedging_positions,
    run_hedging_sell_positions,
)
from homologation.scenarios.position_reconcile_suite import (
    run_close_on_stop_mixed,
    run_close_on_stop_multi,
    run_minimal_mixed_book,
    run_position_reconcile,
)
from homologation.support.clients import reset_mt5_client_cache


async def main() -> int:
    cfg = HomologationConfig.from_env()
    report = HomologationReport()

    print("=" * 64)
    print("  MT5 ADAPTER — HEDGING WAVE HOMOLOGATION")
    print(f"  Gateway : {cfg.host}:{cfg.port}  (Docker Tickmill RPyC)")
    print(f"  Account : {cfg.account_number}")
    print(f"  Symbol  : {cfg.symbol}")
    print(f"  Exec    : {'ENABLED' if cfg.enable_execution else 'DISABLED'}")
    print("=" * 64)

    if not cfg.enable_execution:
        print("ERROR: set MT5_ENABLE_LIVE_EXECUTION=1")
        return 1

    scenarios = (
        ("E08", run_hedging_positions),
        ("E08b", run_hedging_sell_positions),
        ("E10", run_position_reconcile),
        ("E10c", run_minimal_mixed_book),
        ("E10b", run_close_on_stop_multi),
        ("E10d", run_close_on_stop_mixed),
    )

    for label, runner in scenarios:
        print(f"\n--- Running {label} ---")
        reset_mt5_client_cache()
        await runner(cfg, report)

    report.print_summary()

    json_path = os.environ.get("HOMOLOG_REPORT_JSON", "").strip()
    if json_path:
        report.write_json(json_path)
        print(f"  JSON report written to {json_path}")

    return 0 if report.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
