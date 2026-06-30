"""
run_open_market.py
==================

Focused open-market homologation for Tickmill (or any profile with live ticks).

Covers:
  TC-HOM-PF   Bridge pre-flight
  TC-HOM-D01  Quote ticks via TradingNode
  TC-HOM-E01  Market round-trip (requires MT5_ENABLE_LIVE_EXECUTION=1)
  TC-HOM-D02  Sustained quote tick stream (requires MT5_FEED_ENABLED=1)
  TC-HOM-D03  Live M1 bar subscribe
  TC-HOM-D05  Unsubscribe on stop
  TC-HOM-D21  RequestQuoteTicks Nautilus-level (D21 limit fix)
  TC-HOM-E05  Reconcile orders/positions on reconnect
  TC-HOM-E05b Fill reports after market fill
  TC-HOM-E81  Open-on-start reconcile

Environment variables — same as run_homologation.py; defaults tuned for a
shorter run (60s stream vs 120s).

Usage (Windows CMD)
-------------------
    set MT5_HOST=127.0.0.1
    set MT5_PORT=18812
    set MT5_SYMBOL=BTCUSD
    set MT5_FEED_ENABLED=1
    set MT5_ENABLE_LIVE_EXECUTION=1
    set HOMOLOG_REPORT_JSON=homologation/last_open_market_report.json
    E:\\miniconda\\envs\\trading\\python.exe homologation\\run_open_market.py

Start NT5TickFeedService in MT5 before D02/D03/D05.
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
from homologation.scenarios.closed_market_suite import run_request_quote_ticks_e2e
from homologation.scenarios.data_tester_suite import run_bar_subscribe, run_unsubscribe_on_stop
from homologation.scenarios.mt5_edges import (
    run_fill_reports_after_fill,
    run_open_on_start_reconcile,
    run_reconcile_mass_status,
)
from homologation.scenarios.preflight import run_preflight
from homologation.scenarios.tick_stream import run_tick_stream
from homologation.scenarios.trading_node_suite import run_trading_node_suite
from homologation.support.clients import reset_mt5_client_cache


async def main() -> int:
    cfg = HomologationConfig.from_env()
    report = HomologationReport()

    print("=" * 64)
    print("  MT5 ADAPTER — OPEN MARKET HOMOLOGATION")
    print(f"  Gateway : {cfg.host}:{cfg.port}")
    print(f"  Account : {cfg.account_number}")
    print(f"  Broker  : {cfg.broker}")
    print(f"  Symbol  : {cfg.symbol}")
    print(f"  Profile : {cfg.venue_profile.name}")
    print(f"  Exec    : {'ENABLED' if cfg.enable_execution else 'DISABLED'}")
    print(
        f"  Stream  : {cfg.stream_duration_secs:.0f}s "
        f"({'SKIP' if cfg.skip_stream else 'ENABLED'})"
    )
    print(
        f"  WS feed : {'ENABLED' if cfg.feed_enabled else 'DISABLED'} "
        f"ws://{cfg.feed_host}:{cfg.feed_port}{cfg.feed_path}"
    )
    if cfg.feed_enabled and not cfg.skip_stream:
        print("  Note    : start NT5TickFeedService in MT5 before D02/D03/D05")
    print("=" * 64)

    reset_mt5_client_cache()
    await run_preflight(cfg, report)
    if report.has_failures:
        report.print_summary()
        return 1

    reset_mt5_client_cache()
    await run_trading_node_suite(cfg, report)

    reset_mt5_client_cache()
    await run_tick_stream(cfg, report)

    reset_mt5_client_cache()
    await run_bar_subscribe(cfg, report)

    reset_mt5_client_cache()
    await run_unsubscribe_on_stop(cfg, report)

    reset_mt5_client_cache()
    await run_request_quote_ticks_e2e(cfg, report)

    reset_mt5_client_cache()
    await run_reconcile_mass_status(cfg, report)

    if cfg.enable_execution:
        reset_mt5_client_cache()
        await run_fill_reports_after_fill(cfg, report)

        reset_mt5_client_cache()
        await run_open_on_start_reconcile(cfg, report)

    report.print_summary()

    json_path = os.environ.get("HOMOLOG_REPORT_JSON", "").strip()
    if json_path:
        report.write_json(json_path)
        print(f"  JSON report written to {json_path}")

    return 0 if report.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
