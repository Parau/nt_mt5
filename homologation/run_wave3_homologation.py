"""Run homologation wave 3 — documented OPEN pendencies."""
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
from homologation.scenarios.multi_symbol import run_multi_symbol_stream
from homologation.scenarios.position_reconcile_suite import (
    run_close_on_stop_multi,
    run_position_reconcile,
)
from homologation.scenarios.preflight import run_preflight
from homologation.support.clients import reset_mt5_client_cache


async def main() -> int:
    cfg = HomologationConfig.from_env()
    report = HomologationReport()

    print("=" * 64)
    print("  MT5 ADAPTER — HOMOLOGATION WAVE 3 (OPEN pendencies)")
    print(f"  Gateway : {cfg.host}:{cfg.port}")
    print(f"  Symbol  : {cfg.symbol}")
    print(f"  Multi   : {cfg.multi_symbols}")
    print(f"  Feed    : {'ENABLED' if cfg.feed_enabled else 'DISABLED'}")
    print(f"  Exec    : {'ENABLED' if cfg.enable_execution else 'DISABLED'}")
    if os.environ.get("HOMOLOG_D06_REQUIRE_SERVICE_RESTART", "").strip() == "1":
        print("  D06-SVC : manual NT5TickFeedService stop/start when prompted")
    else:
        print("  D06-SVC : skipped (set HOMOLOG_D06_REQUIRE_SERVICE_RESTART=1)")
    for sym in cfg.multi_symbols:
        tick = probe_symbol_tick(cfg.host, cfg.port, sym)
        print(f"  Quote {sym}: {tick if tick else 'NO TICK'}")
    print("=" * 64)

    reset_mt5_client_cache()
    await run_preflight(cfg, report)
    if report.has_failures:
        report.print_summary()
        return 1

    runners = []
    if os.environ.get("HOMOLOG_D06_REQUIRE_SERVICE_RESTART", "").strip() == "1":
        runners.append(run_feed_service_restart_dedup)
    runners.extend([
        run_multi_symbol_stream,
        run_position_reconcile,
        run_close_on_stop_multi,
    ])
    for runner in runners:
        reset_mt5_client_cache()
        await runner(cfg, report)

    report.print_summary()
    json_path = os.environ.get("HOMOLOG_REPORT_JSON", "homologation/last_wave3_report.json")
    report.write_json(json_path)
    print(f"  JSON report written to {json_path}")
    return 0 if report.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
