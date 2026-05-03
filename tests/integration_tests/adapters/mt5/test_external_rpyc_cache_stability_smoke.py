import asyncio
from unittest.mock import MagicMock
import pytest

from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_mt5.client.types import MT5TerminalAccessMode
from nautilus_mt5.config import (
    ExternalRPyCTerminalConfig,
    MetaTrader5DataClientConfig,
)
from nautilus_mt5.factories import (
    get_resolved_mt5_client,
    MT5_CLIENTS,
)

class DummyMT5Client:
    instances = []

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        DummyMT5Client.instances.append(self)

    def start(self):
        return None

    def stop(self):
        return None

    @property
    def is_running(self):
        return True

@pytest.fixture(autouse=True)
def clear_mt5_clients():
    """
    Ensure MT5_CLIENTS registry and DummyMT5Client.instances are isolated for each test.
    """
    MT5_CLIENTS.clear()
    DummyMT5Client.instances = []
    yield
    MT5_CLIENTS.clear()
    DummyMT5Client.instances = []

@pytest.fixture
def mock_components():
    return {
        "loop": asyncio.new_event_loop(),
        "msgbus": MagicMock(spec=MessageBus),
        "cache": MagicMock(spec=Cache),
        "clock": MagicMock(spec=LiveClock),
    }

def test_external_rpyc_identical_configs_reuse_client(mock_components, monkeypatch):
    """
    Caso 1 — Config idêntica reutiliza o mesmo client (50 vezes)
    """
    monkeypatch.setattr("nautilus_mt5.factories.MetaTrader5Client", DummyMT5Client)

    config = MetaTrader5DataClientConfig(
        client_id=1,
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=ExternalRPyCTerminalConfig(
            host="127.0.0.1",
            port=18812,
            keep_alive=False,
            timeout_secs=None,
        )
    )

    iterations = 50
    clients = []
    for _ in range(iterations):
        client = get_resolved_mt5_client(config=config, **mock_components)
        clients.append(client)

    # Todos os retornos apontam para o mesmo client fake
    assert all(c is clients[0] for c in clients)
    # Cache contém uma única entrada
    assert len(MT5_CLIENTS) == 1
    # DummyMT5Client foi construído uma vez
    assert len(DummyMT5Client.instances) == 1

def test_external_rpyc_client_id_distinguishes_clients(mock_components, monkeypatch):
    """
    Caso 2 — client_id diferente cria entrada distinta
    """
    monkeypatch.setattr("nautilus_mt5.factories.MetaTrader5Client", DummyMT5Client)

    def create_config(client_id):
        return MetaTrader5DataClientConfig(
            client_id=client_id,
            terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
            external_rpyc=ExternalRPyCTerminalConfig(
                host="127.0.0.1",
                port=18812,
            )
        )

    client1 = get_resolved_mt5_client(config=create_config(1), **mock_components)
    client2 = get_resolved_mt5_client(config=create_config(2), **mock_components)

    assert client1 is not client2
    assert len(MT5_CLIENTS) == 2
    assert len(DummyMT5Client.instances) == 2

def test_external_rpyc_endpoint_distinguishes_clients(mock_components, monkeypatch):
    """
    Caso 3 — host ou port diferente cria entrada distinta
    """
    monkeypatch.setattr("nautilus_mt5.factories.MetaTrader5Client", DummyMT5Client)

    config_host1 = MetaTrader5DataClientConfig(
        client_id=1,
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=ExternalRPyCTerminalConfig(host="127.0.0.1", port=18812)
    )
    config_host2 = MetaTrader5DataClientConfig(
        client_id=1,
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=ExternalRPyCTerminalConfig(host="127.0.0.2", port=18812)
    )
    config_port2 = MetaTrader5DataClientConfig(
        client_id=1,
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=ExternalRPyCTerminalConfig(host="127.0.0.1", port=18813)
    )

    get_resolved_mt5_client(config=config_host1, **mock_components)
    get_resolved_mt5_client(config=config_host2, **mock_components)
    get_resolved_mt5_client(config=config_port2, **mock_components)

    assert len(MT5_CLIENTS) == 3
    assert len(DummyMT5Client.instances) == 3

def test_external_rpyc_keep_alive_distinguishes_clients(mock_components, monkeypatch):
    """
    Caso 4 — keep_alive diferente cria entrada distinta
    """
    monkeypatch.setattr("nautilus_mt5.factories.MetaTrader5Client", DummyMT5Client)

    config_ka_false = MetaTrader5DataClientConfig(
        client_id=1,
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=ExternalRPyCTerminalConfig(host="127.0.0.1", port=18812, keep_alive=False)
    )
    config_ka_true = MetaTrader5DataClientConfig(
        client_id=1,
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=ExternalRPyCTerminalConfig(host="127.0.0.1", port=18812, keep_alive=True)
    )

    get_resolved_mt5_client(config=config_ka_false, **mock_components)
    get_resolved_mt5_client(config=config_ka_true, **mock_components)

    assert len(MT5_CLIENTS) == 2
    assert len(DummyMT5Client.instances) == 2

def test_external_rpyc_timeout_secs_distinguishes_clients(mock_components, monkeypatch):
    """
    Caso 5 — timeout_secs diferente cria entrada distinta
    """
    monkeypatch.setattr("nautilus_mt5.factories.MetaTrader5Client", DummyMT5Client)

    config_t1 = MetaTrader5DataClientConfig(
        client_id=1,
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=ExternalRPyCTerminalConfig(host="127.0.0.1", port=18812, timeout_secs=10.0)
    )
    config_t2 = MetaTrader5DataClientConfig(
        client_id=1,
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=ExternalRPyCTerminalConfig(host="127.0.0.1", port=18812, timeout_secs=20.0)
    )
    config_t_none = MetaTrader5DataClientConfig(
        client_id=1,
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=ExternalRPyCTerminalConfig(host="127.0.0.1", port=18812, timeout_secs=None)
    )

    get_resolved_mt5_client(config=config_t1, **mock_components)
    get_resolved_mt5_client(config=config_t2, **mock_components)
    get_resolved_mt5_client(config=config_t_none, **mock_components)

    assert len(MT5_CLIENTS) == 3
    assert len(DummyMT5Client.instances) == 3

def test_external_rpyc_finite_configs_loop_no_growth(mock_components, monkeypatch):
    """
    Caso 6 — Loop com conjunto finito de configs não cresce indefinidamente
    """
    monkeypatch.setattr("nautilus_mt5.factories.MetaTrader5Client", DummyMT5Client)

    configs = [
        MetaTrader5DataClientConfig(
            client_id=i,
            terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
            external_rpyc=ExternalRPyCTerminalConfig(host="127.0.0.1", port=18812 + i)
        )
        for i in range(5)
    ]

    rounds = 20
    for _ in range(rounds):
        for config in configs:
            get_resolved_mt5_client(config=config, **mock_components)

    # Cache final possui exatamente o número de identidades distintas
    assert len(MT5_CLIENTS) == 5
    # DummyMT5Client foi construído apenas para identidades distintas
    assert len(DummyMT5Client.instances) == 5
