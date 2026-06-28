"""TC-HOM-D03 smoke: M1 bars via WS feed (subscribe_bars)."""
from __future__ import annotations

import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from homologation.config import HomologationConfig
from homologation.report import HomologationReport
from homologation.scenarios.data_tester_suite import run_bar_subscribe
from homologation.support.clients import reset_mt5_client_cache


async def main() -> int:
    cfg = HomologationConfig.from_env()
    if not cfg.feed_enabled:
        os.environ["MT5_FEED_ENABLED"] = "1"
        cfg = HomologationConfig.from_env()

    report = HomologationReport()
    print("=" * 64)
    print("  MT5 WS BAR SMOKE — TC-HOM-D03 (Service → Bar)")
    print(f"  RPyC    : {cfg.host}:{cfg.port}")
    print(f"  WS feed : ws://{cfg.feed_host}:{cfg.feed_port}{cfg.feed_path}")
    print(f"  Symbol  : {cfg.symbol}")
    print("=" * 64)
    print()
    print("Ensure NT5TickFeedService is running (InpBarSpecs optional; adapter sends subscribe_bars).")
    print()

    reset_mt5_client_cache()
    await run_bar_subscribe(cfg, report)
    report.print_summary()
    return 0 if not report.has_failures else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
