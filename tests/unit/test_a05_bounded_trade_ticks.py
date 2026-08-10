"""
A05 bounded historical TradeTick unit coverage.

Purpose/Single Responsibility:
    Deterministic proofs for constant resolution, provider envelope, materialization,
    empty success vs None failure, filtering, and multiplicity.

Data Flow & Dependencies:
    Exercises ``_resolve_mt5_constant`` and ``get_historical_trade_ticks_range`` with
    stub MT5 surfaces and NumPy fixtures; uses XP WIN$ instrument fixture.

Premises & Limitations:
    No live terminal. LOCAL_PYTHON constant fallback is simulated with a thin
    wrapper that only exposes ``get_constant``.
"""
from __future__ import annotations

import json
import pathlib
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from nautilus_mt5.client.errors import MT5HistoricalDataError
from nautilus_mt5.client.market_data import (
    MetaTrader5ClientMarketDataMixin,
    _resolve_mt5_constant,
)
from nautilus_mt5.data_types import MT5Symbol, MT5SymbolDetails
from nautilus_mt5.feed.converter import wire_tick_to_trade_tick
from nautilus_mt5.feed.messages import WireTick
from nautilus_mt5.parsing.instruments import parse_instrument
from nautilus_mt5.tick_routing import route_wire_tick
from nautilus_mt5.venue_profile import XP_B3_PROFILE
from tests.support.fake_mt5_rpyc_bridge import MT5_TICK_DTYPE, _make_tick_array

_TEST_DATA = pathlib.Path(__file__).parent.parent / "test_data"


def _win_dollar_instrument():
    data = json.loads((_TEST_DATA / "symbol_info_win_dollar.json").read_text())
    data.pop("_comment", None)
    data["symbol"] = MT5Symbol(**data["symbol"])
    details = MT5SymbolDetails(**data)
    return parse_instrument(details, venue_profile=XP_B3_PROFILE)


class _BoundedHelperHost(MetaTrader5ClientMarketDataMixin):
    """Minimal host for exercising the A05 mixin helper."""

    def __init__(self, mt5: Any) -> None:
        self._mt5_client = {"mt5": mt5}
        self._clock = MagicMock()
        self._clock.timestamp_ns.return_value = 1_700_000_000_000_000_000
        self._log = MagicMock()
        self._cache = MagicMock()


def test_resolve_constant_direct_attribute() -> None:
    mt5 = SimpleNamespace(COPY_TICKS_TRADE=2)
    assert _resolve_mt5_constant(mt5, "COPY_TICKS_TRADE") == 2


def test_resolve_constant_get_constant_fallback() -> None:
    class LocalLike:
        def get_constant(self, name: str) -> Any:
            return {"COPY_TICKS_TRADE": 2}.get(name)

    assert _resolve_mt5_constant(LocalLike(), "COPY_TICKS_TRADE") == 2


def test_resolve_constant_missing_raises() -> None:
    with pytest.raises(MT5HistoricalDataError, match="does not expose"):
        _resolve_mt5_constant(SimpleNamespace(), "COPY_TICKS_TRADE")


def test_resolve_constant_get_constant_error_wraps() -> None:
    class Broken:
        def get_constant(self, name: str) -> Any:
            raise RuntimeError("boom")

    with pytest.raises(MT5HistoricalDataError, match="get_constant"):
        _resolve_mt5_constant(Broken(), "COPY_TICKS_TRADE")


def test_resolve_constant_never_uses_literal_two_as_fallback() -> None:
    """Absence of the named constant must fail — not substitute enum value 2."""
    with pytest.raises(MT5HistoricalDataError):
        _resolve_mt5_constant(SimpleNamespace(COPY_TICKS_ALL=0), "COPY_TICKS_TRADE")


@pytest.mark.asyncio
async def test_empty_ndarray_is_success() -> None:
    raw = np.zeros(0, dtype=MT5_TICK_DTYPE)
    mt5 = SimpleNamespace(
        COPY_TICKS_TRADE=2,
        copy_ticks_range=MagicMock(return_value=raw),
        last_error=MagicMock(return_value=(0, "OK")),
    )
    host = _BoundedHelperHost(mt5)
    instrument = _win_dollar_instrument()
    start = pd.Timestamp("2023-11-14 22:13:20", tz="UTC")
    end = pd.Timestamp("2023-11-14 22:13:21", tz="UTC")

    ticks = await host.get_historical_trade_ticks_range(
        symbol=MT5Symbol(symbol="WIN$"),
        instrument=instrument,
        start_date_time=start,
        end_date_time=end,
        map_tick_flags_to_aggressor=True,
    )
    assert ticks == []
    mt5.copy_ticks_range.assert_called_once()
    args = mt5.copy_ticks_range.call_args[0]
    assert args[3] == 2


