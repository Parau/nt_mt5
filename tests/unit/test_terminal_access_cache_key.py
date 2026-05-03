import asyncio
import pytest
from unittest.mock import MagicMock
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_mt5.client.types import MT5TerminalAccessMode
from nautilus_mt5.config import (
    MetaTrader5DataClientConfig,
    ExternalRPyCTerminalConfig,
)
from nautilus_mt5.factories import get_resolved_mt5_client

@pytest.fixture
def mock_components():
    return {
        "loop": asyncio.new_event_loop(),
        "msgbus": MagicMock(spec=MessageBus),
        "cache": MagicMock(spec=Cache),
        "clock": MagicMock(spec=LiveClock),
    }

@pytest.fixture(autouse=True)
def mock_mt5_clients_registry(monkeypatch):
    """
    Ensure MT5_CLIENTS registry is isolated for each test.
    """
    local_clients = {}
    monkeypatch.setattr("nautilus_mt5.factories.MT5_CLIENTS", local_clients)
    return local_clients

def test_external_rpyc_cache_key_distinguishes_keep_alive(mock_components, mock_mt5_clients_registry, monkeypatch):
    """
    Test that the cache key for EXTERNAL_RPYC distinguishes between different keep_alive values.
    """
    # Mock MetaTrader5Client to avoid real connections
    # We use side_effect to return a new mock instance on each call
    mock_client_class = MagicMock(side_effect=lambda *args, **kwargs: MagicMock())
    monkeypatch.setattr("nautilus_mt5.factories.MetaTrader5Client", mock_client_class)

    config_keep_alive_true = MetaTrader5DataClientConfig(
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=ExternalRPyCTerminalConfig(
            host="127.0.0.1",
            port=18812,
            keep_alive=True,
        ),
        client_id=1,
    )

    config_keep_alive_false = MetaTrader5DataClientConfig(
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=ExternalRPyCTerminalConfig(
            host="127.0.0.1",
            port=18812,
            keep_alive=False,
        ),
        client_id=1,
    )

    client_true = get_resolved_mt5_client(
        loop=mock_components["loop"],
        msgbus=mock_components["msgbus"],
        cache=mock_components["cache"],
        clock=mock_components["clock"],
        config=config_keep_alive_true,
    )

    client_false = get_resolved_mt5_client(
        loop=mock_components["loop"],
        msgbus=mock_components["msgbus"],
        cache=mock_components["cache"],
        clock=mock_components["clock"],
        config=config_keep_alive_false,
    )

    # ASSERTIONS
    # Expected behavior: they should be different instances because keep_alive is different
    assert client_true is not client_false
    assert len(mock_mt5_clients_registry) == 2

    # Check that keep_alive was correctly passed to the clients
    assert mock_client_class.call_count == 2

    # First call (keep_alive=True)
    args_true, kwargs_true = mock_client_class.call_args_list[0]
    assert kwargs_true["mt5_config"]["rpyc"].keep_alive is True

    # Second call (keep_alive=False)
    args_false, kwargs_false = mock_client_class.call_args_list[1]
    assert kwargs_false["mt5_config"]["rpyc"].keep_alive is False
