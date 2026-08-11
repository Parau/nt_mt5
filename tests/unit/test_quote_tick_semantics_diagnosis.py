"""
Diagnostic unit tests for QuoteTick flag semantics (pre-correction).

Purpose:
    Document the gap between current ``route_wire_tick`` quote emission
    (``emit_quote = has_bid_ask``) and the candidate flag rule
    (``TICK_FLAG_BID | TICK_FLAG_ASK``). Does not change production routing.

These tests assert both current behavior and expected semantic intent so the
future correction has an explicit contract.
"""
from __future__ import annotations

import json
import pathlib

from nautilus_trader.model.instruments import FuturesContract

from homologation.support.quote_tick_semantics import semantic_quote_changed
from nautilus_mt5 import XP_B3_PROFILE
from nautilus_mt5.data_types import MT5Symbol, MT5SymbolDetails
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


def test_semantic_bid_only_is_quote_changed() -> None:
    assert semantic_quote_changed(TICK_FLAG_BID) is True


def test_semantic_ask_only_is_quote_changed() -> None:
    assert semantic_quote_changed(TICK_FLAG_ASK) is True


def test_semantic_bid_ask_is_quote_changed() -> None:
    assert semantic_quote_changed(TICK_FLAG_BID | TICK_FLAG_ASK) is True


def test_semantic_trade_only_residual_quote_is_not_quote_changed() -> None:
    flags = TICK_FLAG_LAST | TICK_FLAG_VOLUME
    assert semantic_quote_changed(flags) is False


def test_semantic_trade_plus_quote_flags_is_quote_changed() -> None:
    flags = TICK_FLAG_BID | TICK_FLAG_ASK | TICK_FLAG_LAST | TICK_FLAG_VOLUME
    assert semantic_quote_changed(flags) is True


def test_current_route_emits_quote_on_trade_only_residual_bid_ask() -> None:
    """Current production: valid bid/ask alone ⇒ emit_quote (suspected over-emit)."""
    inst = _instrument()
    decision = route_wire_tick(inst, _wire(flags=TICK_FLAG_LAST | TICK_FLAG_VOLUME))
    assert decision.emit_trade is True
    assert decision.emit_quote is True  # current behavior
    assert semantic_quote_changed(TICK_FLAG_LAST | TICK_FLAG_VOLUME) is False


def test_current_route_emits_quote_on_bid_only_flag() -> None:
    inst = _instrument()
    decision = route_wire_tick(inst, _wire(flags=TICK_FLAG_BID))
    assert decision.emit_quote is True
    assert semantic_quote_changed(TICK_FLAG_BID) is True


def test_current_route_emits_quote_on_ask_only_flag() -> None:
    inst = _instrument()
    decision = route_wire_tick(inst, _wire(flags=TICK_FLAG_ASK))
    assert decision.emit_quote is True
    assert semantic_quote_changed(TICK_FLAG_ASK) is True


def test_diagnosis_documents_expected_future_gate() -> None:
    """
    Expected future rule (NOT implemented yet):

        quote_changed = bool(flags & (BID|ASK))
        emit_quote = has_bid_ask and quote_changed
    """
    flags = TICK_FLAG_LAST | TICK_FLAG_VOLUME
    has_bid_ask = True
    quote_changed = semantic_quote_changed(flags)
    expected_future_emit_quote = has_bid_ask and quote_changed
    assert expected_future_emit_quote is False
