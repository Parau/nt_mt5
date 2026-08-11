"""
QuoteTick flag-semantics classifiers for MT5 tick homologation.

Purpose/Single Responsibility:
    Classify MT5 tick rows by BID/ASK/LAST/VOLUME flags and compare
    ``COPY_TICKS_INFO`` vs flagged ``COPY_TICKS_ALL`` multisets. Also measure
    eligible vs actual QuoteTick emission after the flag-based routing fix.

Data Flow & Dependencies:
    Consumed by ``homologation/run_quote_tick_semantics.py`` and unit tests.
    Inputs are structured tick rows or ``WireTick``-like objects.

Premises & Limitations:
    ``semantic_quote_changed`` mirrors production ``route_wire_tick`` quote flags.
    Eligible quotes additionally require valid bid/ask and the existing sanity gate.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from nautilus_mt5.tick_routing import (
    TICK_FLAG_ASK,
    TICK_FLAG_BID,
    TICK_FLAG_LAST,
    TICK_FLAG_VOLUME,
)

QUOTE_FLAG_MASK = TICK_FLAG_BID | TICK_FLAG_ASK
TRADE_FLAG_MASK = TICK_FLAG_LAST | TICK_FLAG_VOLUME


def tick_field(row: Any, name: str, default: Any = 0) -> Any:
    if isinstance(row, Mapping):
        return row.get(name, default)
    try:
        return row[name]
    except Exception:
        return getattr(row, name, default)


def semantic_quote_changed(flags: int) -> bool:
    """Production QuoteTick flag rule: Bid and/or Ask changed per MT5 flags."""
    return bool(int(flags) & QUOTE_FLAG_MASK)


def semantic_trade_changed(flags: int) -> bool:
    return bool(int(flags) & TRADE_FLAG_MASK)


def has_valid_bid_ask(bid: float, ask: float) -> bool:
    return bid > 0.0 and ask > 0.0 and ask > bid


@dataclass(frozen=True, slots=True)
class QuoteRowKey:
    time_msc: int
    bid: float
    ask: float
    flags: int


def quote_row_key(row: Any) -> QuoteRowKey:
    return QuoteRowKey(
        time_msc=int(tick_field(row, "time_msc", 0) or 0),
        bid=round(float(tick_field(row, "bid", 0.0) or 0.0), 8),
        ask=round(float(tick_field(row, "ask", 0.0) or 0.0), 8),
        flags=int(tick_field(row, "flags", 0) or 0),
    )


def classify_flag_category(flags: int) -> str:
    has_bid = bool(flags & TICK_FLAG_BID)
    has_ask = bool(flags & TICK_FLAG_ASK)
    has_trade = bool(flags & TRADE_FLAG_MASK)
    if has_bid and not has_ask and not has_trade:
        return "BID-only"
    if has_ask and not has_bid and not has_trade:
        return "ASK-only"
    if has_bid and has_ask and not has_trade:
        return "BID|ASK"
    if (has_bid or has_ask) and has_trade:
        return "BID/ASK + LAST/VOLUME"
    if has_trade and not has_bid and not has_ask:
        return "LAST/VOLUME sem BID/ASK"
    return "outros"


def classify_all_rows(rows: Sequence[Any]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in rows:
        counts[classify_flag_category(int(tick_field(row, "flags", 0) or 0))] += 1
    return dict(counts)


def flagged_quote_rows(rows: Sequence[Any]) -> list[Any]:
    return [
        row
        for row in rows
        if semantic_quote_changed(int(tick_field(row, "flags", 0) or 0))
    ]


def multiset_keys(rows: Iterable[Any]) -> Counter[QuoteRowKey]:
    return Counter(quote_row_key(row) for row in rows)


def compare_info_vs_flagged_all(
    all_rows: Sequence[Any],
    info_rows: Sequence[Any],
) -> dict[str, Any]:
    flagged = flagged_quote_rows(all_rows)
    all_keys = multiset_keys(flagged)
    info_keys = multiset_keys(info_rows)
    only_all = all_keys - info_keys
    only_info = info_keys - all_keys
    divergences: list[dict[str, Any]] = []
    for key, n in only_all.items():
        divergences.append(
            {
                "side": "in_flagged_ALL_not_INFO",
                "count": int(n),
                "time_msc": key.time_msc,
                "bid": key.bid,
                "ask": key.ask,
                "flags": key.flags,
                "category": classify_flag_category(key.flags),
            },
        )
    for key, n in only_info.items():
        divergences.append(
            {
                "side": "in_INFO_not_flagged_ALL",
                "count": int(n),
                "time_msc": key.time_msc,
                "bid": key.bid,
                "ask": key.ask,
                "flags": key.flags,
                "category": classify_flag_category(key.flags),
            },
        )
    return {
        "all_count": len(all_rows),
        "info_count": len(info_rows),
        "all_with_bid_ask_flags": len(flagged),
        "exact_multiset_match": len(only_all) == 0 and len(only_info) == 0,
        "divergence_count": len(divergences),
        "divergences_head": divergences[:30],
        "flag_categories_all": classify_all_rows(all_rows),
    }


def residual_quote_candidates(rows: Sequence[Any]) -> list[dict[str, Any]]:
    """Rows with valid bid/ask but without BID/ASK change flags."""
    out: list[dict[str, Any]] = []
    for row in rows:
        flags = int(tick_field(row, "flags", 0) or 0)
        bid = float(tick_field(row, "bid", 0.0) or 0.0)
        ask = float(tick_field(row, "ask", 0.0) or 0.0)
        if semantic_quote_changed(flags):
            continue
        if not has_valid_bid_ask(bid, ask):
            continue
        out.append(
            {
                "time_msc": int(tick_field(row, "time_msc", 0) or 0),
                "bid": bid,
                "ask": ask,
                "last": float(tick_field(row, "last", 0.0) or 0.0),
                "volume": int(tick_field(row, "volume", 0) or 0),
                "volume_real": float(tick_field(row, "volume_real", 0.0) or 0.0),
                "flags": flags,
                "category": classify_flag_category(flags),
                "has_trade_flag": semantic_trade_changed(flags),
            },
        )
    return out


def handler_drop_trade_candidates(rows: Sequence[Any]) -> dict[str, Any]:
    """Trade-flagged rows that InboundFeedHandler would drop (bid/ask <= 0)."""
    trade_rows = [
        row for row in rows if semantic_trade_changed(int(tick_field(row, "flags", 0) or 0))
    ]
    bid_le0 = 0
    ask_le0 = 0
    any_invalid = 0
    samples: list[dict[str, Any]] = []
    for row in trade_rows:
        bid = float(tick_field(row, "bid", 0.0) or 0.0)
        ask = float(tick_field(row, "ask", 0.0) or 0.0)
        bad_bid = bid <= 0.0
        bad_ask = ask <= 0.0
        if bad_bid:
            bid_le0 += 1
        if bad_ask:
            ask_le0 += 1
        if bad_bid or bad_ask:
            any_invalid += 1
            if len(samples) < 10:
                samples.append(
                    {
                        "time_msc": int(tick_field(row, "time_msc", 0) or 0),
                        "bid": bid,
                        "ask": ask,
                        "last": float(tick_field(row, "last", 0.0) or 0.0),
                        "volume": int(tick_field(row, "volume", 0) or 0),
                        "flags": int(tick_field(row, "flags", 0) or 0),
                    },
                )
    return {
        "trade_rows_total": len(trade_rows),
        "trade_rows_bid_le0": bid_le0,
        "trade_rows_ask_le0": ask_le0,
        "trade_rows_any_side_invalid": any_invalid,
        "samples": samples,
    }


def quote_sample_from_nautilus(tick: Any) -> tuple[int, float, float]:
    return (int(tick.ts_event), float(tick.bid_price), float(tick.ask_price))


def wire_quote_sample(tick: Any) -> tuple[int, float, float]:
    time_msc = int(tick_field(tick, "time_msc", 0) or 0)
    return (
        time_msc * 1_000_000,
        float(tick_field(tick, "bid", 0.0) or 0.0),
        float(tick_field(tick, "ask", 0.0) or 0.0),
    )
