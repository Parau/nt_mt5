"""
Live smoke: resolve_volume_capability + tick helpers against real XP symbols.

Usage (Windows CMD):
    set MT5_HOST=127.0.0.1 && set MT5_PORT=18813 && set VENUE_PROFILE=xp && ^
    E:\\miniconda\\envs\\trading\\python.exe homologation\\tools\\volume_capability_smoke.py
"""
from __future__ import annotations

import os
import sys

import rpyc
from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.enums import AggressorSide
from nautilus_trader.model.identifiers import TradeId

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from nautilus_mt5 import XP_B3_PROFILE
from nautilus_mt5.data_types import MT5Symbol
from nautilus_mt5.metatrader5.models import Symbol as Mt5WireSymbol
from nautilus_mt5.parsing.instruments import convert_symbol_info_to_mt5_symbol_details, parse_instrument
from nautilus_mt5.parsing.tick_volume import resolve_trade_tick_size
from nautilus_mt5.volume_capability import (
    financial_notional_from_tick,
    resolve_volume_capability,
    trade_qty_from_tick,
)

COPY_TICKS_ALL = 0
DEFAULT_SYMBOLS = ("WINQ26", "PETR4", "DI1F27")


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


def smoke_symbol(root, symbol: str) -> bool:
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
    instrument = parse_instrument(details, venue_profile=XP_B3_PROFILE)
    cap = resolve_volume_capability(instrument, XP_B3_PROFILE)

    print(f"  type={cap.instrument_type}")
    print(f"  calc_mode={cap.calc_mode}")
    print(f"  trade_qty={cap.trade_qty} (status={cap.trade_ticks_status.value})")
    print(f"  financial_notional={cap.financial_notional} (mode={cap.notional_mode!r})")
    print(f"  bar_volume_activity_only={cap.bar_volume_activity_only}")

    snap = root.symbol_info_tick(symbol)
    from_sec = int(_row_field(snap, "time", 0)) - 3600 if snap else 0
    ticks = root.copy_ticks_from(symbol, from_sec, 50, COPY_TICKS_ALL)
    if ticks is None:
        print("  WARN: no ticks in last hour")
        return True

    n = len(ticks)
    sample_tick: TradeTick | None = None
    for i in range(n):
        row = ticks[i]
        last = float(_row_field(row, "last", 0) or 0)
        if last <= 0:
            continue
        vol = float(_row_field(row, "volume", 0) or 0)
        vr = float(_row_field(row, "volume_real", 0) or 0)
        size = resolve_trade_tick_size(vol, vr)
        if size is None:
            continue
        sample_tick = TradeTick(
            instrument_id=instrument.id,
            price=instrument.make_price(last),
            size=instrument.make_qty(size),
            aggressor_side=AggressorSide.NO_AGGRESSOR,
            trade_id=TradeId(str(i)),
            ts_event=1_000_000_000,
            ts_init=1_000_000_000,
        )
        qty = trade_qty_from_tick(cap, sample_tick)
        notional = financial_notional_from_tick(instrument, cap, sample_tick)
        print(f"  sample qty={qty} notional={notional}")
        break

    if sample_tick is None:
        print("  WARN: no resolvable trade size in sample")
    return True


def main() -> int:
    host = os.environ.get("MT5_HOST", "127.0.0.1")
    port = int(os.environ.get("MT5_PORT", "18813"))
    symbols = sys.argv[1:] or list(DEFAULT_SYMBOLS)
    print(f"Connecting RPyC {host}:{port} profile=xp-b3")
    conn = rpyc.connect(host, port)
    root = conn.root
    ok = all(smoke_symbol(root, sym) for sym in symbols)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
