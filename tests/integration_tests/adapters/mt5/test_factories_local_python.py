"""
test_factories_local_python.py

Integration tests for the MT5 factory in LOCAL_PYTHON mode.

These tests exercise the factory wiring and validation paths for LOCAL_PYTHON
terminal access without requiring a real MT5 terminal or the MetaTrader5 package.

Tests:
    - Factory creates MetaTrader5DataClient for LOCAL_PYTHON config
    - Factory creates MetaTrader5ExecutionClient for LOCAL_PYTHON config
    - Factory caches client when called twice with identical config
    - Factory rejects local_python=None (ValueError)
    - Factory rejects external_rpyc set in LOCAL_PYTHON mode (ValueError)
"""
import asyncio

import pytest

from nautilus_mt5.client import MetaTrader5Client
from nautilus_mt5.client.types import MT5TerminalAccessMode
from nautilus_mt5.config import (
    ExternalRPyCTerminalConfig,
    LocalPythonTerminalConfig,
    MetaTrader5DataClientConfig,
    MetaTrader5ExecClientConfig,
    MetaTrader5InstrumentProviderConfig,
)
from nautilus_mt5.data import MetaTrader5DataClient
from nautilus_mt5.execution import MetaTrader5ExecutionClient
from nautilus_mt5.factories import MT5LiveDataClientFactory, MT5LiveExecClientFactory


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

_LP_CONFIG = LocalPythonTerminalConfig(
    path=None,
    login=25306658,
    password="demo_pw",
    server="Tickmill-Demo",
)


def _data_config_lp() -> MetaTrader5DataClientConfig:
    return MetaTrader5DataClientConfig(
        client_id=1,
        terminal_access=MT5TerminalAccessMode.LOCAL_PYTHON,
        local_python=_LP_CONFIG,
        instrument_provider=MetaTrader5InstrumentProviderConfig(),
    )


def _exec_config_lp() -> MetaTrader5ExecClientConfig:
    return MetaTrader5ExecClientConfig(
        client_id=1,
        account_id="25306658",
        terminal_access=MT5TerminalAccessMode.LOCAL_PYTHON,
        local_python=_LP_CONFIG,
        instrument_provider=MetaTrader5InstrumentProviderConfig(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_local_python_data_factory_creates_data_client(
    clean_factory_cache, nautilus_components, monkeypatch
):
    """
    MT5LiveDataClientFactory.create() returns a MetaTrader5DataClient
    when LOCAL_PYTHON mode is configured.
    """
    msgbus, cache, clock = nautilus_components

    def _fake_start(self):
        pass  # prevent actual connection

    monkeypatch.setattr(MetaTrader5Client, "_start", _fake_start)

    loop = asyncio.new_event_loop()
    try:
        client = MT5LiveDataClientFactory.create(
            loop=loop, name="MT5", config=_data_config_lp(),
            msgbus=msgbus, cache=cache, clock=clock,
        )
        assert isinstance(client, MetaTrader5DataClient)
    finally:
        loop.close()


def test_local_python_exec_factory_creates_exec_client(
    clean_factory_cache, nautilus_components, monkeypatch
):
    """
    MT5LiveExecClientFactory.create() returns a MetaTrader5ExecutionClient
    when LOCAL_PYTHON mode is configured.
    """
    msgbus, cache, clock = nautilus_components

    def _fake_start(self):
        pass

    monkeypatch.setattr(MetaTrader5Client, "_start", _fake_start)

    loop = asyncio.new_event_loop()
    try:
        client = MT5LiveExecClientFactory.create(
            loop=loop, name="MT5", config=_exec_config_lp(),
            msgbus=msgbus, cache=cache, clock=clock,
        )
        assert isinstance(client, MetaTrader5ExecutionClient)
    finally:
        loop.close()


def test_local_python_factory_caches_client(
    clean_factory_cache, nautilus_components, monkeypatch
):
    """
    Calling the factory twice with the same LOCAL_PYTHON config returns
    the same underlying MetaTrader5Client instance (cache hit).
    """
    msgbus, cache, clock = nautilus_components

    def _fake_start(self):
        pass

    monkeypatch.setattr(MetaTrader5Client, "_start", _fake_start)

    loop = asyncio.new_event_loop()
    try:
        data_client = MT5LiveDataClientFactory.create(
            loop=loop, name="MT5", config=_data_config_lp(),
            msgbus=msgbus, cache=cache, clock=clock,
        )
        exec_client = MT5LiveExecClientFactory.create(
            loop=loop, name="MT5", config=_exec_config_lp(),
            msgbus=msgbus, cache=cache, clock=clock,
        )
        # Both share the same underlying MetaTrader5Client
        assert data_client._client is exec_client._client
    finally:
        loop.close()


def test_local_python_factory_rejects_missing_local_python_config(
    clean_factory_cache, nautilus_components, monkeypatch
):
    """
    Factory raises ValueError when terminal_access=LOCAL_PYTHON but
    local_python config is None.
    """
    msgbus, cache, clock = nautilus_components

    def _fake_start(self):
        pass

    monkeypatch.setattr(MetaTrader5Client, "_start", _fake_start)

    bad_config = MetaTrader5DataClientConfig(
        client_id=1,
        terminal_access=MT5TerminalAccessMode.LOCAL_PYTHON,
        local_python=None,  # missing
        instrument_provider=MetaTrader5InstrumentProviderConfig(),
    )

    loop = asyncio.new_event_loop()
    try:
        with pytest.raises(ValueError, match="local_python config is required"):
            MT5LiveDataClientFactory.create(
                loop=loop, name="MT5", config=bad_config,
                msgbus=msgbus, cache=cache, clock=clock,
            )
    finally:
        loop.close()


def test_local_python_factory_rejects_external_rpyc_set(
    clean_factory_cache, nautilus_components, monkeypatch
):
    """
    Factory raises ValueError when terminal_access=LOCAL_PYTHON but
    external_rpyc is also set (conflicting config).
    """
    msgbus, cache, clock = nautilus_components

    def _fake_start(self):
        pass

    monkeypatch.setattr(MetaTrader5Client, "_start", _fake_start)

    bad_config = MetaTrader5DataClientConfig(
        client_id=1,
        terminal_access=MT5TerminalAccessMode.LOCAL_PYTHON,
        local_python=_LP_CONFIG,
        external_rpyc=ExternalRPyCTerminalConfig(host="127.0.0.1", port=18812),
        instrument_provider=MetaTrader5InstrumentProviderConfig(),
    )

    loop = asyncio.new_event_loop()
    try:
        with pytest.raises(ValueError, match="external_rpyc config must be None"):
            MT5LiveDataClientFactory.create(
                loop=loop, name="MT5", config=bad_config,
                msgbus=msgbus, cache=cache, clock=clock,
            )
    finally:
        loop.close()
