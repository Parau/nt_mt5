import asyncio
import pytest
import rpyc
from unittest.mock import MagicMock

from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock
from nautilus_trader.common.component import MessageBus
from nautilus_trader.model.identifiers import TraderId

from nautilus_mt5.client.types import MT5TerminalAccessMode
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

    # Mock logger
    from nautilus_trader.common.component import Logger
    mock_log = MagicMock(spec=Logger)
    monkeypatch.setattr("nautilus_mt5.client.client.MetaTrader5Client._log", mock_log)

    client = get_resolved_mt5_client(loop, msgbus, cache, clock, config)

    await asyncio.sleep(0.5)

    assert not client._is_client_ready.is_set()

    # Verify logger was called with controlled error message
    # In connection.py: self._log.error(f"Connection failed: {e}")
    # e will be the RuntimeError we raised in MetaTrader5.__init__
    error_calls = [call.args[0] for call in mock_log.error.call_args_list]
    combined_errors = " ".join(error_calls)
    assert "external_rpyc gateway unreachable" in combined_errors
    assert f"{config.external_rpyc.host}:{config.external_rpyc.port}" in combined_errors

@pytest.mark.asyncio
async def test_initialize_returns_false(monkeypatch, clean_factory_cache, nautilus_components):
    """
    Test that initialize() returning False results in a controlled error.
    """
    fake_connection = make_fake_mt5_rpyc_connection()
    fake_root = fake_connection.root

    # Configure fake root to fail initialization
    monkeypatch.setattr(fake_root, "exposed_initialize", lambda *a, **k: False)
    monkeypatch.setattr(fake_root, "exposed_last_error", lambda *a, **k: (100, "MT5 initialize failed"))

    monkeypatch.setattr(rpyc, "connect", lambda *a, **k: fake_connection)
    monkeypatch.setenv("MT5_MAX_CONNECTION_ATTEMPTS", "1")

    loop, clock, msgbus, cache = nautilus_components
    config = get_config()

    # Mock logger
    from nautilus_trader.common.component import Logger
    mock_log = MagicMock(spec=Logger)
    monkeypatch.setattr("nautilus_mt5.client.client.MetaTrader5Client._log", mock_log)

    client = get_resolved_mt5_client(loop, msgbus, cache, clock, config)

    await asyncio.sleep(0.5)
    assert not client._is_client_ready.is_set()

    error_calls = [call.args[0] for call in mock_log.error.call_args_list]
    combined_errors = " ".join(error_calls)
    assert "Failed to initialize MT5 terminal via gateway" in combined_errors
    assert "code=100" in combined_errors
    assert "msg=MT5 initialize failed" in combined_errors

@pytest.mark.asyncio
async def test_terminal_info_returns_none(monkeypatch, clean_factory_cache, nautilus_components):
    """
    Test that terminal_info() returning None results in a controlled error.
    """
    fake_connection = make_fake_mt5_rpyc_connection()
    fake_root = fake_connection.root

    monkeypatch.setattr(fake_root, "exposed_terminal_info", lambda *a, **k: None)

    monkeypatch.setattr(rpyc, "connect", lambda *a, **k: fake_connection)
    monkeypatch.setenv("MT5_MAX_CONNECTION_ATTEMPTS", "1")

    loop, clock, msgbus, cache = nautilus_components
    config = get_config()

    # Mock logger
    from nautilus_trader.common.component import Logger
    mock_log = MagicMock(spec=Logger)
    monkeypatch.setattr("nautilus_mt5.client.client.MetaTrader5Client._log", mock_log)

    client = get_resolved_mt5_client(loop, msgbus, cache, clock, config)

    await asyncio.sleep(0.5)
    assert not client._is_client_ready.is_set()

    error_calls = [call.args[0] for call in mock_log.error.call_args_list]
    combined_errors = " ".join(error_calls)
    assert "terminal_info indisponível" in combined_errors

@pytest.mark.asyncio
async def test_terminal_info_connected_is_false(monkeypatch, clean_factory_cache, nautilus_components):
    """
    Test that terminal_info().connected being False results in a controlled error.
    """
    fake_connection = make_fake_mt5_rpyc_connection()
    fake_root = fake_connection.root

    monkeypatch.setattr(fake_root, "exposed_terminal_info", lambda *a, **k: {
        "connected": False,
        "trade_allowed": False,
        "build": 3000
    })

    monkeypatch.setattr(rpyc, "connect", lambda *a, **k: fake_connection)
    monkeypatch.setenv("MT5_MAX_CONNECTION_ATTEMPTS", "1")

    loop, clock, msgbus, cache = nautilus_components
    config = get_config()

    # Mock logger
    from nautilus_trader.common.component import Logger
    mock_log = MagicMock(spec=Logger)
    monkeypatch.setattr("nautilus_mt5.client.client.MetaTrader5Client._log", mock_log)

    client = get_resolved_mt5_client(loop, msgbus, cache, clock, config)

    await asyncio.sleep(0.5)
    assert not client._is_client_ready.is_set()

    error_calls = [call.args[0] for call in mock_log.error.call_args_list]
    combined_errors = " ".join(error_calls)
    assert "MetaTrader 5 terminal is not connected to a server via gateway" in combined_errors

@pytest.mark.asyncio
async def test_account_info_returns_none(monkeypatch, clean_factory_cache, nautilus_components):
    """
    Test that account_info() returning None results in a controlled error.
    """
    fake_connection = make_fake_mt5_rpyc_connection()
    fake_root = fake_connection.root

    monkeypatch.setattr(fake_root, "exposed_account_info", lambda *a, **k: None)

    monkeypatch.setattr(rpyc, "connect", lambda *a, **k: fake_connection)
    monkeypatch.setenv("MT5_MAX_CONNECTION_ATTEMPTS", "1")

    loop, clock, msgbus, cache = nautilus_components
    config = get_config()

    # Mock logger
    from nautilus_trader.common.component import Logger
    mock_log = MagicMock(spec=Logger)
    monkeypatch.setattr("nautilus_mt5.client.client.MetaTrader5Client._log", mock_log)

    client = get_resolved_mt5_client(loop, msgbus, cache, clock, config)

    await asyncio.sleep(0.5)
    assert not client._is_client_ready.is_set()

    error_calls = [call.args[0] for call in mock_log.error.call_args_list]
    combined_errors = " ".join(error_calls)
    assert "account_info indisponível" in combined_errors
