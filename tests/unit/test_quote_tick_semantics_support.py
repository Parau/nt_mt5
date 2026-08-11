"""
Unit coverage for QuoteTick semantics support helpers (deterministic).
"""
from __future__ import annotations

from homologation.support.quote_tick_semantics import (
    classify_flag_category,
    compare_info_vs_flagged_all,
    handler_drop_trade_candidates,
    residual_quote_candidates,
)
from nautilus_mt5.tick_routing import (
    TICK_FLAG_ASK,
    TICK_FLAG_BID,
    TICK_FLAG_LAST,
    TICK_FLAG_VOLUME,
)


def _row(time_msc: int, bid: float, ask: float, flags: int, *, last: float = 1.0, volume: int = 1):
    return {
        "time_msc": time_msc,
        "bid": bid,
        "ask": ask,
        "last": last,
        "volume": volume,
        "volume_real": float(volume),
        "flags": flags,
    }


def test_compare_info_matches_flagged_all_multiset() -> None:
    all_rows = [
        _row(1, 10.0, 11.0, TICK_FLAG_BID),
        _row(2, 10.0, 11.0, TICK_FLAG_LAST | TICK_FLAG_VOLUME),  # residual quote
        _row(3, 10.1, 11.1, TICK_FLAG_BID | TICK_FLAG_ASK),
    ]
    info_rows = [
        _row(1, 10.0, 11.0, TICK_FLAG_BID),
        _row(3, 10.1, 11.1, TICK_FLAG_BID | TICK_FLAG_ASK),
    ]
    result = compare_info_vs_flagged_all(all_rows, info_rows)
    assert result["exact_multiset_match"] is True
    assert result["all_with_bid_ask_flags"] == 2
    assert result["info_count"] == 2


def test_residual_trade_only_with_valid_bid_ask() -> None:
    rows = [
        _row(1, 10.0, 11.0, TICK_FLAG_LAST | TICK_FLAG_VOLUME),
        _row(2, 10.0, 11.0, TICK_FLAG_BID),
    ]
    residual = residual_quote_candidates(rows)
    assert len(residual) == 1
    assert residual[0]["time_msc"] == 1
    assert classify_flag_category(TICK_FLAG_LAST | TICK_FLAG_VOLUME) == "LAST/VOLUME sem BID/ASK"


def test_handler_drop_candidates_detect_invalid_sides() -> None:
    rows = [
        _row(1, 0.0, 11.0, TICK_FLAG_LAST),
        _row(2, 10.0, 0.0, TICK_FLAG_VOLUME),
        _row(3, 10.0, 11.0, TICK_FLAG_LAST | TICK_FLAG_VOLUME),
        _row(4, 10.0, 11.0, TICK_FLAG_BID),  # not trade
    ]
    stats = handler_drop_trade_candidates(rows)
    assert stats["trade_rows_total"] == 3
    assert stats["trade_rows_bid_le0"] == 1
    assert stats["trade_rows_ask_le0"] == 1
    assert stats["trade_rows_any_side_invalid"] == 2
