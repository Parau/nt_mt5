"""
test_instrument_provider_external_rpyc.py
Nautilus-level instrument provider tests for EXTERNAL_RPYC mode.

Exercises the path:
    MT5LiveDataClientFactory.create(...)
    → MetaTrader5InstrumentProvider.initialize()
    → MetaTrader5Client.get_symbol_details()  [via fake RPyC]
    → parse_instrument()
    → NautilusCache.add_instrument()

Supported symbols under test: EURUSD (Forex CFD), USTEC (Index CFD).
No real MT5, no live env vars.
"""
import asyncio

import pytest

from nautilus_mt5.client.types import MT5TerminalAccessMode
from nautilus_mt5.config import (
    ExternalRPyCTerminalConfig,
    MetaTrader5DataClientConfig,
    MetaTrader5InstrumentProviderConfig,
)
from nautilus_mt5.data_types import MT5Symbol
from nautilus_mt5.factories import MT5LiveDataClientFactory
from nautilus_mt5 import TICKMILL_DEMO_PROFILE


_RPYC_CONFIG = ExternalRPyCTerminalConfig(host="127.0.0.1", port=18812)


def _config_with_symbols(*symbols: str) -> MetaTrader5DataClientConfig:
    return MetaTrader5DataClientConfig(
        client_id=1,
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=_RPYC_CONFIG,
        instrument_provider=MetaTrader5InstrumentProviderConfig(
            load_symbols=frozenset(MT5Symbol(symbol=s) for s in symbols)
        ),
        venue_profile=TICKMILL_DEMO_PROFILE,
    )


@pytest.mark.asyncio
async def test_provider_loads_eurusd_via_factory(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    Provider loads EURUSD instrument via the factory pipeline with a fake bridge.
    The parsed instrument is accessible via instrument_provider.list_all().
    """
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop,
        name="MT5",
        config=_config_with_symbols("EURUSD"),
        msgbus=msgbus,
        cache=cache,
        clock=clock,
    )

    # _connect() calls _client._connect() (sets up RPyC), then provider.initialize().
    await data_client._connect()

    instruments = data_client.instrument_provider.list_all()
    symbols = [i.id.symbol.value for i in instruments]
    assert "EURUSD" in symbols


@pytest.mark.asyncio
async def test_provider_loads_ustec_via_factory(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    Provider loads USTEC (Index CFD) instrument via the factory pipeline.
    Confirms USTEC works end-to-end through fake bridge → parse_instrument → cache.
    """
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop,
        name="MT5",
        config=_config_with_symbols("USTEC"),
        msgbus=msgbus,
        cache=cache,
        clock=clock,
    )

    await data_client._connect()

    instruments = data_client.instrument_provider.list_all()
    symbols = [i.id.symbol.value for i in instruments]
    assert "USTEC" in symbols


@pytest.mark.asyncio
async def test_provider_instrument_in_nautilus_cache(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    After provider.initialize(), the instrument is present in the shared Nautilus cache,
    accessible via data_client._cache.instrument(instrument_id).
    """
    from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue

    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop,
        name="MT5",
        config=_config_with_symbols("USTEC"),
        msgbus=msgbus,
        cache=cache,
        clock=clock,
    )

    await data_client._connect()

    instrument_id = InstrumentId(Symbol("USTEC"), Venue("METATRADER_5"))
    instrument = data_client._cache.instrument(instrument_id)
    assert instrument is not None
    assert instrument.id.symbol.value == "USTEC"


@pytest.mark.asyncio
async def test_provider_fake_bridge_symbol_info_called(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    Verify that the fake bridge's exposed_symbol_info was called during
    provider.initialize() for the requested symbol.
    """
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()
    fake_conn = nautilus_mt5_harness

    data_client = MT5LiveDataClientFactory.create(
        loop=loop,
        name="MT5",
        config=_config_with_symbols("USTEC"),
        msgbus=msgbus,
        cache=cache,
        clock=clock,
    )

    # Capture calls that happen during _connect() → provider.initialize().
    fake_conn.root.reset_calls()
    await data_client._connect()

    calls = fake_conn.root.calls
    symbol_info_calls = [c for c in calls if c.method == "symbol_info"]
    assert any(c.args[0] == "USTEC" for c in symbol_info_calls), (
        f"symbol_info was not called for USTEC. All calls: {[c.method for c in calls]}"
    )
