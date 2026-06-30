"""Unit tests for MQL5 bridge history argument normalization."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

_BRIDGE_DIR = Path(__file__).resolve().parents[2] / "MQL5" / "refactoring" / "bridge"
if str(_BRIDGE_DIR) not in sys.path:
    sys.path.insert(0, str(_BRIDGE_DIR))

from history_args import (
    coerce_tick_time,
    coerce_unix_timestamp,
    normalize_history_interval_args,
)


def test_coerce_unix_from_int():
    assert coerce_unix_timestamp(1782654517) == 1782654517


def test_coerce_unix_from_utc_datetime():
    ts = dt.datetime(2026, 6, 28, 13, 0, 0, tzinfo=dt.timezone.utc)
    assert coerce_unix_timestamp(ts) == int(ts.timestamp())


def test_coerce_unix_from_naive_datetime_as_utc():
    ts = dt.datetime(2026, 6, 28, 13, 0, 0)
    expected = int(ts.replace(tzinfo=dt.timezone.utc).timestamp())
    assert coerce_unix_timestamp(ts) == expected


def test_normalize_interval_converts_datetimes():
    start = dt.datetime(2026, 6, 28, 11, 0, 0, tzinfo=dt.timezone.utc)
    end = dt.datetime(2026, 6, 28, 13, 0, 0, tzinfo=dt.timezone.utc)
    args, kwargs = normalize_history_interval_args(start, end, group="*BTCUSD*")
    assert args == (int(start.timestamp()), int(end.timestamp()))
    assert kwargs == {"group": "*BTCUSD*"}


def test_normalize_interval_passes_unix_through():
    args, kwargs = normalize_history_interval_args(0, 1782654517, group="*BTCUSD*")
    assert args == (0, 1782654517)
    assert kwargs == {"group": "*BTCUSD*"}


def test_normalize_ticket_query_unchanged():
    args, kwargs = normalize_history_interval_args(ticket=264631868)
    assert args == ()
    assert kwargs == {"ticket": 264631868}


def test_normalize_position_query_unchanged():
    args, kwargs = normalize_history_interval_args(position=226858998)
    assert args == ()
    assert kwargs == {"position": 226858998}


def test_coerce_tick_time_datetime():
    ts = dt.datetime(2026, 6, 28, 13, 0, 0, tzinfo=dt.timezone.utc)
    assert coerce_tick_time(ts) == int(ts.timestamp())


def test_coerce_tick_time_int_passthrough():
    assert coerce_tick_time(1782654517) == 1782654517


def test_coerce_unix_rejects_bool():
    with pytest.raises(TypeError):
        coerce_unix_timestamp(True)
