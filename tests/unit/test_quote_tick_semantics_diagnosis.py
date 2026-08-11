"""
Production contract tests for QuoteTick flag semantics in ``route_wire_tick``.

Purpose:
    Prove that QuoteTick emission requires ``TICK_FLAG_BID`` and/or
    ``TICK_FLAG_ASK`` (matching ``COPY_TICKS_INFO``), while TradeTick continues
    to use ``TICK_FLAG_LAST`` / ``TICK_FLAG_VOLUME``.
"""
from __future__ import annotations

import json
import pathlib

from nautilus_trader.model.instruments import FuturesContract

from homologation.support.quote_tick_semantics import semantic_quote_changed
from nautilus_mt5 import XP_B3_PROFILE
from nautilus_mt5.data_types import MT5Symbol, MT5SymbolDetails
from nautilus_mt5.feed.converter import route_wire_tick_to_nautilus
from nautilus_mt5.feed.messages import WireTick
from nautilus_mt5.parsing.instruments import parse_instrument
from nautilus_mt5.tick_routing import (
    TICK_FLAG_ASK,
    TICK_FLAG_BID,
    TICK_FLAG_LAST,
    TICK_FLAG_VOLUME,
    route_wire_tick,
)

_TEST_DATA = pathlib.Path(__file__).parent.parent / "test_data"


def _instrument() -> FuturesContract:
    data = json.loads((_TEST_DATA / "symbol_info_wdon26.json").read_text())
    data.pop("_comment", None)
    data["symbol"] = MT5Symbol(**data["symbol"])
    return parse_instrument(MT5SymbolDetails(**data), venue_profile=XP_B3_PROFILE)


def _wire(*, flags: int) -> WireTick:
    return WireTick(
        time_msc=1,
        bid=100.0,
        ask=101.0,
        last=100.5,
        volume=2,
        volume_real=2.0,
        flags=flags,
    )


def test_bid_only_emits_quote() -> None:
    inst = _instrument()
    decision = route_wire_tick(inst, _wire(flags=TICK_FLAG_BID))
    assert decision.emit_quote is True
    assert decision.emit_trade is False


def test_ask_only_emits_quote() -> None:
    inst = _instrument()
    decision = route_wire_tick(inst, _wire(flags=TICK_FLAG_ASK))
    assert decision.emit_quote is True
    assert decision.emit_trade is False


def test_bid_ask_emits_quote() -> None:
    inst = _instrument()
    decision = route_wire_tick(inst, _wire(flags=TICK_FLAG_BID | TICK_FLAG_ASK))
    assert decision.emit_quote is True
    assert decision.emit_trade is False


def test_trade_only_residual_bid_ask_emits_trade_not_quote() -> None:
    """Principal regression: LAST|VOLUME must not invent QuoteTicks from residual bid/ask."""
    inst = _instrument()
    flags = TICK_FLAG_LAST | TICK_FLAG_VOLUME
    decision = route_wire_tick(inst, _wire(flags=flags))
    assert decision.emit_trade is True
    assert decision.emit_quote is False
    assert semantic_quote_changed(flags) is False


def test_trade_plus_quote_flags_emit_both() -> None:
    inst = _instrument()
    flags = TICK_FLAG_BID | TICK_FLAG_ASK | TICK_FLAG_LAST | TICK_FLAG_VOLUME
    decision = route_wire_tick(inst, _wire(flags=flags))
    assert decision.emit_quote is True
    assert decision.emit_trade is True


def test_valid_bid_ask_without_quote_flags_does_not_emit_quote() -> None:
    inst = _instrument()
    decision = route_wire_tick(inst, _wire(flags=0))
    assert decision.emit_quote is False
    assert decision.emit_trade is False


def test_route_to_nautilus_trade_only_residual_yields_trade_not_quote() -> None:
    inst = _instrument()
    quote, trade = route_wire_tick_to_nautilus(
        inst,
        _wire(flags=TICK_FLAG_LAST | TICK_FLAG_VOLUME),
        ts_init=1,
    )
    assert quote is None
    assert trade is not None


def test_route_to_nautilus_bid_only_yields_quote() -> None:
    inst = _instrument()
    quote, trade = route_wire_tick_to_nautilus(inst, _wire(flags=TICK_FLAG_BID), ts_init=1)
    assert quote is not None
    assert trade is None
    assert float(quote.bid_price) == 100.0
    assert float(quote.ask_price) == 101.0


def test_route_to_nautilus_ask_only_yields_quote() -> None:
    inst = _instrument()
    quote, trade = route_wire_tick_to_nautilus(inst, _wire(flags=TICK_FLAG_ASK), ts_init=1)
    assert quote is not None
    assert trade is None
