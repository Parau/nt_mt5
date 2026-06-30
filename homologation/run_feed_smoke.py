"""
WS feed smoke test — TC-HOM-D02 (MQL5 Service → InboundFeedGateway → QuoteTick).

Prerequisites (manual):
  1. RPyC bridge running (port 18812)
  2. NT5TickFeedService started in MT5 with:
       InpWsUrl=ws://127.0.0.1:8765/mt5-feed
       InpSymbols=<MT5_SYMBOL>
  3. Start this script BEFORE or AFTER the Service (hello timeout 30s by default)

Usage (Windows CMD):
    set MT5_HOST=127.0.0.1
    set MT5_PORT=18812
    set MT5_FEED_ENABLED=1
    set MT5_SYMBOL=BTCUSD
    set HOMOLOG_STREAM_SECS=30
    set HOMOLOG_STREAM_MIN_TICKS=3
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
    return 0 if not report.has_failures else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
