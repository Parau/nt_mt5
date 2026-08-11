"""
Probe real MT5 ticks for VOLUME-only trade rows (no TICK_FLAG_LAST).

Purpose:
    Audit whether ``COPY_TICKS_ALL`` / ``COPY_TICKS_TRADE`` contain rows where
    ``TICK_FLAG_VOLUME`` is set and ``TICK_FLAG_LAST`` is absent. Writes
    ``homologation/last_a05_volume_only_observation.json`` for review.

Usage (Windows CMD)::

    set MT5_HOST=127.0.0.1 && set MT5_PORT=18814 && ^
    set HOMOLOG_SYMBOL=ENQU26 && ^
    E:\\miniconda\\envs\\trading\\python.exe ^
        homologation\\tools\\probe_volume_only_observation.py

Optional env:
    HOMOLOG_LOOKBACK_HOURS (default 6)
    HOMOLOG_OUT (default homologation/last_a05_volume_only_observation.json)

``NOT OBSERVED`` is a valid outcome and must not be treated as a test failure.
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import rpyc

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nautilus_mt5.metatrader5.tick_transport import decode_mt5_ticks_frame
from nautilus_mt5.tick_routing import TICK_FLAG_LAST, TICK_FLAG_VOLUME

COPY_TICKS_ALL = 0
COPY_TICKS_TRADE = 2


def _load_ticks(root: object, symbol: str, start_i: int, end_i: int, flags: int):
    frame = root.copy_ticks_range(symbol, start_i, end_i, flags)
    if frame is None:
        return None
    if isinstance(frame, tuple):
        return decode_mt5_ticks_frame(frame)
    return frame


def _scan_volume_only(arr, source: str) -> list[dict]:
    if arr is None:
        return []
    found: list[dict] = []
    for t in arr:
        flags = int(t["flags"])
        if (flags & TICK_FLAG_VOLUME) and not (flags & TICK_FLAG_LAST):
            found.append(
                {
                    "source": source,
                    "time_msc": int(t["time_msc"]),
                    "last": float(t["last"]),
                    "volume": int(t["volume"]),
                    "volume_real": float(t["volume_real"]),
                    "flags": flags,
                    "bid": float(t["bid"]),
                    "ask": float(t["ask"]),
                },
            )
    return found


def main() -> int:
    host = os.environ.get("MT5_HOST", "127.0.0.1")
    port = int(os.environ.get("MT5_PORT", "18814"))
    symbol = os.environ.get("HOMOLOG_SYMBOL", "ENQU26")
    lookback_h = float(os.environ.get("HOMOLOG_LOOKBACK_HOURS", "6"))
    out_path = Path(
        os.environ.get(
            "HOMOLOG_OUT",
            str(ROOT / "homologation" / "last_a05_volume_only_observation.json"),
        ),
    )

    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=lookback_h)
    start_i = int(start.timestamp())
    end_i = int(end.timestamp())

    print(f"Connecting RPyC {host}:{port} symbol={symbol} lookback_h={lookback_h} ...")
    conn = rpyc.connect(host, port, config={"sync_request_timeout": 120})
    root = conn.root
    try:
        root.symbol_select(symbol, True)
        all_arr = _load_ticks(root, symbol, start_i, end_i, COPY_TICKS_ALL)
        trade_arr = _load_ticks(root, symbol, start_i, end_i, COPY_TICKS_TRADE)
    finally:
        conn.close()

    vo_all = _scan_volume_only(all_arr, "COPY_TICKS_ALL")
    vo_trade = _scan_volume_only(trade_arr, "COPY_TICKS_TRADE")

    trade_keys = {
        (r["time_msc"], r["flags"], r["volume"], r["last"]) for r in vo_trade
    }
    for row in vo_all:
        row["in_COPY_TICKS_TRADE"] = (
            row["time_msc"],
            row["flags"],
            row["volume"],
            row["last"],
        ) in trade_keys

    hist: Counter[tuple[bool, bool]] = Counter()
    if trade_arr is not None:
        for t in trade_arr:
            fl = int(t["flags"])
            hist[(bool(fl & TICK_FLAG_LAST), bool(fl & TICK_FLAG_VOLUME))] += 1

    observed = bool(vo_all or vo_trade)
    status = "OBSERVED" if observed else "NOT OBSERVED"
    report = {
        "purpose": (
            "real-provider VOLUME-only observation "
            "(TICK_FLAG_VOLUME without TICK_FLAG_LAST)"
        ),
        "probe": "homologation/tools/probe_volume_only_observation.py",
        "symbol": symbol,
        "mt5_host": host,
        "mt5_port": port,
        "window_utc": [start.isoformat(), end.isoformat()],
        "all_count": 0 if all_arr is None else int(len(all_arr)),
        "trade_count": 0 if trade_arr is None else int(len(trade_arr)),
        "trade_LAST_VOLUME_cooccurrence": {
            f"LAST={k[0]}_VOLUME={k[1]}": int(v) for k, v in sorted(hist.items())
        },
        "volume_only_in_ALL": len(vo_all),
        "volume_only_in_TRADE": len(vo_trade),
        "samples": (vo_trade or vo_all)[:10],
        "status": status,
        "real_provider_VOLUME_only_observation": status,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": status,
                "all_count": report["all_count"],
                "trade_count": report["trade_count"],
                "volume_only_in_ALL": report["volume_only_in_ALL"],
                "volume_only_in_TRADE": report["volume_only_in_TRADE"],
                "out": str(out_path),
            },
            indent=2,
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
