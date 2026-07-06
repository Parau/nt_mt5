"""Unit tests for instrument volume capability resolution."""
from __future__ import annotations

import json
import pathlib

import pytest

from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.enums import AggressorSide
from nautilus_trader.model.identifiers import TradeId
from nautilus_trader.model.instruments import Cfd, CurrencyPair, Equity, FuturesContract

from nautilus_mt5 import TICKMILL_DEMO_PROFILE, XP_B3_PROFILE
from nautilus_mt5.data_types import MT5Symbol, MT5SymbolDetails
from nautilus_mt5.parsing.instruments import parse_instrument
from nautilus_mt5.venue_profile import CapabilityStatus
from nautilus_mt5.volume_capability import (
    financial_notional_from_tick,
    resolve_volume_capability,
    trade_qty_from_tick,
)

_TEST_DATA_DIR = pathlib.Path(__file__).parent.parent / "test_data"


def _load_symbol_details(filename: str) -> MT5SymbolDetails:
    data = json.loads((_TEST_DATA_DIR / filename).read_text())
    data.pop("_comment", None)
    if isinstance(data.get("symbol"), dict):
        data["symbol"] = MT5Symbol(**data["symbol"])
    return MT5SymbolDetails(**data)


def _make_trade_tick(instrument, price: str, size: str) -> TradeTick:
    return TradeTick(
        instrument_id=instrument.id,
        price=instrument.make_price(price),
        size=instrument.make_qty(size),
        aggressor_side=AggressorSide.NO_AGGRESSOR,
        trade_id=TradeId("1"),
        ts_event=1_000_000_000,
        ts_init=1_000_000_000,
    )


@pytest.mark.parametrize(
    ("fixture", "profile", "inst_type", "trade_qty", "financial_notional", "bar_activity"),
    [
        ("symbol_info_winq26.json", XP_B3_PROFILE, FuturesContract, True, True, False),
        ("symbol_info_petr4.json", XP_B3_PROFILE, Equity, True, True, False),
        ("symbol_info_di1f27.json", XP_B3_PROFILE, FuturesContract, True, False, False),
        ("symbol_info_btcusd.json", TICKMILL_DEMO_PROFILE, Cfd, False, False, True),
        ("symbol_info_eurusd.json", TICKMILL_DEMO_PROFILE, CurrencyPair, False, False, True),
    ],
)
def test_resolve_volume_capability_matrix(
    fixture: str,
    profile,
    inst_type,
    trade_qty: bool,
    financial_notional: bool,
    bar_activity: bool,
) -> None:
    details = _load_symbol_details(fixture)
    instrument = parse_instrument(details, venue_profile=profile)
    assert isinstance(instrument, inst_type)

    cap = resolve_volume_capability(instrument, profile)
    assert cap.trade_qty is trade_qty
    assert cap.financial_notional is financial_notional
    assert cap.bar_volume_activity_only is bar_activity


def test_trade_qty_from_tick_respects_capability() -> None:
    details = _load_symbol_details("symbol_info_winq26.json")
    instrument = parse_instrument(details, venue_profile=XP_B3_PROFILE)
    cap = resolve_volume_capability(instrument, XP_B3_PROFILE)
    tick = _make_trade_tick(instrument, "130000", "2")

    assert trade_qty_from_tick(cap, tick) == pytest.approx(2.0)

    cfd = parse_instrument(_load_symbol_details("symbol_info_btcusd.json"), venue_profile=TICKMILL_DEMO_PROFILE)
    cfd_cap = resolve_volume_capability(cfd, TICKMILL_DEMO_PROFILE)
    assert trade_qty_from_tick(cfd_cap, _make_trade_tick(cfd, "90000", "1")) is None


def test_financial_notional_from_tick() -> None:
    details = _load_symbol_details("symbol_info_winq26.json")
    instrument = parse_instrument(details, venue_profile=XP_B3_PROFILE)
    cap = resolve_volume_capability(instrument, XP_B3_PROFILE)
    tick = _make_trade_tick(instrument, "130000", "2")

    notional = financial_notional_from_tick(instrument, cap, tick)
    assert notional is not None
    assert float(notional.as_double()) == pytest.approx(52000.0)

    di1 = parse_instrument(_load_symbol_details("symbol_info_di1f27.json"), venue_profile=XP_B3_PROFILE)
    di1_cap = resolve_volume_capability(di1, XP_B3_PROFILE)
    di1_tick = _make_trade_tick(di1, "12.5", "1")
    assert financial_notional_from_tick(di1, di1_cap, di1_tick) is None
    assert di1_cap.trade_ticks_status != CapabilityStatus.UNSUPPORTED
