"""
A05 historical↔live TradeTick stream-parity comparator.

Purpose/Single Responsibility:
    Project TradeTicks onto comparable samples and report ordered stream
    mismatches for A05 §17 / x03 §12 field sets.

Data Flow & Dependencies:
    Invoked by ``homologation/run_a05_trade_tick_parity.py`` after live capture
    and A05 bounded historical request for the same logical interval.
    Unit tests may call ``compare_trade_tick_streams`` directly.

Premises & Limitations:
    This module does not subscribe to feeds or request history — it only compares.
    Full PASS/FAIL certification is owned by the Tier-1.5 runner. Tickmill is
    out of scope (trade_ticks UNSUPPORTED).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TradeTickParitySample:
    """Minimal comparable TradeTick fields for A05 §17 / x03 §12."""

    ts_event: int
    price_raw: int
    size_raw: int
    aggressor_side: Any


def trade_tick_to_parity_sample(tick: Any) -> TradeTickParitySample:
    """Project a Nautilus TradeTick onto the A05 parity comparison fields."""
    return TradeTickParitySample(
        ts_event=int(tick.ts_event),
        price_raw=int(tick.price.raw),
        size_raw=int(tick.size.raw),
        aggressor_side=tick.aggressor_side,
    )


def compare_trade_tick_streams(
    live_ticks: list[Any],
    historical_ticks: list[Any],
) -> list[str]:
    """
    Compare ordered TradeTick streams.

    Returns a list of human-readable mismatch descriptions (empty = match).
    """
    live_samples = [trade_tick_to_parity_sample(t) for t in live_ticks]
    hist_samples = [trade_tick_to_parity_sample(t) for t in historical_ticks]
    mismatches: list[str] = []

    if len(live_samples) != len(hist_samples):
        mismatches.append(
            f"accepted event count live={len(live_samples)} historical={len(hist_samples)}",
        )

    for index, (live, hist) in enumerate(zip(live_samples, hist_samples)):
        if live.ts_event != hist.ts_event:
            mismatches.append(f"index={index} ts_event: live={live.ts_event} historical={hist.ts_event}")
        if live.price_raw != hist.price_raw:
            mismatches.append(
                f"index={index} price.raw: live={live.price_raw} historical={hist.price_raw}",
            )
        if live.size_raw != hist.size_raw:
            mismatches.append(
                f"index={index} size.raw: live={live.size_raw} historical={hist.size_raw}",
            )
        if live.aggressor_side != hist.aggressor_side:
            mismatches.append(
                f"index={index} aggressor_side: live={live.aggressor_side!r} "
                f"historical={hist.aggressor_side!r}",
            )

    return mismatches
