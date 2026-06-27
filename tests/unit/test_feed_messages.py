from __future__ import annotations

import json

import pytest

from nautilus_mt5.feed.messages import (
    HelloMessage,
    TickBatchMessage,
    WireTick,
    build_subscribe_command,
    build_unsubscribe_command,
    parse_wire_message,
)


def test_parse_hello_minimal() -> None:
    raw = json.dumps(
        {
            "op": "hello",
            "session": "nt5-1",
            "terminal": "MetaTrader 5",
            "account": 25339175,
            "symbols": ["BTCUSD"],
        }
    )
    msg = parse_wire_message(raw)
    assert isinstance(msg, HelloMessage)
    assert msg.session == "nt5-1"
    assert msg.symbols == ("BTCUSD",)
    assert msg.account == "25339175"


def test_parse_ticks_batch() -> None:
    raw = json.dumps(
        {
            "op": "ticks",
            "symbol": "BTCUSD",
            "cursor": 1782604709488,
            "data": [
                {
                    "time_msc": 1782604709488,
                    "bid": 60468.0,
                    "ask": 60478.0,
                    "last": 0.0,
                    "volume": 0,
                    "flags": 6,
                }
            ],
        }
    )
    msg = parse_wire_message(raw)
    assert isinstance(msg, TickBatchMessage)
    assert msg.symbol == "BTCUSD"
    assert msg.cursor == 1782604709488
    assert len(msg.ticks) == 1
    assert msg.ticks[0] == WireTick(
        time_msc=1782604709488,
        bid=60468.0,
        ask=60478.0,
        last=0.0,
        volume=0,
        flags=6,
    )


def test_build_subscribe_command() -> None:
    assert build_subscribe_command(["BTCUSD", "EURUSD"]) == (
        '{"op":"subscribe","symbols":["BTCUSD","EURUSD"]}'
    )
    assert build_unsubscribe_command(["BTCUSD"]) == '{"op":"unsubscribe","symbols":["BTCUSD"]}'


def test_parse_unknown_op_raises() -> None:
    with pytest.raises(ValueError, match="unsupported wire op"):
        parse_wire_message('{"op":"nope"}')
