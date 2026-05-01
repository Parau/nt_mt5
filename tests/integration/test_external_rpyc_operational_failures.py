import asyncio
import pytest
import rpyc
from unittest.mock import MagicMock

from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock
from nautilus_trader.common.component import MessageBus
from nautilus_trader.model.identifiers import TraderId
from nautilus_trader.test_kit.functions import eventually

from nautilus_mt5.client.types import MT5TerminalAccessMode, TerminalConnectionState
from nautilus_mt5.config import ExternalRPyCTerminalConfig, MetaTrader5DataClientConfig
from nautilus_mt5.factories import get_resolved_mt5_client, MT5_CLIENTS
from tests.support.fake_mt5_rpyc_bridge import make_fake_mt5_rpyc_connection, FakeMT5RPyCRoot


@pytest.fixture
def clean_factory_cache():
    """
    Ensure MT5_CLIENTS factory cache is clean before and after each test.
    """
    MT5_CLIENTS.clear()
    yield
    MT5_CLIENTS.clear()


@pytest.fixture
def nautilus_components(event_loop):
    loop = event_loop
    clock = LiveClock()
    msgbus = MessageBus(TraderId("TEST-1"), clock)
    cache = Cache()
    return loop, clock, msgbus, cache


def get_config():
    external_rpyc_config = ExternalRPyCTerminalConfig(
        host="127.0.0.1",
        port=18812,
        keep_alive=True,
        timeout_secs=30.0
    )

    return MetaTrader5DataClientConfig(
        client_id=1,
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=external_rpyc_config
    )


@pytest.mark.asyncio
async def test_endpoint_unreachable_connection_refused(monkeypatch, clean_factory_cache, nautilus_components):
    """
    Test that a ConnectionRefusedError during rpyc.connect results in a controlled error.
    """
    def mock_rpyc_connect(*args, **kwargs):
        raise ConnectionRefusedError("[Errno 111] Connection refused")

    monkeypatch.setattr(rpyc, "connect", mock_rpyc_connect)
    monkeypatch.setenv("MT5_MAX_CONNECTION_ATTEMPTS", "1")

    loop, clock, msgbus, cache = nautilus_components
    config = get_config()

    client = get_resolved_mt5_client(loop, msgbus, cache, clock, config)

    # Wait for the client to process the failure
    await eventually(lambda: client._last_connection_error is not None)

    # Ensure client is NOT ready
    # In some failure cases, _stop() might have been called, but we want to be sure it never reached 'ready'
    assert not client._is_client_ready.is_set()
    assert client.get_conn_state() != TerminalConnectionState.CONNECTED

    # Verify diagnostic info
    # Initial Connection failure raises RuntimeError in MetaTrader5.__init__
    assert isinstance(client._last_connection_error, RuntimeError)
    assert "external_rpyc gateway unreachable" in str(client._last_connection_error)
    assert f"{config.external_rpyc.host}:{config.external_rpyc.port}" in str(client._last_connection_error)

@pytest.mark.asyncio
async def test_initialize_returns_false(monkeypatch, clean_factory_cache, nautilus_components):
    """
    Test that initialize() returning False results in a controlled error.
    """
    fake_connection = make_fake_mt5_rpyc_connection()
    fake_root = fake_connection.root

    # Configure fake root to fail initialization
    def failing_initialize(*a, **k):
        fake_root._record_call("initialize", a, k)
        return False
    fake_root.exposed_initialize = failing_initialize

    def failing_last_error(*a, **k):
        fake_root._record_call("last_error", a, k)
        return (100, "MT5 initialize failed")
    fake_root.exposed_last_error = failing_last_error

    monkeypatch.setattr(rpyc, "connect", lambda *a, **k: fake_connection)
    monkeypatch.setenv("MT5_MAX_CONNECTION_ATTEMPTS", "1")

    loop, clock, msgbus, cache = nautilus_components
    config = get_config()

    client = get_resolved_mt5_client(loop, msgbus, cache, clock, config)

    await eventually(lambda: client._last_connection_error is not None)
    assert not client._is_client_ready.is_set()
    assert client.get_conn_state() != TerminalConnectionState.CONNECTED

    # Verify diagnostic info
    # MetaTrader5ClientConnectionMixin._handle_connection_error raises ValueError
    assert isinstance(client._last_connection_error, (ConnectionError, ValueError))

    # Verify RPC calls
    method_names = [call.method for call in fake_root.calls]
    assert "initialize" in method_names
    assert "last_error" in method_names
    assert "terminal_info" not in method_names

