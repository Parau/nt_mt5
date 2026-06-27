from __future__ import annotations

import json

from nautilus_mt5.feed.handler import InboundFeedHandler
from nautilus_mt5.feed.messages import TickBatchMessage, WireTick, parse_wire_message


def _batch(symbol: str, cursor: int, ticks: list[WireTick]) -> TickBatchMessage:
    return TickBatchMessage(symbol=symbol, cursor=cursor, ticks=tuple(ticks))


def test_dedup_skips_duplicate_snapshot() -> None:
    handler = InboundFeedHandler()
    tick = WireTick(time_msc=100, bid=1.1, ask=1.2, flags=6)

    first = handler.handle_message(_batch("BTCUSD", 100, [tick]))
    assert isinstance(first, TickBatchMessage)
    assert len(first.ticks) == 1

    second = handler.handle_message(_batch("BTCUSD", 100, [tick]))
    assert second is None


def test_dedup_advances_cursor_and_accepts_new_ticks() -> None:
    handler = InboundFeedHandler()
    t1 = WireTick(time_msc=100, bid=1.1, ask=1.2, flags=6)
    t2 = WireTick(time_msc=101, bid=1.11, ask=1.21, flags=6)

    out1 = handler.handle_message(_batch("BTCUSD", 100, [t1]))
    out2 = handler.handle_message(_batch("BTCUSD", 101, [t2]))

    assert isinstance(out1, TickBatchMessage)
    assert isinstance(out2, TickBatchMessage)
    assert out2.ticks[0].time_msc == 101


def test_dedup_rejects_regressing_cursor() -> None:
    handler = InboundFeedHandler()
    t1 = WireTick(time_msc=100, bid=1.1, ask=1.2, flags=6)
    t2 = WireTick(time_msc=99, bid=1.0, ask=1.1, flags=6)

    handler.handle_message(_batch("BTCUSD", 100, [t1]))
    out = handler.handle_message(_batch("BTCUSD", 99, [t2]))
    assert out is None


def test_hello_updates_subscription_state() -> None:
    handler = InboundFeedHandler()
    handler.subscription_state.mark_subscribe(["BTCUSD"])

    raw = json.dumps({"op": "hello", "session": "s1", "symbols": ["BTCUSD"]})
    hello = handler.handle_raw(raw)

    assert hello is not None
    assert hello.session == "s1"
    assert "BTCUSD" not in handler.subscription_state.pending_subscribe
    assert handler.subscription_state.service_symbols == frozenset({"BTCUSD"})


def test_invalid_bid_ask_filtered() -> None:
    handler = InboundFeedHandler()
    bad = WireTick(time_msc=100, bid=0.0, ask=60478.0, flags=6)
    out = handler.handle_message(_batch("BTCUSD", 100, [bad]))
    assert out is None
