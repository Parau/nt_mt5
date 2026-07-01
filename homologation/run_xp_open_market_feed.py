"""
run_xp_open_market_feed.py
============================

XP/B3 open-market — **real-time feed scenarios only** (WS tick stream).

Re-run after fixing NT5TickFeedService URL (container XP → host :8766).

Container: RPyC ``127.0.0.1:18813``, feed ``ws://0.0.0.0:8766/mt5-feed``
(Service in MT5: ``ws://host.docker.internal:8766/mt5-feed``)

Scenarios: PF, D01/E01, D02, D04 multi-symbol, D06, D03, D05.

Usage (Windows CMD)
-------------------
    set MT5_HOST=127.0.0.1
    set MT5_PORT=18813
    set MT5_VENUE_PROFILE=xp_b3
    set MT5_ACCOUNT_NUMBER=56822578
    set MT5_SYMBOL=WDOQ26
    set MT5_FEED_ENABLED=1
    rem Feed-only: leave exec off to avoid portfolio/reconcile noise
    rem set MT5_ENABLE_LIVE_EXECUTION=1
    set HOMOLOG_MULTI_SYMBOLS=WDOQ26,PETR4,DI1F27,WINQ26
    set HOMOLOG_STREAM_SECS=60
    set HOMOLOG_REPORT_JSON=homologation/last_xp_open_market_feed_report.json
    E:\\miniconda\\envs\\trading\\python.exe homologation\\run_xp_open_market_feed.py
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
from homologation.scenarios.data_tester_suite import run_bar_subscribe, run_unsubscribe_on_stop
from homologation.scenarios.feed_resilience import run_feed_service_restart_dedup
from homologation.scenarios.multi_symbol import run_multi_symbol_stream
from homologation.scenarios.preflight import run_preflight
from homologation.scenarios.tick_stream import run_tick_stream
from homologation.scenarios.trading_node_suite import run_trading_node_suite
from homologation.support.clients import reset_mt5_client_cache

_XP_LOGIN = "56822578"


async def main() -> int:
    cfg = HomologationConfig.from_env()
    if not cfg.feed_enabled:
        os.environ["MT5_FEED_ENABLED"] = "1"
        cfg = HomologationConfig.from_env()

    report = HomologationReport()

    print("=" * 64)
    print("  MT5 ADAPTER — XP/B3 OPEN MARKET (FEED / REAL-TIME TICKS)")
    print(f"  Gateway : {cfg.host}:{cfg.port}")
    print(f"  Account : {cfg.account_number}  (expected {_XP_LOGIN})")
    print(f"  Symbol  : {cfg.symbol}")
    print(f"  Multi   : {','.join(cfg.multi_symbols)}")
    print(f"  WS feed : ws://{cfg.feed_host}:{cfg.feed_port}{cfg.feed_path}")
    print(f"  Stream  : {cfg.stream_duration_secs:.0f}s")
    print("=" * 64)

    reset_mt5_client_cache()
    await run_preflight(cfg, report)
    if report.has_failures:
        report.print_summary()
        return 1

    steps = [
        ("trading_node_d01_e01", run_trading_node_suite),
        ("tick_stream_d02", run_tick_stream),
        ("multi_symbol_d04", run_multi_symbol_stream),
        ("feed_resilience_d06", run_feed_service_restart_dedup),
        ("bar_subscribe_d03", run_bar_subscribe),
        ("unsubscribe_d05", run_unsubscribe_on_stop),
    ]

    for _name, fn in steps:
        reset_mt5_client_cache()
        await fn(cfg, report)

    report.print_summary()

    json_path = os.environ.get(
        "HOMOLOG_REPORT_JSON",
        "homologation/last_xp_open_market_feed_report.json",
    )
    report.write_json(json_path)
    print(f"  JSON report written to {json_path}")

    return 0 if report.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
