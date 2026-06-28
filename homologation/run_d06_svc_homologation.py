"""TC-HOM-D06-SVC only: gateway restart + manual NT5TickFeedService stop/start."""
from __future__ import annotations

import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from homologation.config import HomologationConfig, probe_symbol_tick
from homologation.report import HomologationReport
from homologation.scenarios.feed_resilience import run_feed_service_restart_dedup
from homologation.scenarios.preflight import run_preflight
from homologation.support.clients import reset_mt5_client_cache


async def main() -> int:
    os.environ["HOMOLOG_D06_REQUIRE_SERVICE_RESTART"] = "1"
    cfg = HomologationConfig.from_env()
    report = HomologationReport()

    print("=" * 64)
    print("  TC-HOM-D06-SVC — WS feed + manual Service restart")
    print(f"  Gateway : {cfg.host}:{cfg.port}")
    print(f"  WS feed : ws://{cfg.feed_host}:{cfg.feed_port}{cfg.feed_path}")
    print(f"  Symbol  : {cfg.symbol}")
    print("  >>> When prompted: STOP then START NT5TickFeedService in MT5 <<<")
    print("=" * 64)
    tick = probe_symbol_tick(cfg.host, cfg.port, cfg.symbol)
    print(f"  Quote {cfg.symbol}: {tick if tick else 'NO TICK'}")

    reset_mt5_client_cache()
    await run_preflight(cfg, report)
    if report.has_failures:
        report.print_summary()
        return 1

    reset_mt5_client_cache()
    await run_feed_service_restart_dedup(cfg, report)

    report.print_summary()
    json_path = os.environ.get("HOMOLOG_REPORT_JSON", "homologation/last_d06_svc_report.json")
    report.write_json(json_path)
    print(f"  JSON report written to {json_path}")
    return 0 if report.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
