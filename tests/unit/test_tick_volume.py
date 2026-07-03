"""Unit tests for trade tick volume resolution."""
from __future__ import annotations

from decimal import Decimal

from nautilus_mt5.parsing.tick_volume import resolve_trade_tick_size


def test_resolve_trade_tick_size_volume_only() -> None:
    assert resolve_trade_tick_size(10, 0.0) == Decimal(10)


def test_resolve_trade_tick_size_real_only() -> None:
    assert resolve_trade_tick_size(0, 2.5) == Decimal("2.5")
