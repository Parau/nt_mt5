"""Confirm QuoteTick + TradeTick (live D02/D30 + hist D21/D31) per AMP symbol."""
from __future__ import annotations

import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from homologation.config import HomologationConfig
from homologation.report import HomologationReport
from homologation.scenarios.closed_market_suite import run_request_quote_ticks_e2e
from homologation.scenarios.preflight import run_preflight
from homologation.scenarios.tick_stream import run_tick_stream
from homologation.scenarios.trade_tick_open_market import (
    run_request_trade_ticks_open,
    run_trade_tick_stream,
)
from homologation.support.clients import reset_mt5_client_cache


def _symbols() -> tuple[str, ...]:
    raw = os.environ.get(
        "HOMOLOG_CONFIRM_SYMBOLS",
        "MESU26,MNQU26,ENQU26",
    ).strip()
    return tuple(s.strip() for s in raw.split(",") if s.strip())


async def _run_symbol(sym: str, report: HomologationReport) -> None:
    os.environ["MT5_SYMBOL"] = sym
    os.environ["HOMOLOG_TRADE_SYMBOLS"] = sym
    cfg = HomologationConfig.from_env()

    reset_mt5_client_cache()
    await run_preflight(cfg, report)
    if report.has_failures:
        return

    reset_mt5_client_cache()
    await run_tick_stream(cfg, report)

    reset_mt5_client_cache()
    await run_request_quote_ticks_e2e(cfg, report)

    reset_mt5_client_cache()
    await run_trade_tick_stream(cfg, report)

    reset_mt5_client_cache()
    await run_request_trade_ticks_open(cfg, report)


async def main() -> int:
    symbols = _symbols()
    report = HomologationReport()

    print("=" * 64)
    print("  AMP/CME — Quote + Trade tick confirm (D02/D21/D30/D31)")
    print(f"  Symbols : {','.join(symbols)}")
    print(f"  Gateway : {os.environ.get('MT5_HOST', '127.0.0.1')}:{os.environ.get('MT5_PORT', '18814')}")
    print("=" * 64)

    for sym in symbols:
        await _run_symbol(sym, report)

    report.print_summary()
    path = os.environ.get(
        "HOMOLOG_REPORT_JSON",
        "homologation/last_amp_symbol_confirm_report.json",
    )
    report.write_json(path)
    print(f"  JSON report written to {path}")
    return 0 if report.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
