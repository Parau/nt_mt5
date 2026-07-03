"""
Live smoke: instrument multiplier + TradeTick notional via RPyC (no WS required).

Usage (Windows CMD):
    set MT5_HOST=127.0.0.1 && set MT5_PORT=18814 && set VENUE_PROFILE=amp && ^
    E:\\miniconda\\envs\\trading\\python.exe homologation\\tools\\notional_live_smoke.py MESU26

    set MT5_PORT=18812 && set VENUE_PROFILE=tickmill && ^
    E:\\miniconda\\envs\\trading\\python.exe homologation\\tools\\notional_live_smoke.py BTCUSD USTEC
"""
from __future__ import annotations

import os
import sys

import rpyc

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from nautilus_mt5 import AMP_US_PROFILE, TICKMILL_DEMO_PROFILE, XP_B3_PROFILE
from nautilus_mt5.venue_profile import VenueProfile
from nautilus_mt5.data_types import MT5Symbol, MT5SymbolDetails
from nautilus_mt5.metatrader5.models import Symbol as Mt5WireSymbol
from nautilus_mt5.parsing.instruments import convert_symbol_info_to_mt5_symbol_details, parse_instrument
from nautilus_mt5.parsing.tick_volume import resolve_trade_tick_size

COPY_TICKS_ALL = 0


def _resolve_profile() -> VenueProfile:
    key = (os.environ.get("VENUE_PROFILE") or "xp").strip().lower()
    if key in ("amp", "amp_us", "amp_us_profile"):
        return AMP_US_PROFILE
    if key in ("tickmill", "tickmill_demo", "tickmill-demo"):
        return TICKMILL_DEMO_PROFILE
    return XP_B3_PROFILE


def _expect_notional(inst) -> bool:
    """Whether strategy should use notional_value for this instrument."""
    return inst.info.get("notional_mode") == "linear_price_multiplier"


def _normalize_symbol_info(info, symbol: str):
    if hasattr(info, "_asdict"):
        info_dict = info._asdict()
    elif hasattr(info, "__dict__"):
        info_dict = info.__dict__.copy()
    else:
        info_dict = dict(info)
    if "name" not in info_dict:
        info_dict["name"] = symbol
    if "under_sec_type" not in info_dict:
        raw_path = info_dict.get("path") or ""
        info_dict["under_sec_type"] = raw_path.split("\\")[0].upper() if raw_path else None
    if "symbol" not in info_dict or info_dict["symbol"] is None:
        info_dict["symbol"] = Mt5WireSymbol(symbol=symbol)

    class _NormalizedInfo:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    return _NormalizedInfo(**info_dict)


def _row_field(row, name: str, default=0):
    if hasattr(row, "dtype"):
        return row[name] if name in row.dtype.names else default
    if isinstance(row, dict):
        return row.get(name, default)
    return getattr(row, name, default)


def smoke_symbol(root, symbol: str, profile: VenueProfile) -> bool:
    print(f"\n{'=' * 60}\n  {symbol}\n{'=' * 60}")
    if not root.symbol_select(symbol, True):
        print("  FAIL: symbol_select returned False")
        return False

    info = root.symbol_info(symbol)
    if info is None:
        print("  FAIL: symbol_info returned None")
        return False

    normalized = _normalize_symbol_info(info, symbol)
    details = convert_symbol_info_to_mt5_symbol_details(normalized)
    if isinstance(details.symbol, str):
        details = details.model_copy(update={"symbol": MT5Symbol(symbol=details.symbol)})
    elif details.symbol is None or not getattr(details.symbol, "symbol", None):
        details = details.model_copy(update={"symbol": MT5Symbol(symbol=symbol)})
    inst = parse_instrument(details, venue_profile=profile)

    print(f"  type={type(inst).__name__}")
    print(f"  multiplier={float(inst.multiplier)}")
    print(f"  notional_mode={inst.info.get('notional_mode')}")
    print(f"  expect_notional={_expect_notional(inst)}")

    snap = root.symbol_info_tick(symbol)
    if snap is None:
        print("  WARN: no symbol_info_tick snapshot")
        from_sec = 0
    else:
        from_sec = int(_row_field(snap, "time", 0)) - 3600

    ticks = root.copy_ticks_from(symbol, from_sec, 200, COPY_TICKS_ALL)
    if ticks is None:
        n = 0
        tick_rows = []
    else:
        n = len(ticks)
        tick_rows = [ticks[i] for i in range(n)]
    print(f"  copy_ticks_from: {n} rows (last 1h)")

    trade_count = 0
    for row in tick_rows:
        last = float(_row_field(row, "last", 0) or 0)
        if last <= 0:
            continue
        vol = float(_row_field(row, "volume", 0) or 0)
        vr = float(_row_field(row, "volume_real", 0) or 0)
        size = resolve_trade_tick_size(vol, vr)
        if size is None:
            continue
        trade_count += 1
        if trade_count <= 3 and _expect_notional(inst):
            notional = inst.notional_value(inst.make_qty(size), inst.make_price(last))
            print(
                f"  trade sample: last={last} vol={vol} vr={vr} "
                f"size={size} notional={float(notional.as_double()):.2f} {notional.currency}"
            )
        elif trade_count <= 3 and not _expect_notional(inst):
            print(
                f"  trade sample (no notional): last={last} vol={vol} vr={vr} size={size}"
            )

    print(f"  trades_with_resolvable_size: {trade_count}")
    if _expect_notional(inst) and trade_count == 0:
        print("  WARN: no trade ticks with volume in window (market closed or no prints?)")
    if not _expect_notional(inst) and inst.info.get("notional_mode") == "linear_price_multiplier":
        print("  FAIL: unexpected linear_price_multiplier for this venue/symbol")
        return False
    return True


def main() -> int:
    host = os.environ.get("MT5_HOST", "127.0.0.1")
    port = int(os.environ.get("MT5_PORT", "18813"))
    profile = _resolve_profile()
    symbols = sys.argv[1:]
    if not symbols:
        if profile is AMP_US_PROFILE:
            symbols = ["MESU26", "ENQU26", "MNQU26", "EPU26"]
        elif profile is TICKMILL_DEMO_PROFILE:
            symbols = ["BTCUSD", "USTEC"]
        else:
            symbols = ["WINQ26", "WDON26", "PETR4", "DI1F27"]

    print(f"Connecting RPyC {host}:{port} profile={profile.name}")
    conn = rpyc.connect(host, port)
    root = conn.root

    ok = all(smoke_symbol(root, sym, profile) for sym in symbols)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
