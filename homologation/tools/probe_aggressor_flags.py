"""
Fast aggressor-side probe: TICK_FLAG_BUY/SELL on XP vs Tickmill.

Usage (CMD):
    set MT5_HOST=127.0.0.1 && set MT5_PORT=18813 && ^
    E:\\miniconda\\envs\\trading\\python.exe homologation\\tools\\probe_aggressor_flags.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import rpyc

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

TICK_FLAG_BID = 2
TICK_FLAG_ASK = 4
TICK_FLAG_LAST = 8
TICK_FLAG_VOLUME = 16
TICK_FLAG_BUY = 32
TICK_FLAG_SELL = 64
COPY_TICKS_ALL = 0
KNOWN_MASK = (
    TICK_FLAG_BID | TICK_FLAG_ASK | TICK_FLAG_LAST | TICK_FLAG_VOLUME | TICK_FLAG_BUY | TICK_FLAG_SELL
)


def _field(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    try:
        return obj[name]
    except (TypeError, KeyError, IndexError, ValueError):
        pass
    if name != "flags":
        try:
            return getattr(obj, name, default)
        except AttributeError:
            return default
    return default


def _iter_ticks(ticks):
    if ticks is None:
        return
    try:
        import numpy as np

        if isinstance(ticks, np.ndarray):
            for i in range(len(ticks)):
                yield ticks[i]
            return
    except ImportError:
        pass
    yield from ticks


def _flag_names(flags: int) -> str:
    parts = []
    for val, label in (
        (TICK_FLAG_BID, "BID"),
        (TICK_FLAG_ASK, "ASK"),
        (TICK_FLAG_LAST, "LAST"),
        (TICK_FLAG_VOLUME, "VOL"),
        (TICK_FLAG_BUY, "BUY"),
        (TICK_FLAG_SELL, "SELL"),
    ):
        if flags & val:
            parts.append(label)
    extra = flags & ~KNOWN_MASK
    if extra:
        parts.append(f"UNK({extra})")
    return "|".join(parts) if parts else "NONE"


def analyze_aggressor(label: str, ticks) -> dict:
    print(f"\n{'=' * 72}")
    print(f"  {label}")
    print(f"{'=' * 72}")

    rows = list(_iter_ticks(ticks)) if ticks is not None else []
    n = len(rows)
    if n == 0:
        print("  WARNING: 0 ticks")
        return {"n": 0, "verdict": "no_data"}

    trade_rows = []
    for t in rows:
        flags = int(_field(t, "flags", 0) or 0)
        last = float(_field(t, "last", 0) or 0)
        if (flags & TICK_FLAG_LAST) or last > 0:
            trade_rows.append(t)

    tn = len(trade_rows)
    buy_only = sell_only = both = neither = 0
    unknown_bits: dict[int, int] = {}

    for t in trade_rows:
        flags = int(_field(t, "flags", 0) or 0)
        has_buy = bool(flags & TICK_FLAG_BUY)
        has_sell = bool(flags & TICK_FLAG_SELL)
        if has_buy and has_sell:
            both += 1
        elif has_buy:
            buy_only += 1
        elif has_sell:
            sell_only += 1
        else:
            neither += 1
        extra = flags & ~KNOWN_MASK
        if extra:
            unknown_bits[extra] = unknown_bits.get(extra, 0) + 1

    print(f"  Total ticks          : {n}")
    print(f"  Trade-like ticks     : {tn} ({100.0 * tn / n:.1f}% of sample)")
    print(f"  BUY only (on trades) : {buy_only}")
    print(f"  SELL only (on trades): {sell_only}")
    print(f"  BUY+SELL same tick   : {both}")
    print(f"  Neither BUY nor SELL : {neither}")
    if unknown_bits:
        print("  Unknown flag bits on trades:")
        for bits, count in sorted(unknown_bits.items(), key=lambda x: -x[1])[:5]:
            print(f"    extra={bits} count={count}")

    shown = 0
    print("  Sample trade ticks:")
    for t in trade_rows[:8]:
        flags = int(_field(t, "flags", 0) or 0)
        print(
            f"    last={_field(t, 'last')} vol={_field(t, 'volume')} "
            f"flags={flags} ({_flag_names(flags)})"
        )
        shown += 1

    if tn == 0:
        verdict = "no_trades"
    elif buy_only + sell_only == 0:
        verdict = "no_buy_sell_flags"
    elif both > 0:
        verdict = "ambiguous_both_flags"
    elif neither > tn * 0.1:
        verdict = "partial_coverage"
    else:
        verdict = "buy_sell_present"

    coverage = (buy_only + sell_only) / tn if tn else 0.0
    print(f"  Aggressor mapping verdict: {verdict} (side-hint coverage {coverage:.1%})")
    return {
        "n": n,
        "trade_n": tn,
        "buy_only": buy_only,
        "sell_only": sell_only,
        "both": both,
        "neither": neither,
        "verdict": verdict,
        "coverage": coverage,
    }


def probe_symbol(root, sym: str, *, sample: int, lookback_mins: int) -> None:
    try:
        root.symbol_select(sym, True)
    except Exception as exc:
        print(f"symbol_select({sym}) failed: {exc}")

    snap_anchor_sec: int | None = None
    try:
        snap = root.symbol_info_tick(sym)
        if snap is not None:
            msc = _field(snap, "time_msc")
            if msc is not None and int(msc) > 0:
                snap_anchor_sec = int(int(msc) // 1000)
                fl = int(_field(snap, "flags", 0) or 0)
                print(
                    f"\n{sym} snapshot: bid={_field(snap, 'bid')} ask={_field(snap, 'ask')} "
                    f"last={_field(snap, 'last')} flags={fl} ({_flag_names(fl)})"
                )
    except Exception as exc:
        print(f"{sym} snapshot failed: {exc}")

    from_sec = (
        snap_anchor_sec - (lookback_mins * 60) if snap_anchor_sec else int((datetime.now(timezone.utc) - timedelta(minutes=lookback_mins)).timestamp())
    )
    try:
        ticks = root.copy_ticks_from(sym, from_sec, sample, COPY_TICKS_ALL)
        analyze_aggressor(
            f"{sym} copy_ticks_from (max {sample}, {lookback_mins}min, from {from_sec})",
            ticks,
        )
    except Exception as exc:
        print(f"{sym} copy_ticks_from FAILED: {exc}")


def main() -> int:
    host = os.environ.get("MT5_HOST", "127.0.0.1")
    port = int(os.environ.get("MT5_PORT", "18812"))
    sample = int(os.environ.get("HOMOLOG_PROBE_TICK_COUNT", "150"))
    lookback = int(os.environ.get("HOMOLOG_PROBE_LOOKBACK_MINS", "15"))

    print(f"Connecting RPyC {host}:{port} (sample={sample}, lookback={lookback}min) ...")
    conn = rpyc.connect(host, port, config={"sync_request_timeout": 120})
    root = conn.root

    if port == 18813:
        symbols = os.environ.get("HOMOLOG_PROBE_SYMBOLS", "WINQ26,WDOQ26,PETR4,DI1F27").split(",")
        symbols = [s.strip() for s in symbols if s.strip()]
        print(f"XP/B3 aggressor probe — {symbols}")
    else:
        symbols = os.environ.get("HOMOLOG_PROBE_SYMBOLS", "BTCUSD,USTEC").split(",")
        symbols = [s.strip() for s in symbols if s.strip()]
        print(f"Tickmill aggressor probe — {symbols}")

    for sym in symbols:
        probe_symbol(root, sym, sample=sample, lookback_mins=lookback)

    conn.close()
    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
