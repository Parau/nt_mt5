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
        "loop": asyncio.get_event_loop(),
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

class DummyMT5Client:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.started = False

    def start(self):
        self.started = True

def test_external_rpyc_cache_key_distinguishes_keep_alive(mock_components, mock_mt5_clients_registry, monkeypatch):
    """
    Caso 1 — keep_alive diferente gera clients distintos
    """
    monkeypatch.setattr("nautilus_mt5.factories.MetaTrader5Client", DummyMT5Client)

    def create_config(keep_alive):
        return MetaTrader5DataClientConfig(
            terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
            external_rpyc=ExternalRPyCTerminalConfig(
                host="127.0.0.1",
                port=18812,
                keep_alive=keep_alive,
                timeout_secs=10.0,
            ),
            client_id=1,
        )

    client_true = get_resolved_mt5_client(config=create_config(True), **mock_components)
    client_false = get_resolved_mt5_client(config=create_config(False), **mock_components)

    assert client_true is not client_false
    assert len(mock_mt5_clients_registry) == 2

def test_external_rpyc_cache_key_distinguishes_timeout_secs(mock_components, mock_mt5_clients_registry, monkeypatch):
    """
    Caso 2 — timeout_secs diferente gera clients distintos
    """
    monkeypatch.setattr("nautilus_mt5.factories.MetaTrader5Client", DummyMT5Client)

    def create_config(timeout):
        return MetaTrader5DataClientConfig(
            terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
            external_rpyc=ExternalRPyCTerminalConfig(
                host="127.0.0.1",
                port=18812,
                keep_alive=True,
                timeout_secs=timeout,
            ),
            client_id=1,
        )

    client_none = get_resolved_mt5_client(config=create_config(None), **mock_components)
    client_10 = get_resolved_mt5_client(config=create_config(10.0), **mock_components)

    assert client_none is not client_10
    assert len(mock_mt5_clients_registry) == 2

def test_external_rpyc_identical_configs_reuse_client(mock_components, mock_mt5_clients_registry, monkeypatch):
    """
    Caso 3 — configs idênticas reutilizam o mesmo client
    """
    monkeypatch.setattr("nautilus_mt5.factories.MetaTrader5Client", DummyMT5Client)

    config = MetaTrader5DataClientConfig(
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=ExternalRPyCTerminalConfig(
            host="127.0.0.1",
            port=18812,
            keep_alive=True,
            timeout_secs=10.0,
        ),
        client_id=1,
    )

    client_a = get_resolved_mt5_client(config=config, **mock_components)
    client_b = get_resolved_mt5_client(config=config, **mock_components)

    assert client_a is client_b
    assert len(mock_mt5_clients_registry) == 1

def test_internal_config_preserves_parameters(mock_components, mock_mt5_clients_registry, monkeypatch):
    """
    Caso 4 — config interna preserva keep_alive e timeout_secs
    """
    monkeypatch.setattr("nautilus_mt5.factories.MetaTrader5Client", DummyMT5Client)

    expected_keep_alive = True
    expected_timeout = 15.5

    config = MetaTrader5DataClientConfig(
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=ExternalRPyCTerminalConfig(
            host="127.0.0.1",
            port=18812,
            keep_alive=expected_keep_alive,
            timeout_secs=expected_timeout,
        ),
        client_id=1,
    )

    client = get_resolved_mt5_client(config=config, **mock_components)

    rpyc_config = client.kwargs["mt5_config"]["rpyc"]
    assert rpyc_config.keep_alive == expected_keep_alive
    assert rpyc_config.timeout_secs == expected_timeout
