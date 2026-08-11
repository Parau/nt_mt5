"""
Historical QuoteTick conversion via ``get_historical_ticks`` (COPY_TICKS_INFO).

Purpose/Single Responsibility:
    Prove QuoteTick history selects ``COPY_TICKS_INFO``, applies BID|ASK flag
    semantics, preserves multiplicity, and treats empty provider results as
    success ``[]``. Does not exercise A05 bounded TradeTicks.
"""
from __future__ import annotations

import json
import pathlib
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pandas as pd
import pytest

from nautilus_mt5.client.market_data import MetaTrader5ClientMarketDataMixin
from nautilus_mt5.data_types import MT5Symbol, MT5SymbolDetails
from nautilus_mt5.parsing.instruments import parse_instrument
from nautilus_mt5.tick_routing import (
    TICK_FLAG_ASK,
    TICK_FLAG_BID,
    TICK_FLAG_LAST,
    TICK_FLAG_VOLUME,
)
from nautilus_mt5.venue_profile import XP_B3_PROFILE
from tests.support.fake_mt5_rpyc_bridge import MT5_TICK_DTYPE, _make_tick_array

_TEST_DATA = pathlib.Path(__file__).parent.parent / "test_data"


def _wdon26_instrument():
    data = json.loads((_TEST_DATA / "symbol_info_wdon26.json").read_text())
    data.pop("_comment", None)
    data["symbol"] = MT5Symbol(**data["symbol"])
    return parse_instrument(MT5SymbolDetails(**data), venue_profile=XP_B3_PROFILE)


class _HistTicksHost(MetaTrader5ClientMarketDataMixin):
    def __init__(self, mt5: Any, instrument) -> None:
        self._mt5_client = {"mt5": mt5}
        self._clock = MagicMock()
        self._clock.timestamp_ns.return_value = 1_700_000_000_000_000_000
        self._log = MagicMock()
        self._cache = MagicMock()
        self._cache.instrument.return_value = instrument


@pytest.mark.asyncio
async def test_historical_quote_ticks_uses_copy_ticks_info() -> None:
    captured: dict[str, Any] = {}

    def _copy_from(symbol, date_from, count, flags):
        captured["flags"] = flags
        return _make_tick_array([])

    mt5 = SimpleNamespace(
        COPY_TICKS_ALL=0,
        COPY_TICKS_INFO=1,
        COPY_TICKS_TRADE=2,
        copy_ticks_from=_copy_from,
    )
    host = _HistTicksHost(mt5, _wdon26_instrument())
    out = await host.get_historical_ticks(
        symbol=MT5Symbol(symbol="WDON26"),
        tick_type="BID_ASK",
        start_date_time=pd.Timestamp("2023-11-14 22:13:20", tz="UTC"),
        end_date_time=pd.Timestamp("2023-11-14 22:13:21", tz="UTC"),
        number_of_ticks=100,
    )
    assert out == []
    assert captured["flags"] == 1  # COPY_TICKS_INFO


@pytest.mark.asyncio
async def test_historical_trade_legacy_still_uses_copy_ticks_all() -> None:
    captured: dict[str, Any] = {}

    def _copy_from(symbol, date_from, count, flags):
        captured["flags"] = flags
        return _make_tick_array([])

    mt5 = SimpleNamespace(
        COPY_TICKS_ALL=0,
        COPY_TICKS_INFO=1,
        copy_ticks_from=_copy_from,
    )
    host = _HistTicksHost(mt5, _wdon26_instrument())
    await host.get_historical_ticks(
        symbol=MT5Symbol(symbol="WDON26"),
        tick_type="TRADES",
        start_date_time=pd.Timestamp("2023-11-14 22:13:20", tz="UTC"),
        end_date_time=pd.Timestamp("2023-11-14 22:13:21", tz="UTC"),
        number_of_ticks=100,
    )
    assert captured["flags"] == 0  # COPY_TICKS_ALL


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "flags",
    [TICK_FLAG_BID, TICK_FLAG_ASK, TICK_FLAG_BID | TICK_FLAG_ASK],
)
async def test_historical_quote_emits_for_bid_ask_flags(flags: int) -> None:
    raw = _make_tick_array(
        [(1700000000, 5178.5, 5179.0, 5178.5, 1, 1700000000000, flags, 1.0)],
    )
    mt5 = SimpleNamespace(
        COPY_TICKS_INFO=1,
        copy_ticks_from=MagicMock(return_value=raw),
    )
    host = _HistTicksHost(mt5, _wdon26_instrument())
    ticks = await host.get_historical_ticks(
        symbol=MT5Symbol(symbol="WDON26"),
        tick_type="BID_ASK",
        start_date_time=pd.Timestamp("2023-11-14 22:13:20", tz="UTC"),
        end_date_time=pd.Timestamp("2023-11-14 22:13:21", tz="UTC"),
        number_of_ticks=10,
    )
    assert len(ticks) == 1
    assert float(ticks[0].bid_price) == 5178.5
    assert float(ticks[0].ask_price) == 5179.0


