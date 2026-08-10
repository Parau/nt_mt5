"""
A05 historical↔live TradeTick stream-parity homologation harness.

Purpose/Single Responsibility:
    Provide a runnable real-provider gate that compares TradeTicks emitted by the
    full live inbound feed pipeline against the A05 bounded historical path for
    the same logical interval.

Data Flow & Dependencies:
    Live: MQL5 feed → InboundFeedHandler → route_wire_tick_to_nautilus.
    Historical: copy_ticks_range(COPY_TICKS_TRADE) → A05 helper.
    Invoked from homologation runners when a TradeTick-capable terminal is up
    (AMP CME / XP B3). Tickmill is out of scope (trade_ticks UNSUPPORTED).

Premises & Limitations:
    Does not enable TradingUltimate warmup. Real-provider PASS is required before
    production certification. Deterministic Tier 1 coverage lives under tests/.
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

    Returns a list of human-readable mismatch reasons (empty => parity OK).
    """
    live_s = [trade_tick_to_parity_sample(t) for t in live_ticks]
    hist_s = [trade_tick_to_parity_sample(t) for t in historical_ticks]
    mismatches: list[str] = []

    if len(live_s) != len(hist_s):
        mismatches.append(
            f"accepted event count live={len(live_s)} historical={len(hist_s)}",
        )

    n = min(len(live_s), len(hist_s))
    for i in range(n):
        a, b = live_s[i], hist_s[i]
        if a != b:
            mismatches.append(f"index={i} live={a} historical={b}")

    return mismatches
