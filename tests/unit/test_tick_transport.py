"""EXTERNAL_RPyC brine-safe tick frame unit coverage (A05 / x04).

Purpose/Single Responsibility:
    Prove encode/decode of ``MT5_TICKS_V1`` without pickle, including empty,
    None, malformed tag/count/payload, dtype identity, and order/duplicates.

Data Flow & Dependencies:
    Exercises ``nautilus_mt5.metatrader5.tick_transport`` and confirms bridge
    ThreadedServer protocol_config does not enable ``allow_pickle``.

Premises & Limitations:
    Does not exercise a live RPyC socket; LOCAL_PYTHON path is out of scope.
"""
from __future__ import annotations

import ast
import pathlib

import numpy as np
import pytest

from nautilus_mt5.metatrader5.tick_transport import (
    MT5_TICK_DTYPE,
    MT5_TICKS_FRAME_TAG,
    decode_mt5_ticks_frame,
    encode_mt5_ticks_frame,
)
from tests.support.fake_mt5_rpyc_bridge import _make_tick_array

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_BRIDGE_PATHS = (
    _REPO_ROOT / "MQL5" / "refactoring" / "bridge" / "mt5_bridge.py",
    _REPO_ROOT / "MQL5" / "refactoring" / "bridge" / "mt5_bridge_v008.py",
)


def test_bridge_protocol_config_does_not_enable_pickle() -> None:
    for path in _BRIDGE_PATHS:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        found = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = getattr(func, "attr", None) or getattr(func, "id", None)
            if name != "ThreadedServer":
                continue
            found = True
            for kw in node.keywords:
                if kw.arg != "protocol_config":
                    continue
                assert isinstance(kw.value, ast.Dict)
                for key_node, value_node in zip(kw.value.keys, kw.value.values):
                    if isinstance(key_node, ast.Constant) and key_node.value == "allow_pickle":
                        assert isinstance(value_node, ast.Constant)
                        assert value_node.value is False
        assert found, f"ThreadedServer not found in {path}"


def test_encode_none_stays_none() -> None:
    assert encode_mt5_ticks_frame(None) is None
    assert decode_mt5_ticks_frame(None) is None


def test_non_empty_frame_roundtrip() -> None:
    raw = _make_tick_array(
        [
            (1700000000, 0.0, 0.0, 176290.0, 10, 1700000000000, 1336, 10.0),
            (1700000000, 0.0, 0.0, 176291.0, 11, 1700000000000, 1336, 11.0),
        ],
    )
    frame = encode_mt5_ticks_frame(raw)
    assert frame is not None
    tag, count, payload = frame
    assert tag == MT5_TICKS_FRAME_TAG
    assert count == 2
    assert isinstance(payload, (bytes, bytearray))

    out = decode_mt5_ticks_frame(frame)
    assert type(out) is np.ndarray
    assert out.dtype == MT5_TICK_DTYPE
    assert list(out.dtype.names) == list(MT5_TICK_DTYPE.names)
    assert len(out) == 2
    assert float(out[0]["last"]) == 176290.0
    assert float(out[1]["last"]) == 176291.0
    assert int(out[0]["time_msc"]) == int(out[1]["time_msc"]) == 1700000000000


def test_empty_frame_roundtrip() -> None:
    raw = np.zeros(0, dtype=MT5_TICK_DTYPE)
    frame = encode_mt5_ticks_frame(raw)
    out = decode_mt5_ticks_frame(frame)
    assert type(out) is np.ndarray
    assert len(out) == 0
    assert out.dtype == MT5_TICK_DTYPE


def test_bad_tag_fails() -> None:
    with pytest.raises(RuntimeError, match="wire tag"):
        decode_mt5_ticks_frame(("WRONG", 0, b""))


def test_negative_row_count_fails() -> None:
    with pytest.raises(RuntimeError, match="row_count"):
        decode_mt5_ticks_frame((MT5_TICKS_FRAME_TAG, -1, b""))


def test_byte_length_mismatch_fails() -> None:
    with pytest.raises(RuntimeError, match="length mismatch"):
        decode_mt5_ticks_frame((MT5_TICKS_FRAME_TAG, 1, b"xx"))


@pytest.mark.asyncio
async def test_a05_helper_accepts_reconstructed_frame() -> None:
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    import pandas as pd

    from nautilus_mt5.client.market_data import MetaTrader5ClientMarketDataMixin
    from nautilus_mt5.data_types import MT5Symbol
    from tests.unit.test_a05_bounded_trade_ticks import _win_dollar_instrument

    raw = _make_tick_array(
        [(1700000000, 0.0, 0.0, 176290.0, 10, 1700000000000, 1336, 10.0)],
    )
    reconstructed = decode_mt5_ticks_frame(encode_mt5_ticks_frame(raw))
    mt5 = SimpleNamespace(
        COPY_TICKS_TRADE=2,
        copy_ticks_range=MagicMock(return_value=reconstructed),
    )

    class Host(MetaTrader5ClientMarketDataMixin):
        def __init__(self) -> None:
            self._mt5_client = {"mt5": mt5}
            self._clock = MagicMock()
            self._clock.timestamp_ns.return_value = 1_700_000_000_000_000_000
            self._log = MagicMock()

    ticks = await Host().get_historical_trade_ticks_range(
        symbol=MT5Symbol(symbol="WIN$"),
        instrument=_win_dollar_instrument(),
        start_date_time=pd.Timestamp("2023-11-14 22:13:20", tz="UTC"),
        end_date_time=pd.Timestamp("2023-11-14 22:13:21", tz="UTC"),
        map_tick_flags_to_aggressor=True,
    )
    assert len(ticks) == 1
    assert float(ticks[0].price) == 176290.0
