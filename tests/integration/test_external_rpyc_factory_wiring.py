import asyncio
import rpyc
import pytest
from unittest.mock import MagicMock, patch, ANY

from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_trader.model.identifiers import TraderId

from nautilus_mt5.factories import (
    MT5LiveDataClientFactory,
    MT5LiveExecClientFactory,
    MT5_CLIENTS,
)
from nautilus_mt5.constants import MT5_VENUE
from nautilus_mt5.config import (
    MetaTrader5DataClientConfig,
    MetaTrader5ExecClientConfig,
    ExternalRPyCTerminalConfig,
)
from nautilus_mt5.client.types import MT5TerminalAccessMode
from tests.support.fake_mt5_rpyc_bridge import make_fake_mt5_rpyc_connection

@pytest.fixture(autouse=True)
def clear_mt5_clients():
    """Clear the global MT5_CLIENTS cache before each test."""
    MT5_CLIENTS.clear()
    yield
    MT5_CLIENTS.clear()

@pytest.fixture
def mock_rpyc_connect():
    """Fixture to mock rpyc.connect to return a fake connection."""
    with patch("rpyc.connect") as mock:
        mock.return_value = make_fake_mt5_rpyc_connection()
        yield mock

@pytest.fixture
def nautilus_components():
    """Fixture to provide real but isolated NautilusTrader components."""
    clock = LiveClock()
    msgbus = MessageBus(TraderId("TEST-TRADER"), clock)
    cache = Cache()
    loop = asyncio.get_event_loop()
    return loop, clock, msgbus, cache

def test_data_client_via_factory_uses_external_rpyc(mock_rpyc_connect, nautilus_components):
    """
    Case 1: Data client via factory uses EXTERNAL_RPYC.
    """
    loop, clock, msgbus, cache = nautilus_components

    host = "127.0.0.1"
    port = 18812

    config = MetaTrader5DataClientConfig(
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=ExternalRPyCTerminalConfig(
            host=host,
            port=port,
            keep_alive=False,
        ),
        managed_terminal=None,
        dockerized_gateway=None,
    )

    # Call the factory
    client = MT5LiveDataClientFactory.create(
        loop=loop,
        name="test-data-client",
        config=config,
        msgbus=msgbus,
        cache=cache,
        clock=clock,
    )

    # Validations
    assert client is not None
    # Check that the underlying MT5 client has correct settings
    mt5_client = client._client
    assert mt5_client._terminal_access == MT5TerminalAccessMode.EXTERNAL_RPYC
    assert mt5_client._mt5_config["rpyc"].host == host
    assert mt5_client._mt5_config["rpyc"].port == port

    # Ensure legacy/unintended configs are None
    assert config.dockerized_gateway is None
    assert config.managed_terminal is None

    # Ensure rpyc.connect was called with correct host/port
    # We use ANY for config because MetaTrader5 class adds its own rpyc_config dict
    mock_rpyc_connect.assert_called_with(host, port, config=ANY, keepalive=False)

def test_execution_client_via_factory_uses_external_rpyc(mock_rpyc_connect, nautilus_components):
    """
    Case 2: Execution client via factory uses EXTERNAL_RPYC.
    """
    loop, clock, msgbus, cache = nautilus_components

    host = "127.0.0.1"
    port = 18812
    account_id = "123456"

    config = MetaTrader5ExecClientConfig(
        client_id=1,
        account_id=account_id,
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=ExternalRPyCTerminalConfig(
            host=host,
            port=port,
            keep_alive=False,
        ),
        managed_terminal=None,
        dockerized_gateway=None,
    )

    # Call the factory
    client = MT5LiveExecClientFactory.create(
        loop=loop,
        name=MT5_VENUE.value,
        config=config,
        msgbus=msgbus,
        cache=cache,
        clock=clock,
    )

    # Validations
    assert client is not None
    mt5_client = client._client
    assert mt5_client._terminal_access == MT5TerminalAccessMode.EXTERNAL_RPYC

    # Ensure no legacy/unintended fields used
    assert config.dockerized_gateway is None
    assert config.managed_terminal is None

    # Check account ID was correctly preserved in wiring (though not the main focus)
    assert str(account_id) in str(client.account_id)

def test_no_legacy_fallbacks_reintroduced():
    """
    Case 3: Ensure legacy fields are None and not required.
    """
    config_data = MetaTrader5DataClientConfig(
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=ExternalRPyCTerminalConfig(host="localhost", port=18812)
    )

    assert config_data.dockerized_gateway is None
    assert config_data.managed_terminal is None
    # rpyc_config is a legacy field that should remain None in EXTERNAL_RPYC mode
    assert config_data.rpyc_config is None

    config_exec = MetaTrader5ExecClientConfig(
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=ExternalRPyCTerminalConfig(host="localhost", port=18812)
    )

    assert config_exec.dockerized_gateway is None
    assert config_exec.managed_terminal is None
    assert config_exec.rpyc_config is None
