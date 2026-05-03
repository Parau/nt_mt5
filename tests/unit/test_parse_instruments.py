"""
test_parse_instruments.py — Direct unit tests for the instrument parser.

These tests exercise ``parse_instrument()``, ``parse_currency_pair_contract()``,
``parse_cfd_contract()``, and ``sec_type_to_asset_class()`` in isolation.

Fixtures are loaded from ``tests/test_data/`` JSON files.  Each JSON file
contains the ``MT5SymbolDetails``-compatible field values for a representative
MT5 symbol type, derived from real Tickmill-Demo API responses (2026-05-03).

Covered scenarios
-----------------
- EURUSD (trade_calc_mode=0 / FOREX) with TICKMILL_DEMO_PROFILE  → CurrencyPair
- EURUSD without profile                                          → Cfd (fallback)
- USTEC  (trade_calc_mode=3 / CFDINDEX) with profile             → Cfd / INDEX
- BTCUSD (trade_calc_mode=2 / CFD) with profile                  → Cfd / CRYPTOCURRENCY
- Field-level assertions: price_precision, size_precision, price_increment,
  size_increment, min_quantity, max_quantity, base_currency, quote_currency.
- ``sec_type_to_asset_class()`` with representative path prefixes.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from nautilus_trader.model.enums import AssetClass
from nautilus_trader.model.instruments import Cfd, CurrencyPair
from nautilus_trader.model.objects import Price, Quantity

from nautilus_mt5.data_types import MT5Symbol, MT5SymbolDetails
from nautilus_mt5.parsing.instruments import (
    parse_instrument,
    parse_currency_pair_contract,
    parse_cfd_contract,
    mt5_symbol_to_instrument_id,
    sec_type_to_asset_class,
)
from nautilus_mt5 import TICKMILL_DEMO_PROFILE

# ---------------------------------------------------------------------------
# Fixture loading helpers
# ---------------------------------------------------------------------------

_TEST_DATA_DIR = pathlib.Path(__file__).parent.parent / "test_data"


def _load_symbol_details(filename: str) -> MT5SymbolDetails:
    """Load an MT5SymbolDetails from a JSON fixture file in tests/test_data/."""
    data = json.loads((_TEST_DATA_DIR / filename).read_text())
    data.pop("_comment", None)
    if isinstance(data.get("symbol"), dict):
        data["symbol"] = MT5Symbol(**data["symbol"])
    return MT5SymbolDetails(**data)


@pytest.fixture()
def eurusd_details() -> MT5SymbolDetails:
    return _load_symbol_details("symbol_info_eurusd.json")


@pytest.fixture()
def ustec_details() -> MT5SymbolDetails:
    return _load_symbol_details("symbol_info_ustec.json")


@pytest.fixture()
def btcusd_details() -> MT5SymbolDetails:
    return _load_symbol_details("symbol_info_btcusd.json")


# ---------------------------------------------------------------------------
# parse_instrument — instrument type dispatch
# ---------------------------------------------------------------------------


def test_parse_eurusd_with_profile_yields_currency_pair(eurusd_details):
    """EURUSD with TICKMILL_DEMO_PROFILE must resolve to CurrencyPair (FOREX mode=0)."""
    result = parse_instrument(eurusd_details, venue_profile=TICKMILL_DEMO_PROFILE)
    assert isinstance(result, CurrencyPair)


def test_parse_eurusd_without_profile_yields_cfd(eurusd_details):
    """Without a VenueProfile, parse_instrument falls back to parse_cfd_contract."""
    result = parse_instrument(eurusd_details, venue_profile=None)
    assert isinstance(result, Cfd)


def test_parse_ustec_with_profile_yields_cfd(ustec_details):
    """USTEC (CFDINDEX, mode=3) with profile resolves to Cfd."""
    result = parse_instrument(ustec_details, venue_profile=TICKMILL_DEMO_PROFILE)
    assert isinstance(result, Cfd)


def test_parse_btcusd_with_profile_yields_cfd(btcusd_details):
    """BTCUSD (CFD, mode=2) with profile resolves to Cfd."""
    result = parse_instrument(btcusd_details, venue_profile=TICKMILL_DEMO_PROFILE)
    assert isinstance(result, Cfd)


# ---------------------------------------------------------------------------
# parse_instrument — instrument identity
# ---------------------------------------------------------------------------


def test_parse_eurusd_instrument_id(eurusd_details):
    result = parse_instrument(eurusd_details, venue_profile=TICKMILL_DEMO_PROFILE)
    assert result.id.symbol.value == "EURUSD"
    assert result.id.venue.value == "METATRADER_5"


def test_parse_ustec_instrument_id(ustec_details):
    result = parse_instrument(ustec_details, venue_profile=TICKMILL_DEMO_PROFILE)
    assert result.id.symbol.value == "USTEC"


# ---------------------------------------------------------------------------
# parse_currency_pair_contract — field-level assertions
# ---------------------------------------------------------------------------


def test_parse_eurusd_currencies(eurusd_details):
    instrument_id = mt5_symbol_to_instrument_id(eurusd_details.symbol)
    result = parse_currency_pair_contract(eurusd_details, instrument_id)
    assert result.base_currency.code == "EUR"
    assert result.quote_currency.code == "USD"


def test_parse_eurusd_price_precision(eurusd_details):
    instrument_id = mt5_symbol_to_instrument_id(eurusd_details.symbol)
    result = parse_currency_pair_contract(eurusd_details, instrument_id)
    assert result.price_precision == 5


def test_parse_eurusd_price_increment(eurusd_details):
    instrument_id = mt5_symbol_to_instrument_id(eurusd_details.symbol)
    result = parse_currency_pair_contract(eurusd_details, instrument_id)
    assert result.price_increment == Price(0.00001, 5)


def test_parse_eurusd_size_precision(eurusd_details):
    instrument_id = mt5_symbol_to_instrument_id(eurusd_details.symbol)
    result = parse_currency_pair_contract(eurusd_details, instrument_id)
    assert result.size_precision == 2


def test_parse_eurusd_quantity_constraints(eurusd_details):
    instrument_id = mt5_symbol_to_instrument_id(eurusd_details.symbol)
    result = parse_currency_pair_contract(eurusd_details, instrument_id)
    assert result.min_quantity == Quantity(0.01, 2)
    assert result.max_quantity == Quantity(100.0, 2)  # Tickmill-Demo: volume_max=100.0


# ---------------------------------------------------------------------------
# parse_cfd_contract — asset class and field-level assertions
# ---------------------------------------------------------------------------


def test_parse_ustec_asset_class_is_index(ustec_details):
    instrument_id = mt5_symbol_to_instrument_id(ustec_details.symbol)
    result = parse_cfd_contract(ustec_details, instrument_id)
    assert result.asset_class == AssetClass.INDEX


def test_parse_btcusd_asset_class_is_cryptocurrency(btcusd_details):
    instrument_id = mt5_symbol_to_instrument_id(btcusd_details.symbol)
    result = parse_cfd_contract(btcusd_details, instrument_id)
    assert result.asset_class == AssetClass.CRYPTOCURRENCY


def test_parse_ustec_price_precision(ustec_details):
    instrument_id = mt5_symbol_to_instrument_id(ustec_details.symbol)
    result = parse_cfd_contract(ustec_details, instrument_id)
    assert result.price_precision == 2
    assert result.price_increment == Price(0.01, 2)


def test_parse_btcusd_quantity_constraints(btcusd_details):
    instrument_id = mt5_symbol_to_instrument_id(btcusd_details.symbol)
    result = parse_cfd_contract(btcusd_details, instrument_id)
    assert result.min_quantity == Quantity(0.01, 2)
    assert result.max_quantity == Quantity(30.0, 2)  # Tickmill-Demo: volume_max=30.0


def test_parse_ustec_quote_currency(ustec_details):
    instrument_id = mt5_symbol_to_instrument_id(ustec_details.symbol)
    result = parse_cfd_contract(ustec_details, instrument_id)
    assert result.quote_currency.code == "USD"


# ---------------------------------------------------------------------------
# sec_type_to_asset_class — path prefix mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path,expected", [
    ("Forex\\EURUSD",    AssetClass.FX),
    ("Indexes\\USTEC",   AssetClass.INDEX),
    ("Crypto\\BTCUSD",   AssetClass.CRYPTOCURRENCY),
    ("Metals\\XAUUSD",   AssetClass.COMMODITY),
    ("Energy\\USOIL",    AssetClass.COMMODITY),
    ("CFD-2\\CUSTOM",    AssetClass.INDEX),   # broker-specific CFD prefix → INDEX
    ("Equities\\AAPL",   AssetClass.EQUITY),
])
def test_sec_type_to_asset_class(path, expected):
    under_sec_type = path.split("\\")[0].upper()
    assert sec_type_to_asset_class(under_sec_type) == expected


# ---------------------------------------------------------------------------
# Fixture loading — guard against stale/broken fixture files
# ---------------------------------------------------------------------------


def test_fixture_files_are_loadable_and_have_required_fields():
    """
    All fixture files in tests/test_data/symbol_info_*.json must be loadable
    as MT5SymbolDetails and have the minimum fields required by parse_instrument.
    """
    required = {"digits", "trade_tick_size", "volume_step", "volume_min", "volume_max",
                "currency_profit", "trade_calc_mode"}
    for fixture_file in sorted(_TEST_DATA_DIR.glob("symbol_info_*.json")):
        data = json.loads(fixture_file.read_text())
        data.pop("_comment", None)
        missing = required - set(data.keys())
        assert not missing, (
            f"{fixture_file.name} is missing required fields: {missing}"
        )
        # Must be constructible as MT5SymbolDetails
        if isinstance(data.get("symbol"), dict):
            data["symbol"] = MT5Symbol(**data["symbol"])
        details = MT5SymbolDetails(**data)
        assert details.digits >= 0
        assert details.trade_tick_size >= 0.0
