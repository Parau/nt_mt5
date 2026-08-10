from __future__ import annotations

from decimal import Decimal

from nautilus_trader.model.data import Bar, BarAggregation, BarSpecification, BarType, QuoteTick
from nautilus_trader.model.enums import AggressorSide
from nautilus_trader.model.enums import AggregationSource, PriceType
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.objects import Currency, Price, Quantity

from nautilus_mt5.feed.converter import (
    route_wire_tick_to_nautilus,
    wire_bar_to_nautilus_bar,
    wire_tick_to_quote_tick,
    wire_tick_to_trade_tick,
)
from nautilus_mt5.feed.messages import WireBar, WireTick
from nautilus_mt5.parsing.tick_volume import resolve_trade_tick_size


def _btcusd_instrument() -> CurrencyPair:
    return CurrencyPair(
        instrument_id=InstrumentId(Symbol("BTCUSD"), Venue("METATRADER_5")),
        raw_symbol=Symbol("BTCUSD"),
        base_currency=Currency.from_str("BTC"),
        quote_currency=Currency.from_str("USD"),
        price_precision=2,
        size_precision=2,
        price_increment=Price.from_str("0.01"),
        size_increment=Quantity.from_str("0.01"),
        lot_size=Quantity.from_str("1"),
        max_quantity=Quantity.from_str("100"),
        min_quantity=Quantity.from_str("0.01"),
        max_price=Price.from_str("1000000"),
        min_price=Price.from_str("0.01"),
        margin_init=Decimal("0"),
        margin_maint=Decimal("0"),
        maker_fee=Decimal("0"),
        taker_fee=Decimal("0"),
        ts_event=0,
        ts_init=0,
    )


def test_wire_tick_to_quote_tick() -> None:
    instrument = _btcusd_instrument()
    tick = WireTick(time_msc=1_000, bid=60468.0, ask=60478.0, flags=6)
    quote = wire_tick_to_quote_tick(instrument, tick, ts_init=2_000_000_000)

    assert isinstance(quote, QuoteTick)
    assert quote.instrument_id == instrument.id
    assert float(quote.bid_price) == 60468.0
    assert float(quote.ask_price) == 60478.0
    assert quote.ts_event == 1_000_000_000
    assert quote.ts_init == 2_000_000_000


def test_wire_tick_invalid_prices_returns_none() -> None:
    instrument = _btcusd_instrument()
    tick = WireTick(time_msc=1_000, bid=0.0, ask=60478.0)
    assert wire_tick_to_quote_tick(instrument, tick, ts_init=1) is None


def test_wire_tick_to_trade_tick() -> None:
    instrument = _btcusd_instrument()
    tick = WireTick(time_msc=2_000, bid=0.0, ask=0.0, last=60470.0, volume=3, flags=8)
    trade = wire_tick_to_trade_tick(instrument, tick, ts_init=3_000_000_000)
    assert trade is not None
    assert float(trade.price) == 60470.0
    assert trade.aggressor_side == AggressorSide.NO_AGGRESSOR


def test_wire_tick_to_trade_tick_xp_aggressor_buy() -> None:
    instrument = _btcusd_instrument()
    tick = WireTick(time_msc=2_000, bid=0.0, ask=0.0, last=174115.0, volume=1, flags=1080)
    trade = wire_tick_to_trade_tick(
        instrument,
        tick,
        ts_init=1,
        map_tick_flags_to_aggressor=True,
    )
    assert trade is not None
    assert trade.aggressor_side == AggressorSide.BUYER


def test_wire_tick_to_trade_tick_xp_aggressor_sell() -> None:
    instrument = _btcusd_instrument()
    tick = WireTick(time_msc=2_000, bid=0.0, ask=0.0, last=174110.0, volume=1, flags=1112)
    trade = wire_tick_to_trade_tick(
        instrument,
        tick,
        ts_init=1,
        map_tick_flags_to_aggressor=True,
    )
    assert trade is not None
    assert trade.aggressor_side == AggressorSide.SELLER


def test_route_wire_tick_trade_only() -> None:
    instrument = _btcusd_instrument()
    tick = WireTick(time_msc=1_000, bid=0.0, ask=0.0, last=60400.0, volume=1, flags=1336)
    quote, trade = route_wire_tick_to_nautilus(instrument, tick, ts_init=1)
    assert quote is None
    assert trade is not None


def test_volume_only_flag_creates_nautilus_trade_tick() -> None:
    """VOLUME without LAST must still become a TradeTick (same-price fill)."""
    from nautilus_mt5.tick_routing import TICK_FLAG_LAST, TICK_FLAG_VOLUME

    instrument = _btcusd_instrument()
    tick = WireTick(
        time_msc=2_000,
        bid=60468.0,
        ask=60478.0,
        last=60470.0,
        volume=3,
        volume_real=3.0,
        flags=TICK_FLAG_VOLUME,
    )
    assert tick.flags == TICK_FLAG_VOLUME
    assert (tick.flags & TICK_FLAG_LAST) == 0
    quote, trade = route_wire_tick_to_nautilus(
        instrument,
        tick,
        ts_init=9_000_000_000,
        map_tick_flags_to_aggressor=True,
    )
    assert trade is not None
    assert float(trade.price) == 60470.0
    assert float(trade.size) == float(resolve_trade_tick_size(3, 3.0))
    assert trade.ts_event == 2_000 * 1_000_000
    assert trade.aggressor_side == AggressorSide.NO_AGGRESSOR
    # Bid/Ask present → quote may also emit; trade must not disappear.
    assert quote is not None


def test_wire_bar_to_nautilus_bar() -> None:
    instrument = _btcusd_instrument()
    bar_type = BarType(
        instrument.id,
        BarSpecification(1, BarAggregation.MINUTE, PriceType.LAST),
        AggregationSource.EXTERNAL,
    )
    wire = WireBar(
        symbol="BTCUSD",
        timeframe="M1",
        time=1_700_000_000,
        open=60000.0,
        high=60100.0,
        low=59900.0,
        close=60050.0,
        tick_volume=42,
    )
    bar = wire_bar_to_nautilus_bar(instrument, bar_type, wire, ts_init=2)

    assert isinstance(bar, Bar)
    assert bar.bar_type == bar_type
    assert float(bar.close) == 60050.0
    assert float(bar.volume) == 42.0


def test_resolve_trade_tick_size_prefers_volume() -> None:
    assert resolve_trade_tick_size(3, 5.0) == Decimal(3)


def test_resolve_trade_tick_size_uses_volume_real() -> None:
    assert resolve_trade_tick_size(0, 5.0) == Decimal(5)


def test_resolve_trade_tick_size_absent_returns_none() -> None:
    assert resolve_trade_tick_size(0, 0.0) is None


def test_wire_tick_to_trade_tick_discards_without_volume() -> None:
    instrument = _btcusd_instrument()
    tick = WireTick(time_msc=2_000, bid=0.0, ask=0.0, last=60470.0, volume=0, volume_real=0.0, flags=8)
    assert wire_tick_to_trade_tick(instrument, tick, ts_init=3_000_000_000) is None


def test_wire_tick_to_trade_tick_uses_volume_real() -> None:
    instrument = _btcusd_instrument()
    tick = WireTick(time_msc=2_000, bid=0.0, ask=0.0, last=60470.0, volume=0, volume_real=7.0, flags=8)
    trade = wire_tick_to_trade_tick(instrument, tick, ts_init=3_000_000_000)
    assert trade is not None
    assert float(trade.size) == 7.0
