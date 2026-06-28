import datetime

import pandas as pd
import pytest

from nautilus_trader.model.data import BarSpecification
from nautilus_trader.model.enums import BarAggregation, PriceType

from nautilus_mt5.parsing.rates import (
    bar_spec_to_mt5_timeframe,
    ib_duration_to_timedelta,
    mql_rate_row_to_bar_data,
    timestamp_to_utc_datetime,
)


def test_bar_spec_to_mt5_timeframe_m1():
    spec = BarSpecification(1, BarAggregation.MINUTE, PriceType.LAST)
    assert bar_spec_to_mt5_timeframe(spec) == 1


def test_bar_spec_to_mt5_timeframe_h1():
    spec = BarSpecification(1, BarAggregation.HOUR, PriceType.LAST)
    assert bar_spec_to_mt5_timeframe(spec) == 16385


def test_bar_spec_to_mt5_timeframe_unsupported():
    spec = BarSpecification(5, BarAggregation.SECOND, PriceType.LAST)
    with pytest.raises(ValueError, match="does not support"):
        bar_spec_to_mt5_timeframe(spec)


@pytest.mark.parametrize(
    ("duration", "expected"),
    [
        ("7 D", datetime.timedelta(days=7)),
        ("30 S", datetime.timedelta(seconds=30)),
        ("2 W", datetime.timedelta(weeks=2)),
        ("1 M", datetime.timedelta(days=30)),
        ("1 Y", datetime.timedelta(days=365)),
        ("bad", datetime.timedelta(days=7)),
    ],
)
def test_ib_duration_to_timedelta(duration, expected):
    assert ib_duration_to_timedelta(duration) == expected


def test_mql_rate_row_to_bar_data_from_dict():
    row = {
        "time": 1700000000,
        "open": 100.0,
        "high": 110.0,
        "low": 90.0,
        "close": 105.0,
        "tick_volume": 42,
        "real_volume": 0,
    }
    bar = mql_rate_row_to_bar_data("USTEC", row)
    assert bar.symbol == "USTEC"
    assert bar.time == 1700000000
    assert bar.open == 100.0
    assert bar.volume == 42
    assert bar.complete is True


def test_timestamp_to_utc_datetime_naive():
    ts = pd.Timestamp("2023-11-14 12:00:00")
    dt = timestamp_to_utc_datetime(ts)
    assert dt.tzinfo is not None
    assert dt.tzinfo.utcoffset(dt) == datetime.timedelta(0)
