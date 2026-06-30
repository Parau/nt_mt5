"""Tickmill aggressor regression — XP changes must not alter Tickmill behavior.

Validates:
  - TC-HOM-D08 / D08b: TradeTick subscribe/request still gated (UNSUPPORTED profile)
  - TC-HOM-AGG-TM: historical TRADES via adapter use NO_AGGRESSOR only
  - TC-HOM-D02 (optional): WS quote stream when MT5_FEED_ENABLED=1

Usage (CMD):
    set MT5_HOST=127.0.0.1 && set MT5_PORT=18812 && set MT5_SYMBOL=BTCUSD && ^
    set MT5_FEED_ENABLED=1 && set HOMOLOG_STREAM_SECS=30 && set HOMOLOG_STREAM_MIN_TICKS=3 && ^
    E:\\miniconda\\envs\\trading\\python.exe homologation\\run_tickmill_aggressor_homologation.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import timedelta

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from nautilus_trader.model.enums import AggressorSide

from homologation.config import HomologationConfig
from homologation.report import HomologationReport, ScenarioStatus
from homologation.scenarios.closed_market_suite import (
    _instrument_id,
    _make_data_client,
    run_request_quote_ticks_e2e,
    run_trade_tick_request_rejected,
    run_unsupported_gates,
)
from homologation.scenarios.preflight import run_preflight
from homologation.scenarios.tick_stream import run_tick_stream
from homologation.support.clients import reset_mt5_client_cache
from nautilus_mt5.data_types import MT5Symbol
from nautilus_mt5.tick_routing import TICK_FLAG_BUY, TICK_FLAG_SELL, resolve_trade_aggressor


async def run_tickmill_aggressor_mapping(
    cfg: HomologationConfig,
    report: HomologationReport,
) -> None:
    """TC-HOM-AGG-TM: map_tick_flags_to_aggressor=False → all NO_AGGRESSOR."""
    case_id = "TC-HOM-AGG-TM"
    name = "Historical TRADES aggressor disabled (Tickmill profile)"

    if cfg.venue_profile.map_tick_flags_to_aggressor:
        report.add(case_id, name, ScenarioStatus.FAIL, "profile has map_tick_flags_to_aggressor=True")
        return

    limit = int(os.environ.get("HOMOLOG_AGGRESSOR_LIMIT", "100"))
    lookback_days = int(os.environ.get("HOMOLOG_TRADE_LOOKBACK_DAYS", "7"))
    start = pd.Timestamp.utcnow() - timedelta(days=lookback_days)
    reset_mt5_client_cache()
    data_client, _, cache, _ = await _make_data_client(cfg)
    iid = _instrument_id(cfg.symbol)

    try:
        await data_client._connect()
        await data_client.instrument_provider.load_async(iid)
        instrument = cache.instrument(iid)
        if instrument is None:
            report.add(case_id, name, ScenarioStatus.FAIL, "instrument not loaded")
            return

        sym = MT5Symbol(**instrument.info["symbol"])
        ticks = await data_client._handle_ticks_request(sym, "TRADES", limit, start, None)

        if ticks:
            buyers = sum(1 for t in ticks if t.aggressor_side == AggressorSide.BUYER)
            sellers = sum(1 for t in ticks if t.aggressor_side == AggressorSide.SELLER)
            no_agg = sum(1 for t in ticks if t.aggressor_side == AggressorSide.NO_AGGRESSOR)

            if buyers + sellers > 0:
                report.add(
                    case_id,
                    name,
                    ScenarioStatus.FAIL,
                    f"unexpected BUYER={buyers} SELLER={sellers} (expected all NO_AGGRESSOR)",
                    ticks=len(ticks),
                )
                return

            report.add(
                case_id,
                name,
                ScenarioStatus.PASS,
                f"{len(ticks)} ticks all NO_AGGRESSOR (BUYER=0 SELLER=0 NO_AG={no_agg})",
                ticks=len(ticks),
            )
            return

        # Tickmill often has quote-only ticks (last=0); validate routing + AllLast path.
        await _run_tickmill_aggressor_fallback(cfg, report, data_client, sym, limit, start)
    except Exception as exc:
        report.add(case_id, name, ScenarioStatus.FAIL, str(exc))
    finally:
        await data_client._disconnect()
        reset_mt5_client_cache()


async def _run_tickmill_aggressor_fallback(
    cfg: HomologationConfig,
    report: HomologationReport,
    data_client,
    sym: MT5Symbol,
    limit: int,
    start: pd.Timestamp,
) -> None:
    """TC-HOM-AGG-TMb: no TRADES in window — verify routing disabled + AllLast safe."""
    case_id = "TC-HOM-AGG-TMb"
    name = "Aggressor routing disabled when Tickmill has no trade ticks"

    for flags, label in ((TICK_FLAG_BUY, "BUY"), (TICK_FLAG_SELL, "SELL"), (TICK_FLAG_BUY | TICK_FLAG_SELL, "BUY|SELL")):
        side = resolve_trade_aggressor(flags, map_from_tick_flags=False)
        if side != AggressorSide.NO_AGGRESSOR:
            report.add(case_id, name, ScenarioStatus.FAIL, f"resolve_trade_aggressor({label})={side}")
            return

    all_last = await data_client._handle_ticks_request(sym, "AllLast", limit, start, None)
    buyers = sum(1 for t in all_last if getattr(t, "aggressor_side", None) == AggressorSide.BUYER)
    sellers = sum(1 for t in all_last if getattr(t, "aggressor_side", None) == AggressorSide.SELLER)

    if buyers + sellers > 0:
        report.add(
            case_id,
            name,
            ScenarioStatus.FAIL,
            f"AllLast path leaked aggressor BUYER={buyers} SELLER={sellers}",
            ticks=len(all_last),
        )
        return

    report.add(
        case_id,
        name,
        ScenarioStatus.PASS,
        f"no TRADES in window; routing OFF; AllLast ticks={len(all_last)} with zero BUYER/SELLER",
        ticks=len(all_last),
    )


async def main() -> int:
    cfg = HomologationConfig.from_env()
    if cfg.venue_profile.name == "xp-b3":
        print("SKIP: Tickmill aggressor homologation — unset MT5_VENUE_PROFILE=xp_b3")
        return 0

    report = HomologationReport()

    print("=" * 64)
    print("  TICKMILL AGGRESSOR REGRESSION HOMOLOGATION")
    print(f"  Gateway : {cfg.host}:{cfg.port}")
    print(f"  Profile : {cfg.venue_profile.name} (map_aggressor={cfg.venue_profile.map_tick_flags_to_aggressor})")
    print(f"  Symbol  : {cfg.symbol}")
    print(f"  Feed    : {'ON' if cfg.feed_enabled else 'OFF'}")
    print("=" * 64)

    reset_mt5_client_cache()
    await run_preflight(cfg, report)
    if report.has_failures:
        report.print_summary()
        _write_report(report)
        return 1

    await run_unsupported_gates(cfg, report)
    await run_trade_tick_request_rejected(cfg, report)
    await run_tickmill_aggressor_mapping(cfg, report)
    await run_request_quote_ticks_e2e(cfg, report)

    if cfg.feed_enabled and not cfg.skip_stream:
        await run_tick_stream(cfg, report)

    report.print_summary()
    _write_report(report)
    return 1 if report.has_failures else 0


def _write_report(report: HomologationReport) -> None:
    path = os.environ.get(
        "HOMOLOG_REPORT_JSON",
        os.path.join(_ROOT, "homologation", "last_tickmill_aggressor_report.json"),
    )
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report.to_dict(), fh, indent=2)
    print(f"\nReport: {path}")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
