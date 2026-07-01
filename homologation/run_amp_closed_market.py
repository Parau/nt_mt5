"""
run_amp_closed_market.py
========================

AMP / CME closed-market homologation — historical bars, ticks, instrument load.

Container: RPyC ``127.0.0.1:18814`` (no live session required for D04a/D04b).

Scenarios: PF, D04a/b/c, D21, D01-CM, D08/D08b, D10, D02, E-CONN, E-EDGE1.

Usage (Windows CMD)
-------------------
    set MT5_HOST=127.0.0.1
    set MT5_PORT=18814
    set MT5_VENUE_PROFILE=amp_us
    set MT5_ACCOUNT_NUMBER=1588658
    set MT5_SYMBOL=MESU26
    set MT5_BROKER=AMPGlobalUSA-Demo
    set HOMOLOG_REPORT_JSON=homologation/last_amp_closed_market_report.json
    E:\\miniconda\\envs\\trading\\python.exe homologation\\run_amp_closed_market.py
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
from homologation.scenarios.closed_market_suite import run_closed_market_suite
from homologation.support.clients import reset_mt5_client_cache

_AMP_LOGIN = "1588658"


async def main() -> int:
    cfg = HomologationConfig.from_env()
    report = HomologationReport()

    print("=" * 64)
    print("  MT5 ADAPTER — AMP/CME CLOSED-MARKET HOMOLOGATION")
    print(f"  Profile : {cfg.venue_profile.name}")
    print(f"  Gateway : {cfg.host}:{cfg.port}")
    print(f"  Account : {cfg.account_number}  (expected {_AMP_LOGIN})")
    print(f"  Symbol  : {cfg.symbol}")
    print("  Note    : historical bars/ticks; live stream NOT required")
    print("=" * 64)

    reset_mt5_client_cache()
    await run_closed_market_suite(cfg, report)

    report.print_summary()

    json_path = os.environ.get(
        "HOMOLOG_REPORT_JSON",
        "homologation/last_amp_closed_market_report.json",
    )
    report.write_json(json_path)
    print(f"  JSON report written to {json_path}")

    return 0 if report.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