@pytest.mark.asyncio
async def test_historical_quote_rejects_trade_only_residual_bbo() -> None:
    raw = _make_tick_array(
        [
            (
                1700000000,
                5178.5,
                5179.0,
                5178.5,
                2,
                1700000000000,
                TICK_FLAG_LAST | TICK_FLAG_VOLUME,
                2.0,
            ),
        ],
    )
    mt5 = SimpleNamespace(
        COPY_TICKS_INFO=1,
        copy_ticks_from=MagicMock(return_value=raw),
    )
    host = _HistTicksHost(mt5, _wdon26_instrument())
    ticks = await host.get_historical_ticks(
        symbol=MT5Symbol(symbol="WDON26"),
        tick_type="BID_ASK",
        start_date_time=pd.Timestamp("2023-11-14 22:13:20", tz="UTC"),
        end_date_time=pd.Timestamp("2023-11-14 22:13:21", tz="UTC"),
        number_of_ticks=10,
    )
    assert ticks == []


@pytest.mark.asyncio
async def test_historical_quote_preserves_same_time_msc_multiplicity() -> None:
    raw = _make_tick_array(
        [
            (1700000000, 5178.5, 5179.0, 5178.5, 1, 1700000000000, TICK_FLAG_BID, 1.0),
            (1700000000, 5178.0, 5178.5, 5178.5, 1, 1700000000000, TICK_FLAG_ASK, 1.0),
        ],
    )
    mt5 = SimpleNamespace(
        COPY_TICKS_INFO=1,
        copy_ticks_from=MagicMock(return_value=raw),
    )
    host = _HistTicksHost(mt5, _wdon26_instrument())
    ticks = await host.get_historical_ticks(
        symbol=MT5Symbol(symbol="WDON26"),
        tick_type="BID_ASK",
        start_date_time=pd.Timestamp("2023-11-14 22:13:20", tz="UTC"),
        end_date_time=pd.Timestamp("2023-11-14 22:13:21", tz="UTC"),
        number_of_ticks=10,
    )
    assert len(ticks) == 2
    assert ticks[0].ts_event == ticks[1].ts_event
    assert float(ticks[0].bid_price) == 5178.5
    assert float(ticks[1].bid_price) == 5178.0


@pytest.mark.asyncio
async def test_historical_quote_empty_ndarray_is_success() -> None:
    import numpy as np

    empty = np.empty(0, dtype=MT5_TICK_DTYPE)
    mt5 = SimpleNamespace(
        COPY_TICKS_INFO=1,
        copy_ticks_from=MagicMock(return_value=empty),
    )
    host = _HistTicksHost(mt5, _wdon26_instrument())
    ticks = await host.get_historical_ticks(
        symbol=MT5Symbol(symbol="WDON26"),
        tick_type="BID_ASK",
        start_date_time=pd.Timestamp("2023-11-14 22:13:20", tz="UTC"),
        end_date_time=pd.Timestamp("2023-11-14 22:13:21", tz="UTC"),
        number_of_ticks=10,
    )
    assert ticks == []