@pytest.mark.asyncio
async def test_terminal_info_returns_none(monkeypatch, clean_factory_cache, nautilus_components):
    """
    Test that terminal_info() returning None results in a controlled error.
    """
    fake_connection = make_fake_mt5_rpyc_connection()
    fake_root = fake_connection.root

    def failing_terminal_info(*a, **k):
        fake_root._record_call("terminal_info", a, k)
        return None
    fake_root.exposed_terminal_info = failing_terminal_info

    monkeypatch.setattr(rpyc, "connect", lambda *a, **k: fake_connection)
    monkeypatch.setenv("MT5_MAX_CONNECTION_ATTEMPTS", "1")

    loop, clock, msgbus, cache = nautilus_components
    config = get_config()

    client = get_resolved_mt5_client(loop, msgbus, cache, clock, config)

    await eventually(lambda: client._last_connection_error is not None)
    assert not client._is_client_ready.is_set()
    assert client.get_conn_state() != TerminalConnectionState.CONNECTED

    # Verify diagnostic info
    assert isinstance(client._last_connection_error, (ConnectionError, ValueError))
    assert "terminal_info indisponível" in str(client._last_connection_error)

    # Verify RPC calls
    method_names = [call.method for call in fake_root.calls]
    assert "initialize" in method_names
    assert "terminal_info" in method_names
    assert "account_info" not in method_names

@pytest.mark.asyncio
async def test_terminal_info_connected_is_false(monkeypatch, clean_factory_cache, nautilus_components):
    """
    Test that terminal_info().connected being False results in a controlled error.
    """
    fake_connection = make_fake_mt5_rpyc_connection()
    fake_root = fake_connection.root

    def failing_terminal_info(*a, **k):
        fake_root._record_call("terminal_info", a, k)
        return {
            "connected": False,
            "trade_allowed": False,
            "build": 3000
        }
    fake_root.exposed_terminal_info = failing_terminal_info

    monkeypatch.setattr(rpyc, "connect", lambda *a, **k: fake_connection)
    monkeypatch.setenv("MT5_MAX_CONNECTION_ATTEMPTS", "1")

    loop, clock, msgbus, cache = nautilus_components
    config = get_config()

    client = get_resolved_mt5_client(loop, msgbus, cache, clock, config)

    await eventually(lambda: client._last_connection_error is not None)
    assert not client._is_client_ready.is_set()
    assert client.get_conn_state() != TerminalConnectionState.CONNECTED

    # Verify diagnostic info
    assert isinstance(client._last_connection_error, (ConnectionError, ValueError))
    assert "MetaTrader 5 terminal is not connected to a server via gateway" in str(client._last_connection_error)

    # Verify RPC calls
    method_names = [call.method for call in fake_root.calls]
    assert "initialize" in method_names
    assert "terminal_info" in method_names
    assert "account_info" not in method_names

@pytest.mark.asyncio
async def test_account_info_returns_none(monkeypatch, clean_factory_cache, nautilus_components):
    """
    Test that account_info() returning None results in a controlled error.
    """
    fake_connection = make_fake_mt5_rpyc_connection()
    fake_root = fake_connection.root

    def failing_account_info(*a, **k):
        fake_root._record_call("account_info", a, k)
        return None
    fake_root.exposed_account_info = failing_account_info

    monkeypatch.setattr(rpyc, "connect", lambda *a, **k: fake_connection)
    monkeypatch.setenv("MT5_MAX_CONNECTION_ATTEMPTS", "1")

    loop, clock, msgbus, cache = nautilus_components
    config = get_config()

    client = get_resolved_mt5_client(loop, msgbus, cache, clock, config)

    await eventually(lambda: client._last_connection_error is not None)
    assert not client._is_client_ready.is_set()
    assert client.get_conn_state() != TerminalConnectionState.CONNECTED

    # Verify diagnostic info
    assert isinstance(client._last_connection_error, (ConnectionError, ValueError))
    assert "account_info indisponível" in str(client._last_connection_error)

    # Verify RPC calls
    method_names = [call.method for call in fake_root.calls]
    assert "initialize" in method_names
    assert "terminal_info" in method_names
    assert "account_info" in method_names
