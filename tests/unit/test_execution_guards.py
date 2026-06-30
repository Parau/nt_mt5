"""Unit tests for execution pre-venue guards (disabled symbols, filling)."""
from __future__ import annotations

import pytest
from nautilus_trader.model.enums import TimeInForce

from nautilus_mt5.parsing.execution import (
    SYMBOL_FILLING_FOK,
    SYMBOL_FILLING_IOC,
    validate_filling_mode,
    validate_symbol_tradable,
)


def test_validate_symbol_tradable_rejects_disabled():
    with pytest.raises(ValueError, match="TRADE_MODE=DISABLED"):
        validate_symbol_tradable({"trade_mode": 0, "symbol": {"symbol": "WIN$"}})


def test_validate_symbol_tradable_allows_full():
    validate_symbol_tradable({"trade_mode": 4, "symbol": {"symbol": "WDON26"}})


def test_validate_filling_mode_fok_requires_bit():
    with pytest.raises(ValueError, match="FOK"):
        validate_filling_mode(SYMBOL_FILLING_IOC, TimeInForce.FOK)


def test_validate_filling_mode_ioc_requires_bit():
    with pytest.raises(ValueError, match="IOC"):
        validate_filling_mode(SYMBOL_FILLING_FOK, TimeInForce.IOC)


def test_validate_filling_mode_gtc_skips_return_check():
    validate_filling_mode(SYMBOL_FILLING_IOC, TimeInForce.GTC)
