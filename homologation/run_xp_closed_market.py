"""
run_xp_closed_market.py
=======================

XP/B3 closed-market homologation — real MT5 bridge on XPMT5-DEMO.

**Before running:** confirm MT5 is logged into XP (login 56822578), not Tickmill.

Environment variables
---------------------
MT5_HOST, MT5_PORT, MT5_VENUE_PROFILE=xp_b3, MT5_ACCOUNT_NUMBER=56822578,
MT5_SYMBOL (default WDOQ26), MT5_BROKER (default XPMT5-DEMO),
HOMOLOG_MULTI_SYMBOLS, HOMOLOG_REPORT_JSON

Usage (Windows CMD)
-------------------
    set MT5_HOST=127.0.0.1
    set MT5_PORT=18812
    set MT5_VENUE_PROFILE=xp_b3
    set MT5_ACCOUNT_NUMBER=56822578
    set MT5_SYMBOL=WDOQ26
    set HOMOLOG_REPORT_JSON=homologation/last_xp_closed_market_report.json
    E:\\miniconda\\envs\\trading\\python.exe homologation\\run_xp_closed_market.py
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
from homologation.scenarios.xp_closed_market_suite import run_xp_closed_market_suite
from homologation.support.clients import reset_mt5_client_cache


async def main() -> int:
    cfg = HomologationConfig.from_env()
    report = HomologationReport()

    print("=" * 64)
    print("  MT5 ADAPTER — XP/B3 CLOSED-MARKET HOMOLOGATION")
    print(f"  Profile : {cfg.venue_profile.name}")
    print(f"  Gateway : {cfg.host}:{cfg.port}")
    print(f"  Account : {cfg.account_number} (expected XP: 56822578)")
    print(f"  Symbol  : {cfg.symbol}")
    print(f"  Multi   : {','.join(cfg.multi_symbols)}")
    print("  NOTE    : MT5 must be logged into XPMT5-DEMO before running.")
    print("=" * 64)

    reset_mt5_client_cache()
    await run_xp_closed_market_suite(cfg, report)

    report.print_summary()

    json_path = os.environ.get(
        "HOMOLOG_REPORT_JSON",
        "homologation/last_xp_closed_market_report.json",
    )
    report.write_json(json_path)
    print(f"  JSON report written to {json_path}")

    return 0 if report.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
