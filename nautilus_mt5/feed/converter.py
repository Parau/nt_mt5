from __future__ import annotations

from decimal import Decimal

from nautilus_trader.core.datetime import secs_to_nanos
from nautilus_trader.model.data import Bar, BarType, QuoteTick, TradeTick
from nautilus_trader.model.identifiers import TradeId
from nautilus_trader.model.instruments.base import Instrument

from nautilus_mt5.feed.messages import WireBar, WireTick
from nautilus_mt5.tick_routing import quote_passes_sanity_gate, resolve_trade_aggressor, route_wire_tick


def wire_tick_to_quote_tick(
    instrument: Instrument,
    tick: WireTick,
    ts_init: int,
    *,
    apply_sanity_gate: bool = True,
) -> QuoteTick | None:
    """
    Map one MQL5 wire tick to a Nautilus QuoteTick.

    Sizes use zero qty, matching the legacy symbol_info_tick poll path.
    """
    if tick.bid <= 0.0 or tick.ask <= 0.0:
        return None
    if apply_sanity_gate and tick.last > 0 and not quote_passes_sanity_gate(
        tick.bid, tick.ask, tick.last, instrument
    ):
        return None

    ts_event = int(tick.time_msc * 1_000_000)
    return QuoteTick(
        instrument_id=instrument.id,
        bid_price=instrument.make_price(tick.bid),
        ask_price=instrument.make_price(tick.ask),
        bid_size=instrument.make_qty(Decimal(0)),
        ask_size=instrument.make_qty(Decimal(0)),
        ts_event=ts_event,
        ts_init=max(ts_init, ts_event),
    )


def wire_tick_to_trade_tick(
    instrument: Instrument,
    tick: WireTick,
    ts_init: int,
    *,
    map_tick_flags_to_aggressor: bool = False,
) -> TradeTick | None:
    """Map one MQL5 wire tick to a Nautilus TradeTick when ``last > 0``."""
    if tick.last <= 0.0:
        return None

    ts_event = int(tick.time_msc * 1_000_000)
    size = Decimal(tick.volume) if tick.volume > 0 else Decimal(1)
    return TradeTick(
        instrument_id=instrument.id,
        price=instrument.make_price(tick.last),
        size=instrument.make_qty(size),
        aggressor_side=resolve_trade_aggressor(
            tick.flags,
            map_from_tick_flags=map_tick_flags_to_aggressor,
        ),
        trade_id=TradeId(str(ts_event)),
        ts_event=ts_event,
        ts_init=max(ts_init, ts_event),
    )


def route_wire_tick_to_nautilus(
    instrument: Instrument,
    tick: WireTick,
    ts_init: int,
    *,
    map_tick_flags_to_aggressor: bool = False,
) -> tuple[QuoteTick | None, TradeTick | None]:
    """Apply tick routing and return quote/trade objects to emit."""
    decision = route_wire_tick(instrument, tick)
    quote = wire_tick_to_quote_tick(instrument, tick, ts_init) if decision.emit_quote else None
    trade = (
        wire_tick_to_trade_tick(
            instrument,
            tick,
            ts_init,
            map_tick_flags_to_aggressor=map_tick_flags_to_aggressor,
        )
        if decision.emit_trade
        else None
    )
    return quote, trade


def wire_bar_to_nautilus_bar(
    instrument: Instrument,
    bar_type: BarType,
    bar: WireBar,
    ts_init: int,
) -> Bar | None:
    """Map one closed MQL5 wire bar to a Nautilus Bar (close-only, no revisions)."""
    if bar.close <= 0.0 or bar.time <= 0:
        return None

    ts_event = secs_to_nanos(bar.time)
    volume = bar.tick_volume if bar.tick_volume > 0 else bar.real_volume
    return Bar(
        bar_type=bar_type,
        open=instrument.make_price(bar.open),
        high=instrument.make_price(bar.high),
        low=instrument.make_price(bar.low),
        close=instrument.make_price(bar.close),
        volume=instrument.make_qty(volume),
        ts_event=ts_event,
        ts_init=max(ts_init, ts_event),
        is_revision=False,
    )
