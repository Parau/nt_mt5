"""Fast tick semantics probe — limited samples to avoid huge RPyC transfers."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import rpyc

TICK_FLAG_BID = 2
TICK_FLAG_ASK = 4
TICK_FLAG_LAST = 8
TICK_FLAG_VOLUME = 16


def field(o, n, d=None):
    if isinstance(o, dict):
        return o.get(n, d)
    try:
        return o[n]
    except (TypeError, KeyError, IndexError, ValueError):
        return getattr(o, n, d) if n != "flags" else d


def stats(label: str, ticks) -> None:
    if ticks is None or len(ticks) == 0:
        print(f"=== {label} === EMPTY")
        return
    n = len(ticks)
    last_f = last_p = vol_f = ba_only = 0
    fc: dict[int, int] = {}
    for i in range(n):
        t = ticks[i]
        fl = int(field(t, "flags", 0) or 0)
        la = float(field(t, "last", 0) or 0)
        fc[fl] = fc.get(fl, 0) + 1
        if fl & TICK_FLAG_LAST:
            last_f += 1
        if la > 0:
            last_p += 1
        if fl & TICK_FLAG_VOLUME:
            vol_f += 1
        if (fl & (TICK_FLAG_BID | TICK_FLAG_ASK)) and not (fl & TICK_FLAG_LAST):
            ba_only += 1
    print(f"=== {label} n={n} ===")
    print(f"  LAST flag: {last_f} ({100 * last_f / n:.1f}%)  last>0: {last_p} ({100 * last_p / n:.1f}%)")
    print(f"  VOL flag:  {vol_f} ({100 * vol_f / n:.1f}%)  bid/ask-only: {ba_only} ({100 * ba_only / n:.1f}%)")
    print(f"  top flags: {sorted(fc.items(), key=lambda x: -x[1])[:6]}")
    shown = 0
    for i in range(n):
        t = ticks[i]
        fl = int(field(t, "flags", 0) or 0)
        la = float(field(t, "last", 0) or 0)
        if (fl & TICK_FLAG_LAST) or la > 0:
            print(
                f"  sample: msc={field(t, 'time_msc')} bid={field(t, 'bid')} "
                f"ask={field(t, 'ask')} last={la} vol={field(t, 'volume')} flags={fl}"
            )
            shown += 1
            if shown >= 3:
                break
    if shown == 0:
        print("  (no ticks with LAST flag or last>0)")


def main() -> None:
    host = os.environ.get("MT5_HOST", "127.0.0.1")
    port = int(os.environ.get("MT5_PORT", "18812"))
    conn = rpyc.connect(host, port)
    r = conn.root
    r.symbol_select("USTEC", True)
    r.symbol_select("BTCUSD", True)

    fri_open = int(datetime(2026, 6, 26, 13, 30, tzinfo=timezone.utc).timestamp())
    # First 5000 ticks from Friday open (same window as copy_ticks_range start)
    stats("USTEC Fri 13:30 UTC — first 5000 ticks (copy_ticks_from)", r.copy_ticks_from("USTEC", fri_open, 5000, 0))

    live_from = int((datetime.now(timezone.utc) - timedelta(minutes=30)).timestamp())
    stats("BTCUSD live — first 3000 ticks last 30min", r.copy_ticks_from("BTCUSD", live_from, 3000, 0))

    snap = r.symbol_info_tick("BTCUSD")
    print(
        "BTCUSD snapshot now:",
        f"bid={field(snap, 'bid')} ask={field(snap, 'ask')}",
        f"last={field(snap, 'last')} flags={getattr(snap, 'flags', field(snap, 'flags'))}",
    )
    conn.close()


if __name__ == "__main__":
    main()
