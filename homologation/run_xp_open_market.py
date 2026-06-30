"""
run_xp_open_market.py
=====================

XP/B3 open-market homologation — real MT5 via Docker ``mt5-xp`` profile.

**Container routing (MT5-Docker):**
  RPyC  : ``127.0.0.1:18813``
  WS    : host ``:8766`` (``MT5_FEED_PORT`` auto-defaults when port=18813)
  VNC   : ``127.0.0.1:5902``

**Before running:**
  - XP container up and logged in (login **56822578**, XPMT5-DEMO)
  - NT5TickFeedService started in XP MT5
  - WS test server on host port **8766** (see MT5-Docker ``run_ws_test_server``)

Covers open-market backlog: D01–D07 (core), D21, E01, E05/E05b/E81, E02 stops.

Usage (Windows CMD)
-------------------
    set MT5_HOST=127.0.0.1
    set MT5_PORT=18813
    set MT5_VENUE_PROFILE=xp_b3
    set MT5_ACCOUNT_NUMBER=56822578
    set MT5_SYMBOL=WDON26
    set MT5_FEED_ENABLED=1
    set MT5_ENABLE_LIVE_EXECUTION=1
    set HOMOLOG_MULTI_SYMBOLS=WDON26,PETR4,WIN$,WINQ26
    set HOMOLOG_STREAM_SECS=60
    set HOMOLOG_REPORT_JSON=homologation/last_xp_open_market_report.json
    E:\\miniconda\\envs\\trading\\python.exe homologation\\run_xp_open_market.py
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
from homologation.scenarios.feed_resilience import run_feed_service_restart_dedup
from homologation.scenarios.mt5_edges import (
    run_fill_reports_after_fill,
    run_open_on_start_reconcile,
    run_reconcile_mass_status,
)
from homologation.scenarios.multi_symbol import run_multi_symbol_stream
from homologation.scenarios.preflight import run_preflight
from homologation.scenarios.stop_orders import run_stop_orders
from homologation.scenarios.tick_stream import run_tick_stream
from homologation.scenarios.trading_node_suite import run_trading_node_suite
from homologation.support.clients import reset_mt5_client_cache

_XP_LOGIN = "56822578"


async def main() -> int:
    cfg = HomologationConfig.from_env()
    report = HomologationReport()

    print("=" * 64)
    print("  MT5 ADAPTER — XP/B3 OPEN MARKET HOMOLOGATION")
    print(f"  Profile : {cfg.venue_profile.name}")
    print(f"  Gateway : {cfg.host}:{cfg.port}  (Docker xp → 18813)")
    print(f"  Account : {cfg.account_number}  (expected XP: {_XP_LOGIN})")
    print(f"  Broker  : {cfg.broker}")
    print(f"  Symbol  : {cfg.symbol}")
    print(f"  Multi   : {','.join(cfg.multi_symbols)}")
    print(f"  Exec    : {'ENABLED' if cfg.enable_execution else 'DISABLED'}")
    print(
        f"  Stream  : {cfg.stream_duration_secs:.0f}s "
        f"({'SKIP' if cfg.skip_stream else 'ENABLED'})"
    )
    print(
        f"  WS feed : {'ENABLED' if cfg.feed_enabled else 'DISABLED'} "
        f"ws://{cfg.feed_host}:{cfg.feed_port}{cfg.feed_path}"
    )
    if cfg.account_number != _XP_LOGIN:
        print(f"  WARNING : account is not XP demo {_XP_LOGIN} — wrong container?")
    if cfg.port == 18812:
        print("  WARNING : port 18812 is Tickmill Docker — use 18813 for XP")
    if cfg.feed_enabled:
        print("  Note    : NT5TickFeedService (XP) + WS server on :8766")
    print("=" * 64)

    reset_mt5_client_cache()
    await run_preflight(cfg, report)
    if report.has_failures:
        report.print_summary()
        return 1

    steps = [
        ("trading_node", run_trading_node_suite),
        ("tick_stream", run_tick_stream),
        ("multi_symbol", run_multi_symbol_stream),
        ("feed_resilience", run_feed_service_restart_dedup),
        ("bar_subscribe", run_bar_subscribe),
        ("unsubscribe", run_unsubscribe_on_stop),
        ("d21", run_request_quote_ticks_e2e),
        ("reconcile", run_reconcile_mass_status),
    ]

    for _name, fn in steps:
        reset_mt5_client_cache()
        await fn(cfg, report)

    if cfg.enable_execution:
        reset_mt5_client_cache()
        await run_stop_orders(cfg, report)
        reset_mt5_client_cache()
        await run_fill_reports_after_fill(cfg, report)
        reset_mt5_client_cache()
        await run_open_on_start_reconcile(cfg, report)

    report.print_summary()

    json_path = os.environ.get(
        "HOMOLOG_REPORT_JSON",
        "homologation/last_xp_open_market_report.json",
    )
    report.write_json(json_path)
    print(f"  JSON report written to {json_path}")

    return 0 if report.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
