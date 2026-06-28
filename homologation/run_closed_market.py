"""
run_closed_market.py
====================

Homologation harness for scenarios that do NOT require an open/live market.

Uses the real MT5 terminal via EXTERNAL_RPYC (no mocks). Safe to run when
BTCUSD/USTEC quotes are frozen (session closed).

Environment variables
---------------------
MT5_HOST, MT5_PORT, MT5_ACCOUNT_NUMBER, MT5_SYMBOL (default BTCUSD),
MT5_BROKER, HOMOLOG_REPORT_JSON

Usage (Windows CMD)
-------------------
    set MT5_HOST=127.0.0.1
    set MT5_PORT=18812
    E:\\miniconda\\envs\\trading\\python.exe homologation\\run_closed_market.py
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


async def main() -> int:
    cfg = HomologationConfig.from_env()
    report = HomologationReport()

    print("=" * 64)
    print("  MT5 ADAPTER — CLOSED-MARKET HOMOLOGATION")
    print(f"  Gateway : {cfg.host}:{cfg.port}")
    print(f"  Account : {cfg.account_number}")
    print(f"  Symbol  : {cfg.symbol}")
    print("  Note    : live tick stream / order fills NOT required")
    print("=" * 64)

    reset_mt5_client_cache()
    await run_closed_market_suite(cfg, report)

    report.print_summary()

    json_path = os.environ.get("HOMOLOG_REPORT_JSON", "homologation/last_closed_market_report.json")
    report.write_json(json_path)
    print(f"  JSON report written to {json_path}")

    return 0 if report.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
