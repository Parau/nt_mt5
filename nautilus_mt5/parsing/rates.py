"""MT5 native rate (MqlRates) parsing helpers."""
from __future__ import annotations

import datetime
from typing import Any

import pandas as pd

from nautilus_trader.model.data import BarAggregation
from nautilus_trader.model.data import BarSpecification

from nautilus_mt5.data_types import BarData


def bar_spec_to_mt5_timeframe(bar_spec: BarSpecification) -> int:
    """
    Map a Nautilus bar spec to the MT5 ``ENUM_TIMEFRAMES`` integer.

    Values match ``MetaTrader5.TIMEFRAME_*`` constants on the RPyC wrapper.
    """
    aggregation = bar_spec.aggregation
    step = bar_spec.step
    if aggregation == BarAggregation.SECOND:
        if step == 60:
            return 1  # no native 60s; callers should reject sub-minute specs
        raise ValueError(f"MT5 copy_rates does not support second bar spec {bar_spec!r}")
    if aggregation == BarAggregation.MINUTE:
        mapping = {
            1: 1,
            2: 2,
            3: 3,
            4: 4,
            5: 5,
            6: 6,
            10: 10,
            12: 12,
            15: 15,
            20: 20,
            30: 30,
        }
        tf = mapping.get(step)
        if tf is not None:
            return tf
    elif aggregation == BarAggregation.HOUR:
        mapping = {1: 16385, 2: 16386, 3: 16387, 4: 16388, 6: 16390, 8: 16392, 12: 16396}
        tf = mapping.get(step)
        if tf is not None:
            return tf
    elif aggregation == BarAggregation.DAY and step == 1:
        return 16408
    elif aggregation == BarAggregation.WEEK and step == 1:
        return 32769
    elif aggregation == BarAggregation.MONTH and step == 1:
        return 49153
    raise ValueError(f"MT5 copy_rates does not support bar spec {bar_spec!r}")


def ib_duration_to_timedelta(duration: str) -> datetime.timedelta:
    """Parse IB-style duration strings (``7 D``, ``30 S``, …) used by legacy request paths."""
    parts = duration.strip().split()
    if len(parts) != 2:
        return datetime.timedelta(days=7)
    try:
        count = int(parts[0])
    except ValueError:
        return datetime.timedelta(days=7)
    unit = parts[1].upper()
    if unit == "S":
        return datetime.timedelta(seconds=count)
    if unit == "W":
        return datetime.timedelta(weeks=count)
    if unit == "M":
        return datetime.timedelta(days=30 * count)
    if unit == "Y":
        return datetime.timedelta(days=365 * count)
    return datetime.timedelta(days=count)


def timestamp_to_utc_datetime(ts: pd.Timestamp) -> datetime.datetime:
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts.to_pydatetime()


def rate_row_field(row: Any, name: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(name, default)
    try:
        return row[name]
    except (TypeError, KeyError, IndexError, ValueError):
        return getattr(row, name, default)


def mql_rate_row_to_bar_data(symbol: str, row: Any) -> BarData:
    """Convert one MT5 rate row (dict or structured array element) to ``BarData``."""
    tick_volume = rate_row_field(row, "tick_volume", 0) or 0
    real_volume = rate_row_field(row, "real_volume", 0) or 0
    volume = int(tick_volume if tick_volume else real_volume)
    return BarData(
        symbol=symbol,
        time=int(rate_row_field(row, "time", 0)),
        open=float(rate_row_field(row, "open", 0.0)),
        high=float(rate_row_field(row, "high", 0.0)),
        low=float(rate_row_field(row, "low", 0.0)),
        close=float(rate_row_field(row, "close", 0.0)),
        volume=volume,
        complete=True,
    )
