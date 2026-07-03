"""
Instrument-level volume capability resolution for MT5 adapter strategies.

Strategies should resolve capabilities once per instrument (typically in
``on_start``) using the same ``VenueProfile`` as ``MetaTrader5DataClientConfig``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.instruments import Cfd, CurrencyPair, Instrument
from nautilus_trader.model.objects import Money

from nautilus_mt5.venue_profile import CapabilityStatus, VenueProfile


@dataclass(frozen=True, slots=True)
class InstrumentVolumeCapability:
    """
    Volume semantics resolved once per instrument.

    Attributes
    ----------
    trade_qty
        ``TradeTick.size`` may be treated as trade quantity (contracts/shares).
    financial_notional
        ``instrument.notional_value(size, price)`` is economically meaningful.
    bar_volume_activity_only
        ``Bar.volume`` is MT5 tick/real activity, not per-trade contract qty.
    trade_ticks_status
        Raw ``VenueProfile`` status for ``trade_ticks``.
    notional_mode
        Parser metadata from ``instrument.info`` (may be ``None`` on CFD).
    calc_mode
        MT5 ``trade_calc_mode`` from ``instrument.info``.
    instrument_type
        Nautilus instrument class name.
    """

    trade_qty: bool
    financial_notional: bool
    bar_volume_activity_only: bool
    trade_ticks_status: CapabilityStatus
    notional_mode: str | None
    calc_mode: int
    instrument_type: str


def resolve_volume_capability(
    instrument: Instrument,
    venue_profile: VenueProfile,
) -> InstrumentVolumeCapability:
    """
    Resolve trade-qty and financial-notional support for one instrument.

    Parameters
    ----------
    instrument
        Cached Nautilus instrument (must include MT5 ``info`` metadata).
    venue_profile
        Same profile wired into ``MetaTrader5DataClientConfig``.

    Returns
    -------
    InstrumentVolumeCapability
    """
    info: dict[str, Any] = instrument.info if isinstance(instrument.info, dict) else {}
    calc_mode = int(info.get("trade_calc_mode", 0))
    notional_mode = info.get("notional_mode")

    try:
        trade_status = venue_profile.check_capability(calc_mode, "trade_ticks")
    except ValueError:
        trade_status = CapabilityStatus.UNSUPPORTED

    trade_qty = trade_status != CapabilityStatus.UNSUPPORTED
    financial_notional = notional_mode == "linear_price_multiplier"
    bar_volume_activity_only = isinstance(instrument, (Cfd, CurrencyPair))

    return InstrumentVolumeCapability(
        trade_qty=trade_qty,
        financial_notional=financial_notional,
        bar_volume_activity_only=bar_volume_activity_only,
        trade_ticks_status=trade_status,
        notional_mode=notional_mode,
        calc_mode=calc_mode,
        instrument_type=type(instrument).__name__,
    )


def trade_qty_from_tick(
    cap: InstrumentVolumeCapability,
    tick: TradeTick,
) -> float | None:
    """
    Return trade quantity when the instrument supports it and tick has size.

    Parameters
    ----------
    cap
        Pre-resolved capability for ``tick.instrument_id``.
    tick
        Incoming trade tick.

    Returns
    -------
    float | None
        Positive quantity in instrument units, or ``None``.
    """
    if not cap.trade_qty:
        return None
    qty = tick.size.as_double()
    return qty if qty > 0 else None


def financial_notional_from_tick(
    instrument: Instrument,
    cap: InstrumentVolumeCapability,
    tick: TradeTick,
) -> Money | None:
    """
    Return financial notional via Nautilus ``notional_value`` when supported.

    Parameters
    ----------
    instrument
        Cached instrument for ``tick.instrument_id``.
    cap
        Pre-resolved capability.
    tick
        Incoming trade tick.

    Returns
    -------
    Money | None
    """
    if not cap.financial_notional:
        return None
    if tick.size.as_double() <= 0:
        return None
    return instrument.notional_value(tick.size, tick.price)
