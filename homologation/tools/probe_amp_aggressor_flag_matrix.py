"""
Probe AMP trade-flag matrix vs LAST-gated aggressor mapping.

Purpose:
    Count COPY_TICKS_TRADE rows by LAST/VOLUME/BUY/SELL combinations and compare
    current ``mt5_flags_to_aggressor`` (requires LAST) vs a relaxed mapper that
    honours BUY/SELL without LAST. Observation only — does not change adapter code.

Usage (Windows CMD)::

    set MT5_HOST=127.0.0.1 && set MT5_PORT=18814 && ^
    set HOMOLOG_SYMBOLS=MNQU26,ENQU26 && ^
    set HOMOLOG_LOOKBACK_HOURS=6 && ^
    E:\\miniconda\\envs\\trading\\python.exe ^
        homologation\\tools\\probe_amp_aggressor_flag_matrix.py

Writes ``homologation/last_amp_aggressor_flag_matrix.json``.
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import rpyc
from nautilus_trader.model.enums import AggressorSide

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nautilus_mt5.metatrader5.tick_transport import decode_mt5_ticks_frame
from nautilus_mt5.tick_routing import (
    TICK_FLAG_BUY,
    TICK_FLAG_LAST,
    TICK_FLAG_SELL,
    TICK_FLAG_VOLUME,
    mt5_flags_to_aggressor,
)

COPY_TICKS_TRADE = 2
TRADE_MASK = TICK_FLAG_LAST | TICK_FLAG_VOLUME


def _load_ticks(root: object, symbol: str, start_i: int, end_i: int):
    """Fetch TRADE ticks and materialize an exact local ndarray (no RPyC netref)."""
    from nautilus_mt5.metatrader5.utils import normalize_rpyc_return

    wire = normalize_rpyc_return(root.copy_ticks_range(symbol, start_i, end_i, COPY_TICKS_TRADE))
    if wire is None:
        return None
    if isinstance(wire, tuple):
        return decode_mt5_ticks_frame(wire)
    raise RuntimeError(
        "copy_ticks_range did not return MT5_TICKS_V1 frame; "
        f"got {type(wire)!r}. Update AMP bridge before probing large windows.",
    )


def _relaxed_aggressor(flags: int) -> AggressorSide:
    """BUY/SELL mutually exclusive — no LAST requirement (probe-only)."""
    if (flags & TICK_FLAG_BUY) and not (flags & TICK_FLAG_SELL):
        return AggressorSide.BUYER
    if (flags & TICK_FLAG_SELL) and not (flags & TICK_FLAG_BUY):
        return AggressorSide.SELLER
    return AggressorSide.NO_AGGRESSOR


def _side_name(side: AggressorSide) -> str:
    return AggressorSide(side).name


def _classify_buckets(flags: int) -> list[str]:
    """Return all matching bucket labels for a trade-emitible row."""
    has_last = bool(flags & TICK_FLAG_LAST)
    has_vol = bool(flags & TICK_FLAG_VOLUME)
    has_buy = bool(flags & TICK_FLAG_BUY)
    has_sell = bool(flags & TICK_FLAG_SELL)
    labels: list[str] = []

    if has_last and has_buy and not has_sell:
        labels.append("LAST+BUY")
    if has_last and has_sell and not has_buy:
        labels.append("LAST+SELL")
    if has_last and has_vol and has_buy and not has_sell:
        labels.append("LAST+VOLUME+BUY")
    if has_last and has_vol and has_sell and not has_buy:
        labels.append("LAST+VOLUME+SELL")
    if has_vol and has_buy and not has_last and not has_sell:
        labels.append("VOLUME+BUY_no_LAST")
    if has_vol and has_sell and not has_last and not has_buy:
        labels.append("VOLUME+SELL_no_LAST")
    if (has_last or has_vol) and not has_buy and not has_sell:
        labels.append("LAST_or_VOLUME_no_BUY_SELL")
    if (has_buy or has_sell) and not has_last:
        labels.append("BUY_or_SELL_no_LAST")
    if has_buy and has_sell:
        labels.append("ambiguous_BUY_and_SELL")
    return labels


def _row_sample(t: Any) -> dict[str, Any]:
    flags = int(t["flags"])
    return {
        "time_msc": int(t["time_msc"]),
        "last": float(t["last"]),
        "volume": int(t["volume"]),
        "volume_real": float(t["volume_real"]),
        "flags": flags,
        "bid": float(t["bid"]),
        "ask": float(t["ask"]),
        "buckets": _classify_buckets(flags),
        "aggressor_current": _side_name(mt5_flags_to_aggressor(flags)),
        "aggressor_relaxed": _side_name(_relaxed_aggressor(flags)),
    }


def analyze_symbol(arr, symbol: str) -> dict[str, Any]:
    if arr is None:
        return {
            "symbol": symbol,
            "trade_rows": 0,
            "detail": "provider returned None",
            "buckets": {},
            "aggressor_comparison": {},
            "critical_samples": [],
            "verdict": "NO_DATA",
        }

    bucket_counts: Counter[str] = Counter()
    current_sides: Counter[str] = Counter()
    relaxed_sides: Counter[str] = Counter()
    current_no_relaxed_known = 0
    current_no_on_volume_buy_sell = 0
    volume_buy_no_last = 0
    volume_sell_no_last = 0
    critical_samples: list[dict[str, Any]] = []
    trade_rows = 0

    for t in arr:
        flags = int(t["flags"])
        if not (flags & TRADE_MASK):
            continue
        trade_rows += 1
        for label in _classify_buckets(flags):
            bucket_counts[label] += 1

        cur = mt5_flags_to_aggressor(flags)
        rel = _relaxed_aggressor(flags)
        current_sides[_side_name(cur)] += 1
        relaxed_sides[_side_name(rel)] += 1

        is_vol_buy = bool(
            (flags & TICK_FLAG_VOLUME)
            and (flags & TICK_FLAG_BUY)
            and not (flags & TICK_FLAG_LAST)
            and not (flags & TICK_FLAG_SELL),
        )
        is_vol_sell = bool(
            (flags & TICK_FLAG_VOLUME)
            and (flags & TICK_FLAG_SELL)
            and not (flags & TICK_FLAG_LAST)
            and not (flags & TICK_FLAG_BUY),
        )
        if is_vol_buy:
            volume_buy_no_last += 1
        if is_vol_sell:
            volume_sell_no_last += 1

        if cur == AggressorSide.NO_AGGRESSOR and rel != AggressorSide.NO_AGGRESSOR:
            current_no_relaxed_known += 1
            if is_vol_buy or is_vol_sell:
                current_no_on_volume_buy_sell += 1
            if len(critical_samples) < 25:
                critical_samples.append(_row_sample(t))

    current_no = int(current_sides.get("NO_AGGRESSOR", 0))
    critical_vol_side = volume_buy_no_last + volume_sell_no_last
    pct_current_no = (100.0 * current_no / trade_rows) if trade_rows else 0.0
    pct_explained = (
        (100.0 * current_no_relaxed_known / current_no) if current_no else 0.0
    )

    if trade_rows == 0:
        verdict = "NO_TRADE_ROWS"
    elif critical_vol_side > 0 and current_no_on_volume_buy_sell > 0:
        verdict = "SUSPECT_CONFIRMED_VOLUME_BUY_SELL_WITHOUT_LAST"
    elif current_no_relaxed_known > 0:
        verdict = "SUSPECT_PARTIAL_BUY_SELL_WITHOUT_LAST"
    elif current_no > 0 and critical_vol_side == 0:
        verdict = "LAST_GATE_NOT_CULPRIT_NO_SIDE_ON_MOST_NO_AGGRESSOR"
    else:
        verdict = "NO_MATERIAL_LAST_GATE_LOSS"

    return {
        "symbol": symbol,
        "trade_rows": trade_rows,
        "buckets": dict(sorted(bucket_counts.items())),
        "bucket_pct_of_trade_rows": {
            k: round(100.0 * v / trade_rows, 3) if trade_rows else 0.0
            for k, v in sorted(bucket_counts.items())
        },
        "aggressor_comparison": {
            "current_sides": dict(sorted(current_sides.items())),
            "relaxed_sides": dict(sorted(relaxed_sides.items())),
            "current_NO_AGGRESSOR": current_no,
            "current_NO_AGGRESSOR_pct": round(pct_current_no, 3),
            "current_NO_and_relaxed_known": current_no_relaxed_known,
            "current_NO_and_relaxed_known_pct_of_current_NO": round(pct_explained, 3),
            "current_NO_on_VOLUME_BUY_or_SELL_no_LAST": current_no_on_volume_buy_sell,
            "VOLUME_BUY_no_LAST": volume_buy_no_last,
            "VOLUME_SELL_no_LAST": volume_sell_no_last,
        },
        "critical_samples": critical_samples,
        "verdict": verdict,
    }


def _print_symbol(report: dict[str, Any]) -> None:
    def _log(msg: str) -> None:
        print(msg, flush=True)

    _log(f"\n{'=' * 72}")
    _log(f"  {report['symbol']}")
    _log(f"{'=' * 72}")
    _log(f"  Trade-emitible rows (LAST|VOLUME): {report['trade_rows']}")
    _log("  Buckets:")
    for name, count in (report.get("buckets") or {}).items():
        pct = (report.get("bucket_pct_of_trade_rows") or {}).get(name, 0.0)
        _log(f"    {name:32s} {count:8d}  ({pct:6.2f}%)")
    cmp_ = report.get("aggressor_comparison") or {}
    _log("  Aggressor comparison:")
    _log(f"    current sides : {cmp_.get('current_sides')}")
    _log(f"    relaxed sides : {cmp_.get('relaxed_sides')}")
    _log(
        f"    current NO={cmp_.get('current_NO_AGGRESSOR')} "
        f"({cmp_.get('current_NO_AGGRESSOR_pct')}%) | "
        f"NO→relaxed_known={cmp_.get('current_NO_and_relaxed_known')} "
        f"({cmp_.get('current_NO_and_relaxed_known_pct_of_current_NO')}% of NO) | "
        f"VOLUME±side no LAST={cmp_.get('VOLUME_BUY_no_LAST')}+"
        f"{cmp_.get('VOLUME_SELL_no_LAST')}",
    )
    _log(f"  Verdict: {report.get('verdict')}")


def main() -> int:
    host = os.environ.get("MT5_HOST", "127.0.0.1")
    port = int(os.environ.get("MT5_PORT", "18814"))
    symbols_raw = os.environ.get("HOMOLOG_SYMBOLS", "MNQU26,ENQU26")
    symbols = [s.strip() for s in symbols_raw.split(",") if s.strip()]
    lookback_h = float(os.environ.get("HOMOLOG_LOOKBACK_HOURS", "6"))
    out_path = Path(
        os.environ.get(
            "HOMOLOG_OUT",
            str(ROOT / "homologation" / "last_amp_aggressor_flag_matrix.json"),
        ),
    )

    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=lookback_h)
    start_i = int(start.timestamp())
    end_i = int(end.timestamp())

    def _log(msg: str) -> None:
        print(msg, flush=True)

    _log(
        f"AMP aggressor flag matrix | RPyC {host}:{port} | "
        f"symbols={symbols} | lookback_h={lookback_h}",
    )
    _log(f"Window UTC: {start.isoformat()} → {end.isoformat()}")
    _log("Adapter code: mt5_flags_to_aggressor UNCHANGED (observation only)")

    conn = rpyc.connect(host, port, config={"sync_request_timeout": 300})
    root = conn.root
    symbol_reports: list[dict[str, Any]] = []
    try:
        for symbol in symbols:
            _log(f"Fetching COPY_TICKS_TRADE for {symbol} ...")
            root.symbol_select(symbol, True)
            arr = _load_ticks(root, symbol, start_i, end_i)
            n = 0 if arr is None else int(len(arr))
            _log(f"  received rows={n}; analyzing ...")
            report = analyze_symbol(arr, symbol)
            if arr is not None:
                report["provider_trade_count"] = n
            symbol_reports.append(report)
            _print_symbol(report)
    finally:
        conn.close()

    overall = "INCONCLUSIVE"
    if any(
        r.get("verdict") == "SUSPECT_CONFIRMED_VOLUME_BUY_SELL_WITHOUT_LAST"
        for r in symbol_reports
    ):
        overall = "SUSPECT_CONFIRMED_VOLUME_BUY_SELL_WITHOUT_LAST"
    elif any(
        r.get("verdict") == "SUSPECT_PARTIAL_BUY_SELL_WITHOUT_LAST"
        for r in symbol_reports
    ):
        overall = "SUSPECT_PARTIAL_BUY_SELL_WITHOUT_LAST"
    elif all(
        r.get("verdict")
        in (
            "LAST_GATE_NOT_CULPRIT_NO_SIDE_ON_MOST_NO_AGGRESSOR",
            "NO_MATERIAL_LAST_GATE_LOSS",
            "NO_TRADE_ROWS",
            "NO_DATA",
        )
        for r in symbol_reports
    ):
        if any(
            r.get("verdict") == "LAST_GATE_NOT_CULPRIT_NO_SIDE_ON_MOST_NO_AGGRESSOR"
            for r in symbol_reports
        ):
            overall = "LAST_GATE_NOT_CULPRIT_NO_SIDE_ON_MOST_NO_AGGRESSOR"
        else:
            overall = "NO_MATERIAL_LAST_GATE_LOSS"

    payload = {
        "purpose": (
            "AMP COPY_TICKS_TRADE flag matrix vs LAST-gated aggressor; "
            "measure VOLUME|BUY/SELL without LAST discarded as NO_AGGRESSOR"
        ),
        "probe": "homologation/tools/probe_amp_aggressor_flag_matrix.py",
        "mt5_host": host,
        "mt5_port": port,
        "window_utc": [start.isoformat(), end.isoformat()],
        "lookback_hours": lookback_h,
        "symbols": symbols,
        "adapter_mt5_flags_to_aggressor_changed": False,
        "symbols_detail": symbol_reports,
        "overall_verdict": overall,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"\nOverall verdict: {overall}", flush=True)
    print(f"Report: {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
