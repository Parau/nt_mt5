"""Run low-priority exec homologation: E06 (incl. E06c) and E07."""
from __future__ import annotations

import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from homologation.config import HomologationConfig
from homologation.report import HomologationReport
from homologation.scenarios.exec_tester_suite import run_limit_ioc_scenarios, run_modify_volume
from homologation.scenarios.preflight import run_preflight
from homologation.support.clients import reset_mt5_client_cache


async def main() -> int:
    cfg = HomologationConfig.from_env()
    report = HomologationReport()
    reset_mt5_client_cache()
    await run_preflight(cfg, report)
    await run_limit_ioc_scenarios(cfg, report)
    reset_mt5_client_cache()
    await run_modify_volume(cfg, report)
    path = os.environ.get("HOMOLOG_REPORT_JSON", "homologation/last_e06_e07_report.json")
    report.write_json(path)
    report.print_summary()
    return 0 if report.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
