"""
One-off probe: MT5 tick last/flags semantics via RPyC (no adapter changes).

Usage (Windows CMD):
    set MT5_HOST=127.0.0.1 && set MT5_PORT=18812 && ^
    E:\\miniconda\\envs\\trading\\python.exe homologation\\tools\\probe_tick_semantics.py
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


def _field(obj, name, default=None):
    """Avoid getattr(obj, 'flags') on numpy void — shadows TICK flags field."""
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
    return "|".join(parts) if parts else "NONE"


def analyze_ticks(label: str, ticks) -> None:
    print(f"\n{'=' * 72}")
    print(f"  {label}")
    print(f"{'=' * 72}")

    if ticks is None:
        print("  ERROR: returned None")
        return
    rows = list(_iter_ticks(ticks))
    n = len(rows)
    if n == 0:
        print("  WARNING: 0 ticks (market closed, no history, or wrong window)")
        return

    with_last_flag = 0
    with_last_price = 0
    with_volume_flag = 0
    bid_ask_only = 0
    flag_counts: dict[int, int] = {}

    for t in rows:
        flags = int(_field(t, "flags", 0) or 0)
        last = float(_field(t, "last", 0) or 0)
        flag_counts[flags] = flag_counts.get(flags, 0) + 1

        if flags & TICK_FLAG_LAST:
            with_last_flag += 1
        if last > 0:
            with_last_price += 1
        if flags & TICK_FLAG_VOLUME:
            with_volume_flag += 1
        if (flags & (TICK_FLAG_BID | TICK_FLAG_ASK)) and not (flags & TICK_FLAG_LAST):
            bid_ask_only += 1

    print(f"  Total ticks     : {n}")
    print(f"  TICK_FLAG_LAST  : {with_last_flag} ({100.0 * with_last_flag / n:.1f}%)")
    print(f"  last > 0        : {with_last_price} ({100.0 * with_last_price / n:.1f}%)")
    print(f"  TICK_FLAG_VOLUME: {with_volume_flag} ({100.0 * with_volume_flag / n:.1f}%)")
    print(f"  bid/ask only    : {bid_ask_only} ({100.0 * bid_ask_only / n:.1f}%)")
    print("  Top flag values :")
    for flags, count in sorted(flag_counts.items(), key=lambda x: -x[1])[:8]:
        print(f"    flags={flags:3d} ({_flag_names(flags):12s}) count={count}")

    print("  Sample ticks with LAST flag or last>0:")
    shown = 0
    for t in rows:
        flags = int(_field(t, "flags", 0) or 0)
        last = float(_field(t, "last", 0) or 0)
        if (flags & TICK_FLAG_LAST) or last > 0:
            print(
                f"    time_msc={_field(t, 'time_msc')} bid={_field(t, 'bid')} "
                f"ask={_field(t, 'ask')} last={last} vol={_field(t, 'volume')} "
                f"flags={flags} ({_flag_names(flags)})"
            )
            shown += 1
            if shown >= 5:
                break
    if shown == 0:
        print("    (none)")

    print("  Sample bid/ask-only ticks (flags=2/4/6):")
    shown = 0
    for t in rows:
        flags = int(_field(t, "flags", 0) or 0)
        if flags in (2, 4, 6) and not (flags & TICK_FLAG_LAST):
            print(
                f"    time_msc={_field(t, 'time_msc')} bid={_field(t, 'bid')} "
                f"ask={_field(t, 'ask')} last={_field(t, 'last')} flags={flags}"
            )
            shown += 1
            if shown >= 3:
                break


def main() -> int:
    host = os.environ.get("MT5_HOST", "127.0.0.1")
    port = int(os.environ.get("MT5_PORT", "18812"))

    print(f"Connecting RPyC {host}:{port} ...")
    conn = rpyc.connect(host, port)
    root = conn.root

    for sym in ("USTEC", "BTCUSD"):
        try:
            ok = root.symbol_select(sym, True)
            print(f"symbol_select({sym}) -> {ok}")
        except Exception as exc:
            print(f"symbol_select({sym}) failed: {exc}")

    # USTEC: Friday 2026-06-26, US open ~10:30 BRT = 13:30 UTC, 1 hour window
    ustec_from = int(datetime(2026, 6, 26, 13, 30, tzinfo=timezone.utc).timestamp())
    ustec_to = int(datetime(2026, 6, 26, 14, 30, tzinfo=timezone.utc).timestamp())
    ustec_hist = None
    try:
        ustec_hist = root.copy_ticks_range("USTEC", ustec_from, ustec_to, COPY_TICKS_ALL)
        analyze_ticks(
            f"USTEC historical Fri 2026-06-26 13:30-14:30 UTC (unix {ustec_from}-{ustec_to})",
            ustec_hist,
        )
    except Exception as exc:
        print(f"\nUSTEC historical FAILED: {exc}")

    if ustec_hist is not None and len(ustec_hist) == 0:
        ustec_to3 = int(datetime(2026, 6, 26, 16, 30, tzinfo=timezone.utc).timestamp())
        try:
            ustec_hist3 = root.copy_ticks_range("USTEC", ustec_from, ustec_to3, COPY_TICKS_ALL)
            analyze_ticks(
                "USTEC historical Fri 2026-06-26 13:30-16:30 UTC (wider window)",
                ustec_hist3,
            )
        except Exception as exc:
            print(f"\nUSTEC wider window FAILED: {exc}")

    try:
        btc_hist = root.copy_ticks_range("BTCUSD", ustec_from, ustec_to, COPY_TICKS_ALL)
        analyze_ticks(
            "BTCUSD historical Fri 2026-06-26 13:30-14:30 UTC",
            btc_hist,
        )
    except Exception as exc:
        print(f"\nBTCUSD historical FAILED: {exc}")

    now = datetime.now(timezone.utc)
    live_from = int((now - timedelta(minutes=30)).timestamp())
    try:
        btc_live = root.copy_ticks_from("BTCUSD", live_from, 5000, COPY_TICKS_ALL)
        analyze_ticks(
            f"BTCUSD live copy_ticks_from last 30min (from unix {live_from}, max 5000)",
            btc_live,
        )
    except Exception as exc:
        print(f"\nBTCUSD live FAILED: {exc}")

    try:
        snap = root.symbol_info_tick("BTCUSD")
        print(f"\n{'=' * 72}")
        print("  BTCUSD symbol_info_tick (snapshot now)")
        print(f"{'=' * 72}")
        if snap:
            fl = _field(snap, "flags")
            if fl is None:
                fl = getattr(snap, "flags", None)
            print(
                f"  bid={_field(snap, 'bid')} ask={_field(snap, 'ask')} "
                f"last={_field(snap, 'last')} volume={_field(snap, 'volume')} "
                f"time_msc={_field(snap, 'time_msc')} flags={fl}"
            )
        else:
            print("  None")
    except Exception as exc:
        print(f"\nBTCUSD snapshot FAILED: {exc}")

    conn.close()
    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
