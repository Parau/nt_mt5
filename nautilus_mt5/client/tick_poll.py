from __future__ import annotations


def is_quote_tick_subscription(tick_type: str) -> bool:
    return tick_type.lower() in ("bidask", "bid_ask")