@pytest.mark.asyncio
async def test_none_is_failure_not_empty_success() -> None:
    mt5 = SimpleNamespace(
        COPY_TICKS_TRADE=2,
        copy_ticks_range=MagicMock(return_value=None),
        last_error=MagicMock(return_value=(-1, "ERR")),
    )
    host = _BoundedHelperHost(mt5)
    instrument = _win_dollar_instrument()
    start = pd.Timestamp("2023-11-14 22:13:20", tz="UTC")
    end = pd.Timestamp("2023-11-14 22:13:21", tz="UTC")

    with pytest.raises(MT5HistoricalDataError, match="returned None"):
        await host.get_historical_trade_ticks_range(
            symbol=MT5Symbol(symbol="WIN$"),
            instrument=instrument,
            start_date_time=start,
            end_date_time=end,
            map_tick_flags_to_aggressor=False,
        )


@pytest.mark.asyncio
async def test_provider_exception_raises() -> None:
    mt5 = SimpleNamespace(
        COPY_TICKS_TRADE=2,
        copy_ticks_range=MagicMock(side_effect=RuntimeError("transport")),
    )
    host = _BoundedHelperHost(mt5)
    instrument = _win_dollar_instrument()
    start = pd.Timestamp("2023-11-14 22:13:20", tz="UTC")
    end = pd.Timestamp("2023-11-14 22:13:21", tz="UTC")

    with pytest.raises(MT5HistoricalDataError, match="copy_ticks_range failed"):
        await host.get_historical_trade_ticks_range(
            symbol=MT5Symbol(symbol="WIN$"),
            instrument=instrument,
            start_date_time=start,
            end_date_time=end,
            map_tick_flags_to_aggressor=False,
        )


@pytest.mark.asyncio
async def test_netref_like_ndarray_subclass_rejected() -> None:
    class NetrefNdarray(np.ndarray):
        pass

    base = _make_tick_array([(1700000000, 0.0, 0.0, 176290.0, 10, 1700000000000, 1336, 10.0)])
    netref = base.view(NetrefNdarray)
    assert isinstance(netref, np.ndarray)
    assert type(netref) is not np.ndarray

    mt5 = SimpleNamespace(
        COPY_TICKS_TRADE=2,
        copy_ticks_range=MagicMock(return_value=netref),
    )
    host = _BoundedHelperHost(mt5)
    instrument = _win_dollar_instrument()
    start = pd.Timestamp("2023-11-14 22:13:20", tz="UTC")
    end = pd.Timestamp("2023-11-14 22:13:21", tz="UTC")

    with pytest.raises(MT5HistoricalDataError, match="exact local numpy.ndarray"):
        await host.get_historical_trade_ticks_range(
            symbol=MT5Symbol(symbol="WIN$"),
            instrument=instrument,
            start_date_time=start,
            end_date_time=end,
            map_tick_flags_to_aggressor=False,
        )


@pytest.mark.asyncio
async def test_missing_required_field_fails() -> None:
    dtype = np.dtype(
        [
            ("time", "<i8"),
            ("bid", "<f8"),
            ("ask", "<f8"),
            ("last", "<f8"),
            ("volume", "<u8"),
            ("time_msc", "<i8"),
            ("flags", "<u4"),
            # volume_real intentionally omitted
        ],
    )
    raw = np.array([(1700000000, 0.0, 0.0, 176290.0, 10, 1700000000000, 1336)], dtype=dtype)
    mt5 = SimpleNamespace(COPY_TICKS_TRADE=2, copy_ticks_range=MagicMock(return_value=raw))
    host = _BoundedHelperHost(mt5)
    instrument = _win_dollar_instrument()
    start = pd.Timestamp("2023-11-14 22:13:20", tz="UTC")
    end = pd.Timestamp("2023-11-14 22:13:21", tz="UTC")

    with pytest.raises(MT5HistoricalDataError, match="missing required fields"):
        await host.get_historical_trade_ticks_range(
            symbol=MT5Symbol(symbol="WIN$"),
            instrument=instrument,
            start_date_time=start,
            end_date_time=end,
            map_tick_flags_to_aggressor=False,
        )


