from __future__ import annotations

import json

from nautilus_mt5.feed.handler import InboundFeedHandler
from nautilus_mt5.feed.messages import BarMessage, TickBatchMessage, WireBar, WireTick, parse_wire_message


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


def test_invalid_bid_ask_not_filtered_by_handler() -> None:
    """Handler stays type-neutral; routing decides Quote vs Trade."""
    handler = InboundFeedHandler()
    bad_quote = WireTick(time_msc=100, bid=0.0, ask=60478.0, flags=6)
    out = handler.handle_message(_batch("BTCUSD", 100, [bad_quote]))
    assert isinstance(out, TickBatchMessage)
    assert len(out.ticks) == 1
    assert out.ticks[0].bid == 0.0


def test_trade_only_zero_bbo_preserved_for_routing() -> None:
    from nautilus_mt5.feed.converter import route_wire_tick_to_nautilus
    from nautilus_mt5.tick_routing import TICK_FLAG_LAST, TICK_FLAG_VOLUME
    import json
    import pathlib

    from nautilus_mt5 import XP_B3_PROFILE
    from nautilus_mt5.data_types import MT5Symbol, MT5SymbolDetails
    from nautilus_mt5.parsing.instruments import parse_instrument

    handler = InboundFeedHandler()
    trade = WireTick(
        time_msc=100,
        bid=0.0,
        ask=0.0,
        last=176290.0,
        volume=10,
        volume_real=10.0,
        flags=TICK_FLAG_LAST | TICK_FLAG_VOLUME,
    )
    out = handler.handle_message(_batch("WIN$", 100, [trade]))
    assert isinstance(out, TickBatchMessage)
    assert len(out.ticks) == 1

    data = json.loads(
        (pathlib.Path(__file__).parent.parent / "test_data" / "symbol_info_win_dollar.json").read_text(),
    )
    data.pop("_comment", None)
    data["symbol"] = MT5Symbol(**data["symbol"])
    inst = parse_instrument(MT5SymbolDetails(**data), venue_profile=XP_B3_PROFILE)
    quote, trade_tick = route_wire_tick_to_nautilus(inst, out.ticks[0], ts_init=1)
    assert quote is None
    assert trade_tick is not None


def test_quote_flag_with_invalid_bbo_preserved_but_routing_rejects() -> None:
    from nautilus_mt5.feed.converter import route_wire_tick_to_nautilus
    from nautilus_mt5.tick_routing import TICK_FLAG_BID
    import json
    import pathlib

    from nautilus_mt5 import XP_B3_PROFILE
    from nautilus_mt5.data_types import MT5Symbol, MT5SymbolDetails
    from nautilus_mt5.parsing.instruments import parse_instrument

    handler = InboundFeedHandler()
    wire = WireTick(time_msc=100, bid=0.0, ask=0.0, last=100.5, volume=1, flags=TICK_FLAG_BID)
    out = handler.handle_message(_batch("WDON26", 100, [wire]))
    assert isinstance(out, TickBatchMessage)

    data = json.loads(
        (pathlib.Path(__file__).parent.parent / "test_data" / "symbol_info_wdon26.json").read_text(),
    )
    data.pop("_comment", None)
    data["symbol"] = MT5Symbol(**data["symbol"])
    inst = parse_instrument(MT5SymbolDetails(**data), venue_profile=XP_B3_PROFILE)
    quote, trade = route_wire_tick_to_nautilus(inst, out.ticks[0], ts_init=1)
    assert quote is None
    assert trade is None


def test_bar_dedup_emits_once_per_close_time() -> None:
    handler = InboundFeedHandler()
    bar = WireBar(
        symbol="BTCUSD",
        timeframe="M1",
        time=1730000000,
        open=1.0,
        high=2.0,
        low=0.5,
        close=1.5,
    )
    msg = BarMessage(bar=bar)

    first = handler.handle_message(msg)
    second = handler.handle_message(msg)

    assert isinstance(first, BarMessage)
    assert second is None
