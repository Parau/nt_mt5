"""Run TC-HOM-E10 / E10b only."""
from __future__ import annotations

import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from homologation.config import HomologationConfig
from homologation.report import HomologationReport
from homologation.scenarios.exec_tester_suite import run_hedging_sell_positions
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
    reset_mt5_client_cache()
    reset_mt5_client_cache()
    await run_hedging_sell_positions(cfg, report)
    reset_mt5_client_cache()
    await run_position_reconcile(cfg, report)
    reset_mt5_client_cache()
    await run_minimal_mixed_book(cfg, report)
    reset_mt5_client_cache()
    await run_close_on_stop_multi(cfg, report)
    reset_mt5_client_cache()
    await run_close_on_stop_mixed(cfg, report)
    report.print_summary()
    return 0 if report.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
