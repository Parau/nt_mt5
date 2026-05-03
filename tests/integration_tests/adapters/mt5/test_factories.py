"""
test_factories.py — Nautilus-level factory wiring tests for the MT5 adapter.

Verifies that:
- MT5LiveDataClientFactory.create() returns a MetaTrader5DataClient.
- MT5LiveExecClientFactory.create() returns a MetaTrader5ExecutionClient.
- The factory caches the underlying MetaTrader5Client across calls with the same config.

No real MT5, no live env vars.
"""
import asyncio

import pytest

from nautilus_mt5.client.types import MT5TerminalAccessMode
from nautilus_mt5.config import (
    ExternalRPyCTerminalConfig,
    MetaTrader5DataClientConfig,
    MetaTrader5ExecClientConfig,
    MetaTrader5InstrumentProviderConfig,
)
from nautilus_mt5.data import MetaTrader5DataClient
from nautilus_mt5.execution import MetaTrader5ExecutionClient
from nautilus_mt5.factories import (
    MT5LiveDataClientFactory,
    MT5LiveExecClientFactory,
    MT5_CLIENTS,
)


_RPYC_CONFIG = ExternalRPyCTerminalConfig(host="127.0.0.1", port=18812)
_PROVIDER_CONFIG = MetaTrader5InstrumentProviderConfig()


def _data_config() -> MetaTrader5DataClientConfig:
    return MetaTrader5DataClientConfig(
        client_id=1,
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=_RPYC_CONFIG,
        instrument_provider=_PROVIDER_CONFIG,
    )


def _exec_config() -> MetaTrader5ExecClientConfig:
    return MetaTrader5ExecClientConfig(
        client_id=1,
        account_id="123456",
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=_RPYC_CONFIG,
        instrument_provider=_PROVIDER_CONFIG,
    )


@pytest.mark.asyncio
async def test_factory_creates_data_client(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """MT5LiveDataClientFactory.create returns a MetaTrader5DataClient."""
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop,
        name="MT5",
        config=_data_config(),
        msgbus=msgbus,
        cache=cache,
        clock=clock,
    )

    assert isinstance(data_client, MetaTrader5DataClient)
    # The underlying MT5Client was registered in the cache
    assert len(MT5_CLIENTS) == 1


@pytest.mark.asyncio
async def test_factory_creates_exec_client(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """MT5LiveExecClientFactory.create returns a MetaTrader5ExecutionClient."""
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    exec_client = MT5LiveExecClientFactory.create(
        loop=loop,
        name="MT5",
        config=_exec_config(),
        msgbus=msgbus,
        cache=cache,
        clock=clock,
    )

    assert isinstance(exec_client, MetaTrader5ExecutionClient)
    assert len(MT5_CLIENTS) == 1


@pytest.mark.asyncio
async def test_factory_caches_mt5_client_across_data_and_exec(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    When data client and exec client share the same RPyC config+client_id,
    the factory returns the same underlying MetaTrader5Client instance.
    """
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=_data_config(),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    exec_client = MT5LiveExecClientFactory.create(
        loop=loop, name="MT5", config=_exec_config(),
        msgbus=msgbus, cache=cache, clock=clock,
    )

    # Both clients share the same underlying MetaTrader5Client
    assert data_client._client is exec_client._client
    # Only one entry in the factory cache
    assert len(MT5_CLIENTS) == 1
