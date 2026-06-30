"""Unit tests for tick routing (Quote vs Trade, sanity gate)."""
from __future__ import annotations

import json
import pathlib

import pytest

from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import FuturesContract
from nautilus_trader.model.objects import Currency, Price, Quantity

from nautilus_mt5.data_types import MT5Symbol, MT5SymbolDetails
from nautilus_mt5.feed.messages import WireTick
from nautilus_mt5.parsing.instruments import parse_instrument
from nautilus_mt5.tick_routing import route_wire_tick, quote_passes_sanity_gate
from nautilus_mt5 import XP_B3_PROFILE

_TEST_DATA = pathlib.Path(__file__).parent.parent / "test_data"


def _load(name: str) -> MT5SymbolDetails:
    data = json.loads((_TEST_DATA / name).read_text())
    data.pop("_comment", None)
    data["symbol"] = MT5Symbol(**data["symbol"])
    return MT5SymbolDetails(**data)


def _instrument_from_fixture(filename: str) -> FuturesContract:
    details = _load(filename)
    return parse_instrument(details, venue_profile=XP_B3_PROFILE)


def test_win_dollar_routes_trade_only() -> None:
    inst = _instrument_from_fixture("symbol_info_win_dollar.json")
    decision = route_wire_tick(inst, WireTick(time_msc=1, bid=0, ask=0, last=176290, volume=10, flags=1336))
    assert decision.emit_trade is True
    assert decision.emit_quote is False


def test_wdon26_routes_quote_and_trade() -> None:
    inst = _instrument_from_fixture("symbol_info_wdon26.json")
    decision = route_wire_tick(
        inst,
        WireTick(time_msc=1, bid=5178.5, ask=5179.0, last=5178.5, volume=3, flags=1368),
    )
    assert decision.emit_quote is True
    assert decision.emit_trade is True


def test_winq26_garbage_quote_fails_sanity_gate() -> None:
    inst = _instrument_from_fixture("symbol_info_winq26.json")
    assert quote_passes_sanity_gate(192490, 157495, 176290, inst) is False
    decision = route_wire_tick(
        inst,
        WireTick(time_msc=1, bid=192490, ask=157495, last=176290, volume=5, flags=1336),
    )
    assert decision.emit_quote is False
    assert decision.emit_trade is True


def test_winq26_coherent_quote_passes_sanity_gate() -> None:
    inst = _instrument_from_fixture("symbol_info_winq26.json")
    assert quote_passes_sanity_gate(176280, 176300, 176290, inst) is True
