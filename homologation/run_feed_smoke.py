"""
run_feed_smoke.py — **operational gate** for TC-HOM-D02 (WS sustained quote ticks).

Validates that ``NT5TickFeedService`` sustains ``CopyTicks`` → WebSocket → ``QuoteTick``
before running broader open-market / exec homologation suites.

Prerequisites:
  1. RPyC bridge up (profile port: Tickmill 18812, XP 18813, AMP 18814)
  2. ``NT5TickFeedService`` started in MT5 (Navigator → Services → Start)
  3. ``MT5_FEED_ENABLED=1``

Usage — Tickmill (Windows CMD):
    set MT5_HOST=127.0.0.1
    set MT5_PORT=18812
    set MT5_SYMBOL=BTCUSD
    set MT5_FEED_ENABLED=1
    set HOMOLOG_STREAM_SECS=60
    set HOMOLOG_REPORT_JSON=homologation/last_tickmill_feed_smoke_report.json
    E:\\miniconda\\envs\\trading\\python.exe homologation\\run_feed_smoke.py
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
from homologation.scenarios.preflight import run_preflight
from homologation.scenarios.tick_stream import run_tick_stream
from homologation.support.clients import reset_mt5_client_cache


async def main() -> int:
    cfg = HomologationConfig.from_env()
    if not cfg.feed_enabled:
        os.environ["MT5_FEED_ENABLED"] = "1"
        cfg = HomologationConfig.from_env()

    report = HomologationReport()

    print("=" * 64)
    print("  MT5 WS FEED SMOKE — TC-HOM-D02 (Service → QuoteTick)")
    print(f"  RPyC    : {cfg.host}:{cfg.port}")
    print(f"  WS feed : ws://{cfg.feed_host}:{cfg.feed_port}{cfg.feed_path}")
    print(f"  Symbol  : {cfg.symbol}")
    print(f"  Stream  : {cfg.stream_duration_secs:.0f}s, min {cfg.stream_min_ticks} ticks")
    print("=" * 64)
    print()
    print("Ensure NT5TickFeedService is running in MT5 (Navigator → Services → Start).")
    print()

    reset_mt5_client_cache()

    await run_preflight(cfg, report)
    if report.has_failures:
        report.print_summary()
        return 1

    await run_tick_stream(cfg, report)
    report.print_summary()

    json_path = os.environ.get("HOMOLOG_REPORT_JSON", "").strip()
    if json_path:
        report.write_json(json_path)
        print(f"  JSON report written to {json_path}")

    return 0 if not report.has_failures else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