@pytest.mark.asyncio
async def test_provider_envelope_same_second_widens() -> None:
    raw = np.zeros(0, dtype=MT5_TICK_DTYPE)
    mt5 = SimpleNamespace(COPY_TICKS_TRADE=2, copy_ticks_range=MagicMock(return_value=raw))
    host = _BoundedHelperHost(mt5)
    instrument = _win_dollar_instrument()
    # Sub-second exact point inside second 1700000000
    start = pd.Timestamp(1700000000_500_000_000, unit="ns", tz="UTC")
    end = start

    await host.get_historical_trade_ticks_range(
        symbol=MT5Symbol(symbol="WIN$"),
        instrument=instrument,
        start_date_time=start,
        end_date_time=end,
        map_tick_flags_to_aggressor=False,
    )
    _, date_from, date_to, _flags = mt5.copy_ticks_range.call_args[0]
    assert date_from == 1700000000
    assert date_to == 1700000001


@pytest.mark.asyncio
async def test_exact_logical_filter_and_multiplicity() -> None:
    # Three events: before, two equal-time inside, after
    rows = [
        (1699999999, 0.0, 0.0, 1.0, 1, 1699999999000, 1336, 1.0),
        (1700000000, 0.0, 0.0, 176290.0, 10, 1700000000123, 1336, 10.0),
        (1700000000, 0.0, 0.0, 176291.0, 11, 1700000000123, 1336, 11.0),
        (1700000002, 0.0, 0.0, 2.0, 1, 1700000002000, 1336, 1.0),
    ]
    raw = _make_tick_array(rows)
    mt5 = SimpleNamespace(COPY_TICKS_TRADE=2, copy_ticks_range=MagicMock(return_value=raw))
    host = _BoundedHelperHost(mt5)
    instrument = _win_dollar_instrument()
    start = pd.Timestamp(1700000000123_000_000, unit="ns", tz="UTC")
    end = start

    ticks = await host.get_historical_trade_ticks_range(
        symbol=MT5Symbol(symbol="WIN$"),
        instrument=instrument,
        start_date_time=start,
        end_date_time=end,
        map_tick_flags_to_aggressor=True,
    )
    assert len(ticks) == 2
    assert ticks[0].ts_event == ticks[1].ts_event == 1700000000123_000_000
    assert float(ticks[0].price) == 176290.0
    assert float(ticks[1].price) == 176291.0


@pytest.mark.asyncio
async def test_zero_last_is_valid_non_emitted_not_malformed() -> None:
    raw = _make_tick_array(
        [(1700000000, 0.0, 0.0, 0.0, 0, 1700000000000, 0, 0.0)],
    )
    mt5 = SimpleNamespace(COPY_TICKS_TRADE=2, copy_ticks_range=MagicMock(return_value=raw))
    host = _BoundedHelperHost(mt5)
    instrument = _win_dollar_instrument()
    start = pd.Timestamp("2023-11-14 22:13:20", tz="UTC")
    end = pd.Timestamp("2023-11-14 22:13:21", tz="UTC")

    ticks = await host.get_historical_trade_ticks_range(
        symbol=MT5Symbol(symbol="WIN$"),
        instrument=instrument,
        start_date_time=start,
        end_date_time=end,
        map_tick_flags_to_aggressor=False,
    )
    assert ticks == []


@pytest.mark.asyncio
async def test_naive_bound_rejected() -> None:
    mt5 = SimpleNamespace(COPY_TICKS_TRADE=2, copy_ticks_range=MagicMock())
    host = _BoundedHelperHost(mt5)
    instrument = _win_dollar_instrument()
    with pytest.raises(MT5HistoricalDataError, match="timezone-aware"):
        await host.get_historical_trade_ticks_range(
            symbol=MT5Symbol(symbol="WIN$"),
            instrument=instrument,
            start_date_time=pd.Timestamp("2023-11-14 22:13:20"),
            end_date_time=pd.Timestamp("2023-11-14 22:13:21", tz="UTC"),
            map_tick_flags_to_aggressor=False,
        )


