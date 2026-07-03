"""Trade tick volume resolution for MT5 MqlTick / wire payloads."""
from __future__ import annotations

from decimal import Decimal


def resolve_trade_tick_size(
    volume: float | int,
    volume_real: float = 0.0,
) -> Decimal | None:
    """
    Return positive trade size in instrument units, or None when absent.

    MT5 may populate ``volume`` (lots/contracts) or ``volume_real`` depending on
    symbol calc mode and terminal build. No silent fallback to 1 — callers that
    need a TradeTick must discard ticks without a resolvable size.
    """
    if volume and float(volume) > 0:
        return Decimal(str(volume))
    if volume_real and float(volume_real) > 0:
        return Decimal(str(volume_real))
    return None
