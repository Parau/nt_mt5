import time
import asyncio
from unittest.mock import MagicMock, patch
import pytest

from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_mt5.client.types import MT5TerminalAccessMode
from nautilus_mt5.config import (
    ExternalRPyCTerminalConfig,
    MetaTrader5DataClientConfig,
    MetaTrader5ExecClientConfig,
)
from nautilus_mt5.factories import (
    get_resolved_mt5_client,
    MT5LiveDataClientFactory,
    MT5LiveExecClientFactory,
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

def test_dummy_client_mocking(monkeypatch):
    """
    Verify that the DummyMT5Client can be used to monkeypatch the factory.
    """
    monkeypatch.setattr("nautilus_mt5.factories.MetaTrader5Client", DummyMT5Client)

    loop = asyncio.new_event_loop()
    msgbus = MagicMock(spec=MessageBus)
    cache = MagicMock(spec=Cache)
    clock = MagicMock(spec=LiveClock)

    config = MetaTrader5DataClientConfig(
        client_id=1,
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=ExternalRPyCTerminalConfig(host="127.0.0.1", port=18812)
    )

    client = get_resolved_mt5_client(loop, msgbus, cache, clock, config)
    assert isinstance(client, DummyMT5Client)
    assert len(DummyMT5Client.instances) == 1


def test_external_rpyc_wiring_performance_identical_configs(monkeypatch):
    """
    Case 1: Repeated resolution of identical wiring is fast and reuses cache.
    """
    monkeypatch.setattr("nautilus_mt5.factories.MetaTrader5Client", DummyMT5Client)

    loop = asyncio.new_event_loop()
    msgbus = MagicMock(spec=MessageBus)
    cache = MagicMock(spec=Cache)
    clock = MagicMock(spec=LiveClock)

    config = MetaTrader5DataClientConfig(
        client_id=1,
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=ExternalRPyCTerminalConfig(host="127.0.0.1", port=18812)
    )

    iterations = 100
    start = time.perf_counter()
    for _ in range(iterations):
        client = get_resolved_mt5_client(loop, msgbus, cache, clock, config)
        assert client is not None
    elapsed = time.perf_counter() - start

    # Generous limit: 100 resolutions should be very fast (< 1.0s)
    assert elapsed < 1.0, f"Identical wiring resolution too slow: {elapsed:.4f}s"
    # Should only create 1 client instance
    assert len(DummyMT5Client.instances) == 1


def test_external_rpyc_wiring_performance_distinct_configs(monkeypatch):
    """
    Case 2: Resolution of distinct configurations is fast.
    """
    monkeypatch.setattr("nautilus_mt5.factories.MetaTrader5Client", DummyMT5Client)

    loop = asyncio.new_event_loop()
    msgbus = MagicMock(spec=MessageBus)
    cache = MagicMock(spec=Cache)
    clock = MagicMock(spec=LiveClock)

    iterations = 100
    start = time.perf_counter()
    for index in range(iterations):
        # Varying port to create distinct clients
        config = MetaTrader5DataClientConfig(
            client_id=1,
            terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
            external_rpyc=ExternalRPyCTerminalConfig(host="127.0.0.1", port=18812 + index)
        )
        client = get_resolved_mt5_client(loop, msgbus, cache, clock, config)
        assert client is not None
    elapsed = time.perf_counter() - start

    # Generous limit: 100 distinct resolutions should be fast (< 1.0s)
    assert elapsed < 1.0, f"Distinct wiring resolution too slow: {elapsed:.4f}s"
    # Should create 100 distinct client instances
    assert len(DummyMT5Client.instances) == iterations


def test_external_rpyc_factory_performance(monkeypatch):
    """
    Case 3: Factory resolution is fast with mocked client.
    """
    # Monkeypatch the factory's client resolution to return our DummyMT5Client
    # This avoids Cython type issues with MessageBus and other components when creating real Data/Exec clients
    monkeypatch.setattr("nautilus_mt5.factories.MetaTrader5Client", DummyMT5Client)

    loop = asyncio.new_event_loop()
    msgbus = MagicMock(spec=MessageBus)
    cache = MagicMock(spec=Cache)
    clock = MagicMock(spec=LiveClock)

    data_config = MetaTrader5DataClientConfig(
        client_id=1,
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=ExternalRPyCTerminalConfig(host="127.0.0.1", port=18812)
    )

    exec_config = MetaTrader5ExecClientConfig(
        client_id=1,
        account_id="123456",
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=ExternalRPyCTerminalConfig(host="127.0.0.1", port=18812)
    )

    iterations = 50
    start = time.perf_counter()
    for _ in range(iterations):
        # Patching the creation of clients to focus on the wiring overhead
        # without hitting Cython type checks in real constructors
        with patch("nautilus_mt5.factories.MetaTrader5DataClient") as mock_data_client:
            data_client = MT5LiveDataClientFactory.create(
                loop=loop,
                name="MT5_DATA",
                config=data_config,
                msgbus=msgbus,
                cache=cache,
                clock=clock,
            )
            assert data_client is not None

        with patch("nautilus_mt5.factories.MetaTrader5ExecutionClient") as mock_exec_client:
            exec_client = MT5LiveExecClientFactory.create(
                loop=loop,
                name="MT5_EXEC",
                config=exec_config,
                msgbus=msgbus,
                cache=cache,
                clock=clock,
            )
            assert exec_client is not None
    elapsed = time.perf_counter() - start

    # Generous limit: 50 * 2 factory resolutions should be fast (< 1.0s)
    assert elapsed < 1.0, f"Factory resolution too slow: {elapsed:.4f}s"
    # Both factories should use the same cached DummyMT5Client
    assert len(DummyMT5Client.instances) == 1
