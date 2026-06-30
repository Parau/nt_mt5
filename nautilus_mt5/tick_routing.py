"""
Tick routing helpers — quote vs trade emission from MT5 wire/poll shapes.

Routing uses instrument metadata (trade_mode, symbol suffix) and tick content,
not broker name. See ``res/xp_b3_restrictions.md`` for XP/B3 probe ground truth.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from nautilus_trader.model.enums import AggressorSide

if TYPE_CHECKING:
    from nautilus_trader.model.instruments.base import Instrument

    from nautilus_mt5.feed.messages import WireTick

# MT5 TICK_FLAG_* (MetaTrader5.py)
TICK_FLAG_BID = 2
TICK_FLAG_ASK = 4
TICK_FLAG_LAST = 8
TICK_FLAG_VOLUME = 16
TICK_FLAG_BUY = 32
TICK_FLAG_SELL = 64

# MT5 SYMBOL_TRADE_MODE_DISABLED
SYMBOL_TRADE_MODE_DISABLED = 0


class TickLike(Protocol):
    bid: float
    ask: float
    last: float
    volume: int
    flags: int


@dataclass(frozen=True, slots=True)
class TickRoutingDecision:
    emit_quote: bool
    emit_trade: bool
    quote_reject_reason: str | None = None


def is_continuous_data_symbol(symbol: str) -> bool:
    """True for B3 continuous series (``WIN$``, ``WDO$``) — data-only on XP."""
    return bool(symbol) and symbol.endswith("$")


def instrument_trade_mode(instrument: Instrument) -> int:
    info = instrument.info if isinstance(instrument.info, dict) else {}
    return int(info.get("trade_mode", 4))


def quote_sanity_threshold_ticks(instrument: Instrument, *, default_n: int = 10) -> float:
    """Max allowed |mid - last| as a multiple of tick size before rejecting a quote."""
    info = instrument.info if isinstance(instrument.info, dict) else {}
    tick_size = float(info.get("trade_tick_size") or info.get("point") or 0.0)
    if tick_size <= 0:
        return float("inf")
    return default_n * tick_size


def quote_passes_sanity_gate(
    bid: float,
    ask: float,
    last: float,
    instrument: Instrument,
    *,
    max_mid_last_delta: float | None = None,
) -> bool:
    if bid <= 0 or ask <= 0 or ask <= bid:
        return False
    if last <= 0:
        return True
    threshold = (
        max_mid_last_delta
        if max_mid_last_delta is not None
        else quote_sanity_threshold_ticks(instrument)
    )
    mid = (bid + ask) / 2.0
    return abs(mid - last) <= threshold


def route_wire_tick(instrument: Instrument, tick: WireTick | TickLike) -> TickRoutingDecision:
    """
    Decide whether a WS/poll tick should produce QuoteTick, TradeTick, or both.

    Continuous/disabled symbols never emit quotes. Off-hours WINQ26-style garbage
    bid/ask is filtered by the sanity gate when ``last > 0``.
    """
    symbol = instrument.id.symbol.value
    trade_mode = instrument_trade_mode(instrument)

    has_bid_ask = tick.bid > 0 and tick.ask > 0 and tick.ask > tick.bid
    has_last = tick.last > 0
    flags = int(getattr(tick, "flags", 0) or 0)
    last_flag = bool(flags & TICK_FLAG_LAST) or has_last

    if trade_mode == SYMBOL_TRADE_MODE_DISABLED or is_continuous_data_symbol(symbol):
        if has_last or last_flag:
            return TickRoutingDecision(emit_quote=False, emit_trade=True)
        return TickRoutingDecision(emit_quote=False, emit_trade=False)

    emit_trade = has_last and (last_flag or not has_bid_ask)
    emit_quote = has_bid_ask

    if emit_quote and has_last and not quote_passes_sanity_gate(tick.bid, tick.ask, tick.last, instrument):
        emit_quote = False
        return TickRoutingDecision(
            emit_quote=False,
            emit_trade=emit_trade or has_last,
            quote_reject_reason="bid/ask failed sanity gate vs last",
        )

    return TickRoutingDecision(emit_quote=emit_quote, emit_trade=emit_trade)


def mt5_flags_to_aggressor(flags: int) -> AggressorSide:
    """
    Map MT5 ``TICK_FLAG_*`` on a trade tick to Nautilus ``AggressorSide``.

    Requires ``TICK_FLAG_LAST``. BUY and SELL are mutually exclusive hints
    (XP/B3 export: UI 56/88, API 1080/1112). Ambiguous both → ``NO_AGGRESSOR``.
    See ``res/export ticks xp/README.md``.
    """
    if not (flags & TICK_FLAG_LAST):
        return AggressorSide.NO_AGGRESSOR
    if (flags & TICK_FLAG_BUY) and not (flags & TICK_FLAG_SELL):
        return AggressorSide.BUYER
    if (flags & TICK_FLAG_SELL) and not (flags & TICK_FLAG_BUY):
        return AggressorSide.SELLER
    return AggressorSide.NO_AGGRESSOR


def resolve_trade_aggressor(flags: int, *, map_from_tick_flags: bool) -> AggressorSide:
    """Return trade aggressor; disabled unless the venue profile opts in."""
    if not map_from_tick_flags:
        return AggressorSide.NO_AGGRESSOR
    return mt5_flags_to_aggressor(flags)
