"""XP/B3 backlog — D06 feed resilience + D21 historical quotes (open market)."""
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
from homologation.scenarios.feed_resilience import run_feed_service_restart_dedup
from homologation.scenarios.preflight import run_preflight
from homologation.support.clients import reset_mt5_client_cache


async def main() -> int:
    cfg = HomologationConfig.from_env()
    if not cfg.feed_enabled:
        os.environ["MT5_FEED_ENABLED"] = "1"
        cfg = HomologationConfig.from_env()

    report = HomologationReport()

    print("=" * 64)
    print("  MT5 ADAPTER — XP/B3 BACKLOG (D06 + D21)")
    print(f"  Gateway : {cfg.host}:{cfg.port}")
    print(f"  Symbol  : {cfg.symbol}")
    print(f"  Feed    : {'ENABLED' if cfg.feed_enabled else 'DISABLED'}")
    print("=" * 64)

    reset_mt5_client_cache()
    await run_preflight(cfg, report)
    if report.has_failures:
        report.print_summary()
        return 1

    reset_mt5_client_cache()
    await run_feed_service_restart_dedup(cfg, report)
    reset_mt5_client_cache()
    await run_request_quote_ticks_e2e(cfg, report)

    report.print_summary()
    path = os.environ.get(
        "HOMOLOG_REPORT_JSON",
        "homologation/last_xp_backlog_report.json",
    )
    report.write_json(path)
    print(f"  JSON report written to {path}")
    return 0 if report.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
