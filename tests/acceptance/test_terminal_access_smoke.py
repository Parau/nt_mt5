import asyncio
import pytest
from unittest.mock import MagicMock, patch

from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_trader.model.identifiers import TraderId

from nautilus_mt5.client.types import MT5TerminalAccessMode, ManagedTerminalBackend
from nautilus_mt5.config import (
    MetaTrader5DataClientConfig,
    MetaTrader5ExecClientConfig,
    ExternalRPyCTerminalConfig,
    ManagedTerminalConfig,
    DockerizedMT5TerminalConfig,
)
from nautilus_mt5.factories import MT5LiveDataClientFactory, MT5LiveExecClientFactory
from nautilus_mt5.providers import MetaTrader5InstrumentProvider

@pytest.fixture
def mock_components():
    clock = MagicMock(spec=LiveClock)
    msgbus = MagicMock(spec=MessageBus)
    cache = MagicMock(spec=Cache)
    return {
        "loop": asyncio.get_event_loop(),
        "msgbus": msgbus,
        "cache": cache,
        "clock": clock,
    }

@pytest.fixture(autouse=True)
def mock_mt5_clients_registry(monkeypatch):
    """
    Ensure MT5_CLIENTS registry is isolated for each test.
    """
    local_clients = {}
    monkeypatch.setattr("nautilus_mt5.factories.MT5_CLIENTS", local_clients)
    return local_clients

def test_data_client_wiring_external_rpyc(mock_components):
    """
    Verify that MT5LiveDataClientFactory.create works correctly with EXTERNAL_RPYC.
    """
    config = MetaTrader5DataClientConfig(
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=ExternalRPyCTerminalConfig(host="127.0.0.1", port=18812),
        client_id=1,
    )

    with patch("nautilus_mt5.factories.get_resolved_mt5_client") as mock_get_client:
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        with patch("nautilus_mt5.factories.MetaTrader5DataClient") as mock_data_client_class:
            data_client = MT5LiveDataClientFactory.create(
                loop=mock_components["loop"],
                name="MT5_DATA",
                config=config,
                msgbus=mock_components["msgbus"],
                cache=mock_components["cache"],
                clock=mock_components["clock"],
            )

            assert data_client is not None
            mock_get_client.assert_called_once()
            args, kwargs = mock_get_client.call_args
            assert kwargs["config"].terminal_access == MT5TerminalAccessMode.EXTERNAL_RPYC

            # Verify InstrumentProvider wiring
            mock_data_client_class.assert_called_once()
            _, client_kwargs = mock_data_client_class.call_args
            assert "instrument_provider" in client_kwargs
            assert isinstance(client_kwargs["instrument_provider"], MetaTrader5InstrumentProvider)

def test_exec_client_wiring_external_rpyc(mock_components):
    """
    Verify that MT5LiveExecClientFactory.create works correctly with EXTERNAL_RPYC.
    """
    config = MetaTrader5ExecClientConfig(
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=ExternalRPyCTerminalConfig(host="127.0.0.1", port=18812),
        client_id=1,
        account_id="123456",
    )

    with patch("nautilus_mt5.factories.get_resolved_mt5_client") as mock_get_client:
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        with patch("nautilus_mt5.factories.MetaTrader5ExecutionClient") as mock_exec_client_class:
            exec_client = MT5LiveExecClientFactory.create(
                loop=mock_components["loop"],
                name="MT5_EXEC",
                config=config,
                msgbus=mock_components["msgbus"],
                cache=mock_components["cache"],
                clock=mock_components["clock"],
            )

            assert exec_client is not None
            mock_get_client.assert_called_once()
            args, kwargs = mock_get_client.call_args
            assert kwargs["config"].terminal_access == MT5TerminalAccessMode.EXTERNAL_RPYC

            # Verify InstrumentProvider wiring
            mock_exec_client_class.assert_called_once()
            _, client_kwargs = mock_exec_client_class.call_args
            assert "instrument_provider" in client_kwargs
            assert isinstance(client_kwargs["instrument_provider"], MetaTrader5InstrumentProvider)

def test_managed_terminal_wiring_distinct(mock_components):
    """
    Verify that MANAGED_TERMINAL is recognized as a distinct mode and currently raises RuntimeError.
    """
    config = MetaTrader5DataClientConfig(
        terminal_access=MT5TerminalAccessMode.MANAGED_TERMINAL,
        managed_terminal=ManagedTerminalConfig(backend=ManagedTerminalBackend.DOCKERIZED),
    )

    with pytest.raises(RuntimeError, match="MANAGED_TERMINAL access mode was recognized"):
        MT5LiveDataClientFactory.create(
            loop=mock_components["loop"],
            name="MT5_DATA",
            config=config,
            msgbus=mock_components["msgbus"],
            cache=mock_components["cache"],
            clock=mock_components["clock"],
        )

def test_reject_legacy_dockerized_gateway_with_managed(mock_components):
    """
    Verify rejection of legacy top-level dockerized_gateway when using MANAGED_TERMINAL.
    """
    config = MetaTrader5DataClientConfig(
        terminal_access=MT5TerminalAccessMode.MANAGED_TERMINAL,
        managed_terminal=ManagedTerminalConfig(backend=ManagedTerminalBackend.DOCKERIZED),
        dockerized_gateway=DockerizedMT5TerminalConfig(),
    )

    with pytest.raises(ValueError, match="dockerized_gateway config at top-level is legacy"):
        MT5LiveDataClientFactory.create(
            loop=mock_components["loop"],
            name="MT5_DATA",
            config=config,
            msgbus=mock_components["msgbus"],
            cache=mock_components["cache"],
            clock=mock_components["clock"],
        )
