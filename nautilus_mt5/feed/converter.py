from __future__ import annotations

from decimal import Decimal

from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.instruments.base import Instrument

from nautilus_mt5.feed.messages import WireTick


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
