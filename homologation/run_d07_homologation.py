"""Run TC-HOM-D07 only."""
from __future__ import annotations

import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from homologation.config import HomologationConfig, probe_symbol_tick
from homologation.report import HomologationReport
from homologation.scenarios.multi_symbol import run_multi_symbol_stream
from homologation.scenarios.preflight import run_preflight
from homologation.support.clients import reset_mt5_client_cache


async def main() -> int:
    cfg = HomologationConfig.from_env()
    report = HomologationReport()

    print("=" * 64)
    print("  TC-HOM-D07 — multi-symbol WS quote stream")
    print(f"  Symbols : {cfg.multi_symbols}")
    print(f"  Feed    : {'ENABLED' if cfg.feed_enabled else 'DISABLED'}")
    for sym in cfg.multi_symbols:
        tick = probe_symbol_tick(cfg.host, cfg.port, sym)
        print(f"  Quote {sym}: {tick if tick else 'NO TICK'}")
    print("=" * 64)

    reset_mt5_client_cache()
    await run_preflight(cfg, report)
    if report.has_failures:
        report.print_summary()
        return 1

    reset_mt5_client_cache()
    await run_multi_symbol_stream(cfg, report)

    report.print_summary()
    json_path = os.environ.get("HOMOLOG_REPORT_JSON", "homologation/last_d07_report.json")
    report.write_json(json_path)
    print(f"  JSON report written to {json_path}")
    return 0 if report.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
