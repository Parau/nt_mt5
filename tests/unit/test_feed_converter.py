from __future__ import annotations

from decimal import Decimal

from nautilus_trader.model.data import Bar, BarAggregation, BarSpecification, BarType, QuoteTick
from nautilus_trader.model.enums import AggregationSource, PriceType
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.objects import Currency, Price, Quantity

from nautilus_mt5.feed.converter import wire_bar_to_nautilus_bar, wire_tick_to_quote_tick
from nautilus_mt5.feed.messages import WireBar, WireTick


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