def test_local_python_style_wrapper_resolves_via_get_constant() -> None:
    """Simulate LocalPythonMT5: no attribute, only get_constant → official module."""

    class FakeOfficialMT5:
        COPY_TICKS_TRADE = 2

    class LocalPythonLike:
        def __init__(self) -> None:
            self._mt5 = FakeOfficialMT5()

        def get_constant(self, name: str) -> Any:
            return getattr(self._mt5, name, None)

    assert not hasattr(LocalPythonLike(), "COPY_TICKS_TRADE")
    assert _resolve_mt5_constant(LocalPythonLike(), "COPY_TICKS_TRADE") == 2


def test_parity_helper_detects_count_mismatch() -> None:
    from homologation.support.a05_trade_tick_parity import compare_trade_tick_streams

    class _T:
        def __init__(self, ts: int, px: int, sz: int) -> None:
            self.ts_event = ts
            self.price = SimpleNamespace(raw=px)
            self.size = SimpleNamespace(raw=sz)
            self.aggressor_side = "NO_AGGRESSOR"

    mismatches = compare_trade_tick_streams([_T(1, 1, 1)], [_T(1, 1, 1), _T(2, 2, 2)])
    assert any("accepted event count" in m for m in mismatches)


@pytest.mark.asyncio
async def test_malformed_routing_metadata_raises_historical_error() -> None:
    """route_wire_tick failures must surface as MT5HistoricalDataError (x04 §5)."""
    raw = _make_tick_array(
        [(1700000000, 0.0, 0.0, 176290.0, 10, 1700000000000, 1336, 10.0)],
    )
    mt5 = SimpleNamespace(COPY_TICKS_TRADE=2, copy_ticks_range=MagicMock(return_value=raw))
    host = _BoundedHelperHost(mt5)
    instrument = _win_dollar_instrument()
    # Non-integral trade_mode makes instrument_trade_mode()/route_wire_tick raise.
    instrument.info["trade_mode"] = "not-an-int"

    start = pd.Timestamp("2023-11-14 22:13:20", tz="UTC")
    end = pd.Timestamp("2023-11-14 22:13:21", tz="UTC")
    with pytest.raises(MT5HistoricalDataError, match="routing/converting"):
        await host.get_historical_trade_ticks_range(
            symbol=MT5Symbol(symbol="WIN$"),
            instrument=instrument,
            start_date_time=start,
            end_date_time=end,
            map_tick_flags_to_aggressor=True,
        )


def test_live_equivalent_conversion_matches_wire_path() -> None:
    instrument = _win_dollar_instrument()
    wire = WireTick(
        time_msc=1700000000123,
        bid=0.0,
        ask=0.0,
        last=176290.0,
        volume=10,
        volume_real=10.0,
        flags=1336,
    )
    decision = route_wire_tick(instrument, wire)
    assert decision.emit_trade is True
    trade = wire_tick_to_trade_tick(
        instrument,
        wire,
        1_700_000_000_000_000_000,
        map_tick_flags_to_aggressor=True,
    )
    assert trade is not None
    assert trade.ts_event == 1700000000123_000_000
    assert float(trade.price) == 176290.0


@pytest.mark.asyncio
async def test_uncapped_result_larger_than_typical_capacity() -> None:
    n = 50
    rows = [
        (1700000000, 0.0, 0.0, 176290.0 + i, 1, 1700000000000 + i, 1336, 1.0)
        for i in range(n)
    ]
    raw = _make_tick_array(rows)
    mt5 = SimpleNamespace(COPY_TICKS_TRADE=2, copy_ticks_range=MagicMock(return_value=raw))
    host = _BoundedHelperHost(mt5)
    instrument = _win_dollar_instrument()
    start = pd.Timestamp(1700000000000_000_000, unit="ns", tz="UTC")
    end = pd.Timestamp(1700000000049_000_000, unit="ns", tz="UTC")

    ticks = await host.get_historical_trade_ticks_range(
        symbol=MT5Symbol(symbol="WIN$"),
        instrument=instrument,
        start_date_time=start,
        end_date_time=end,
        map_tick_flags_to_aggressor=False,
    )
    assert len(ticks) == n
