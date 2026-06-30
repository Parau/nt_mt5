"""Run TC-HOM-E05b only — fill reports after market fill."""
from __future__ import annotations

import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from homologation.config import HomologationConfig
from homologation.report import HomologationReport
from homologation.scenarios.mt5_edges import run_fill_reports_after_fill
from homologation.support.clients import reset_mt5_client_cache


async def main() -> int:
    cfg = HomologationConfig.from_env()
    report = HomologationReport()

    print("=" * 64)
    print("  TC-HOM-E05b — Fill reports after market fill")
    print(f"  Gateway : {cfg.host}:{cfg.port}")
    print(f"  Symbol  : {cfg.symbol}")
    print(f"  Exec    : {'ENABLED' if cfg.enable_execution else 'DISABLED'}")
    print("=" * 64)

    reset_mt5_client_cache()
    await run_fill_reports_after_fill(cfg, report)
    report.print_summary()

    json_path = os.environ.get("HOMOLOG_REPORT_JSON", "").strip()
    if json_path:
        report.write_json(json_path)
        print(f"  JSON report written to {json_path}")

    return 0 if report.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
