from __future__ import annotations

from decimal import Decimal

from nautilus_trader.core.datetime import secs_to_nanos
from nautilus_trader.model.data import Bar, BarType, QuoteTick
from nautilus_trader.model.instruments.base import Instrument

from nautilus_mt5.feed.messages import WireBar, WireTick


def wire_tick_to_quote_tick(
    instrument: Instrument,
    tick: WireTick,
    ts_init: int,
) -> QuoteTick | None:
    """
    Map one MQL5 wire tick to a Nautilus QuoteTick.

    Sizes use zero qty, matching the legacy symbol_info_tick poll path.
    """
    if tick.bid <= 0.0 or tick.ask <= 0.0:
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
