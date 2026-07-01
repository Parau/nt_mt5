"""AMP/CME open-market TradeTick homologation — TC-HOM-D30 + TC-HOM-D31."""
from __future__ import annotations

import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from homologation.config import HomologationConfig
from homologation.report import HomologationReport
from homologation.scenarios.preflight import run_preflight
from homologation.scenarios.trade_tick_open_market import (
    run_request_trade_ticks_open,
    run_trade_tick_stream,
)
from homologation.support.clients import reset_mt5_client_cache


async def main() -> int:
    cfg = HomologationConfig.from_env()
    report = HomologationReport()

    print("=" * 64)
    print("  MT5 ADAPTER — AMP/CME TRADE TICK HOMOLOGATION (D30/D31)")
    print(f"  Gateway : {cfg.host}:{cfg.port}")
    print(f"  Profile : {cfg.venue_profile.name}")
    print(f"  Symbols : {os.environ.get('HOMOLOG_TRADE_SYMBOLS', cfg.symbol)}")
    print("=" * 64)

    reset_mt5_client_cache()
    await run_preflight(cfg, report)
    if report.has_failures:
        report.print_summary()
        return 1

    reset_mt5_client_cache()
    await run_trade_tick_stream(cfg, report)
    reset_mt5_client_cache()
    await run_request_trade_ticks_open(cfg, report)

    report.print_summary()
    path = os.environ.get(
        "HOMOLOG_REPORT_JSON",
        "homologation/last_amp_trade_ticks_report.json",
    )
    report.write_json(path)
    print(f"  JSON report written to {path}")
    return 0 if report.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
