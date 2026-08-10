"""Unit tests for tick routing (Quote vs Trade, sanity gate)."""
from __future__ import annotations

import json
import pathlib

import pytest

from nautilus_trader.model.enums import AggressorSide
from nautilus_trader.model.instruments import FuturesContract
from nautilus_trader.model.objects import Currency, Price, Quantity

from nautilus_mt5.data_types import MT5Symbol, MT5SymbolDetails
from nautilus_mt5.feed.messages import WireTick
from nautilus_mt5.parsing.instruments import parse_instrument
from nautilus_mt5.tick_routing import (
    TICK_FLAG_ASK,
    TICK_FLAG_BID,
    TICK_FLAG_LAST,
    TICK_FLAG_VOLUME,
    mt5_flags_to_aggressor,
    quote_passes_sanity_gate,
    resolve_trade_aggressor,
    route_wire_tick,
)
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


def test_mt5_flags_to_aggressor_xp_api_values() -> None:
    # XP API flags (UI + 1024); see res/export ticks xp/README.md
    assert mt5_flags_to_aggressor(1080) == AggressorSide.BUYER
    assert mt5_flags_to_aggressor(1112) == AggressorSide.SELLER
    assert mt5_flags_to_aggressor(1144) == AggressorSide.NO_AGGRESSOR
    assert mt5_flags_to_aggressor(1028) == AggressorSide.NO_AGGRESSOR


def test_resolve_trade_aggressor_respects_venue_gate() -> None:
    assert resolve_trade_aggressor(1080, map_from_tick_flags=False) == AggressorSide.NO_AGGRESSOR
    assert resolve_trade_aggressor(1080, map_from_tick_flags=True) == AggressorSide.BUYER


def test_bid_only_update_with_stale_last_does_not_emit_trade() -> None:
    """MT5 keeps prior last filled on Bid/Ask-only rows — must not invent TradeTicks."""
    inst = _instrument_from_fixture("symbol_info_wdon26.json")
    decision = route_wire_tick(
        inst,
        WireTick(
            time_msc=1,
            bid=100.0,
            ask=101.0,
            last=100.5,
            volume=1,
            volume_real=1.0,
            flags=TICK_FLAG_BID,
        ),
    )
    assert decision.emit_trade is False
    assert decision.emit_quote is True


def test_last_and_volume_flags_emit_trade() -> None:
    inst = _instrument_from_fixture("symbol_info_wdon26.json")
    decision = route_wire_tick(
        inst,
        WireTick(
            time_msc=1,
            bid=100.0,
            ask=101.0,
            last=100.5,
            volume=2,
            volume_real=2.0,
            flags=TICK_FLAG_LAST | TICK_FLAG_VOLUME,
        ),
    )
    assert decision.emit_trade is True


def test_ask_only_update_with_stale_last_does_not_emit_trade() -> None:
    inst = _instrument_from_fixture("symbol_info_wdon26.json")
    decision = route_wire_tick(
        inst,
        WireTick(
            time_msc=1,
            bid=100.0,
            ask=101.0,
            last=100.5,
            volume=1,
            volume_real=1.0,
            flags=TICK_FLAG_ASK,
        ),
    )
    assert decision.emit_trade is False


def test_volume_only_change_emits_trade() -> None:
    """Same-price fill: volume changed, last price unchanged — still a TradeTick."""
    inst = _instrument_from_fixture("symbol_info_wdon26.json")
    wire = WireTick(
        time_msc=1,
        bid=100.0,
        ask=101.0,
        last=100.5,
        volume=2,
        volume_real=2.0,
        flags=TICK_FLAG_VOLUME,
    )
    assert wire.flags == TICK_FLAG_VOLUME
    assert (wire.flags & TICK_FLAG_LAST) == 0
    decision = route_wire_tick(inst, wire)
    assert decision.emit_trade is True
    assert decision.emit_quote is True


def test_last_only_change_emits_trade() -> None:
    inst = _instrument_from_fixture("symbol_info_wdon26.json")
    decision = route_wire_tick(
        inst,
        WireTick(
            time_msc=1,
            bid=100.0,
            ask=101.0,
            last=100.5,
            volume=2,
            volume_real=2.0,
            flags=TICK_FLAG_LAST,
        ),
    )
    assert decision.emit_trade is True


def test_continuous_symbol_also_requires_trade_flags() -> None:
    """WIN$ must not fall back to last>0 — probes show real trades carry LAST/VOLUME."""
    inst = _instrument_from_fixture("symbol_info_win_dollar.json")
    stale = route_wire_tick(
        inst,
        WireTick(time_msc=1, bid=0, ask=0, last=176290, volume=10, flags=0),
    )
    assert stale.emit_trade is False
    real = route_wire_tick(
        inst,
        WireTick(
            time_msc=1,
            bid=0,
            ask=0,
            last=176290,
            volume=10,
            flags=TICK_FLAG_LAST | TICK_FLAG_VOLUME,
        ),
    )
    assert real.emit_trade is True


def test_continuous_volume_only_emits_trade() -> None:
    inst = _instrument_from_fixture("symbol_info_win_dollar.json")
    decision = route_wire_tick(
        inst,
        WireTick(
            time_msc=1,
            bid=0.0,
            ask=0.0,
            last=176290.0,
            volume=10,
            volume_real=10.0,
            flags=TICK_FLAG_VOLUME,
        ),
    )
    assert decision.emit_trade is True
    assert decision.emit_quote is False
