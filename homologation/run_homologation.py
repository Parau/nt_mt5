"""
run_homologation.py
===================

Live homologation harness for the nautilus_mt5 adapter.

Runs a fixed set of scenarios against a real MT5 terminal via the external
RPyC bridge (EXTERNAL_RPYC).  Intended as a manual gate before production use.

Default symbol is BTCUSD — the only instrument typically open outside FX hours
on Tickmill-Demo.

Environment variables
---------------------
MT5_HOST                   RPyC gateway host  (default: 127.0.0.1)
MT5_PORT                   RPyC gateway port  (default: 18812)
MT5_ACCOUNT_NUMBER         MT5 login (auto-detected from bridge if unset)
MT5_SYMBOL                 Symbol to test    (default: BTCUSD)
MT5_BROKER                 Broker label        (default: Tickmill-Demo)
MT5_ENABLE_LIVE_EXECUTION  Set to "1" for order scenarios (E01, E02)
HOMOLOG_MIN_TICKS          Min quote ticks for D01 (default: 3)
HOMOLOG_STREAM_SECS        D02 stream duration in seconds (default: 120)
HOMOLOG_STREAM_MAX_GAP_SECS  D02 max silent gap between ticks (default: 30)
HOMOLOG_STREAM_MIN_TICKS   D02 minimum ticks during stream (default: 5)
HOMOLOG_SKIP_STREAM        Set to "1" to skip D02 streaming scenario
MT5_FEED_ENABLED           Set to "1" for WS live quotes (required for D02)
MT5_FEED_HOST              WS server bind (default: 0.0.0.0)
MT5_FEED_PORT              WS server port (default: 8765)
MT5_FEED_PATH              WS path (default: /mt5-feed)
MT5_FEED_HELLO_TIMEOUT_SECS  Wait for MQL5 Service hello (default: 30)
HOMOLOG_TIMEOUT_SECS       Per-scenario timeout (default: 120)
HOMOLOG_REPORT_JSON        Optional path to write JSON report

Usage (Windows CMD)
-------------------
    set MT5_HOST=127.0.0.1
    set MT5_PORT=18812
    set MT5_ENABLE_LIVE_EXECUTION=1
    E:\\miniconda\\envs\\trading\\python.exe homologation\\run_homologation.py

Data-only (no orders):
    E:\\miniconda\\envs\\trading\\python.exe homologation\\run_homologation.py
"""
from __future__ import annotations

import asyncio
import os
import sys

# Ensure project root is importable when run as a script.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from homologation.config import HomologationConfig
from homologation.report import HomologationReport
from homologation.scenarios.preflight import run_preflight
from homologation.scenarios.tick_stream import run_tick_stream_for_suite
from homologation.scenarios.trading_node_suite import run_trading_node_suite
from homologation.scenarios.stop_orders import run_stop_orders
from homologation.scenarios.data_tester_suite import run_bar_subscribe, run_unsubscribe_on_stop
from homologation.scenarios.exec_tester_suite import (
    run_cancel_rejection,
    run_hedging_positions,
    run_hedging_sell_positions,
    run_limit_fok_day_scenarios,
    run_limit_gtc_cancel,
    run_limit_ioc_scenarios,
    run_modify_stop_trigger,
    run_modify_volume,
)
from homologation.scenarios.feed_resilience import run_feed_service_restart_dedup
from homologation.scenarios.mt5_edges import (
    run_cancel_close_on_stop,
    run_fill_reports_after_fill,
    run_open_on_start_reconcile,
    run_real_retcodes,
    run_reconcile_mass_status,
)
from homologation.scenarios.multi_symbol import run_multi_symbol_stream
from homologation.scenarios.position_reconcile_suite import (
    run_close_on_stop_mixed,
    run_close_on_stop_multi,
    run_minimal_mixed_book,
    run_position_reconcile,
)
from homologation.support.clients import reset_mt5_client_cache


async def main() -> int:
    cfg = HomologationConfig.from_env()
    report = HomologationReport()

    print("=" * 64)
    print("  MT5 ADAPTER — HOMOLOGATION HARNESS")
    print(f"  Gateway : {cfg.host}:{cfg.port}")
    print(f"  Account : {cfg.account_number}")
    print(f"  Symbol  : {cfg.symbol}  (default BTCUSD when only crypto is open)")
    print(f"  Exec    : {'ENABLED' if cfg.enable_execution else 'DISABLED (data-only)'}")
    print(
        f"  Stream  : {cfg.stream_duration_secs:.0f}s "
        f"({'SKIP' if cfg.skip_stream else 'ENABLED'})"
    )
    print(
        f"  WS feed : {'ENABLED' if cfg.feed_enabled else 'DISABLED (D02 skipped)'} "
        f"ws://{cfg.feed_host}:{cfg.feed_port}{cfg.feed_path}"
    )
    if cfg.feed_enabled and not cfg.skip_stream:
        print("  Note    : run run_feed_smoke.py first (D02 gate); suites skip D02 unless HOMOLOG_RUN_D02_IN_SUITE=1")
    print("=" * 64)

    reset_mt5_client_cache()

    await run_preflight(cfg, report)
    if report.has_failures:
        report.print_summary()
        return 1

    await run_trading_node_suite(cfg, report)
    reset_mt5_client_cache()
    await run_tick_stream_for_suite(cfg, report)
    reset_mt5_client_cache()
    await run_feed_service_restart_dedup(cfg, report)
    reset_mt5_client_cache()
    await run_multi_symbol_stream(cfg, report)
    reset_mt5_client_cache()
    await run_bar_subscribe(cfg, report)
    reset_mt5_client_cache()
    await run_unsubscribe_on_stop(cfg, report)
    reset_mt5_client_cache()
    await run_stop_orders(cfg, report)
    reset_mt5_client_cache()
    await run_limit_gtc_cancel(cfg, report)
    reset_mt5_client_cache()
    await run_cancel_rejection(cfg, report)
    reset_mt5_client_cache()
    await run_limit_ioc_scenarios(cfg, report)
    reset_mt5_client_cache()
    await run_modify_volume(cfg, report)
    reset_mt5_client_cache()
    await run_limit_fok_day_scenarios(cfg, report)
    reset_mt5_client_cache()
    await run_modify_stop_trigger(cfg, report)
    reset_mt5_client_cache()
    await run_hedging_positions(cfg, report)
    reset_mt5_client_cache()
    await run_hedging_sell_positions(cfg, report)
    reset_mt5_client_cache()
    await run_cancel_close_on_stop(cfg, report)
    reset_mt5_client_cache()
    await run_reconcile_mass_status(cfg, report)
    reset_mt5_client_cache()
    await run_fill_reports_after_fill(cfg, report)
    reset_mt5_client_cache()
    await run_open_on_start_reconcile(cfg, report)
    reset_mt5_client_cache()
    await run_real_retcodes(cfg, report)
    reset_mt5_client_cache()
    await run_position_reconcile(cfg, report)
    reset_mt5_client_cache()
    await run_minimal_mixed_book(cfg, report)
    reset_mt5_client_cache()
    await run_close_on_stop_multi(cfg, report)
    reset_mt5_client_cache()
    await run_close_on_stop_mixed(cfg, report)

    report.print_summary()

    json_path = os.environ.get("HOMOLOG_REPORT_JSON", "").strip()
    if json_path:
        report.write_json(json_path)
        print(f"  JSON report written to {json_path}")

    return 0 if report.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
