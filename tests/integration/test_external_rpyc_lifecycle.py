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
from tests.support.fake_mt5_rpyc_bridge import make_fake_mt5_rpyc_connection


@pytest.fixture
def clean_factory_cache():
    """
    Ensure MT5_CLIENTS factory cache is clean before and after each test.
    """
    MT5_CLIENTS.clear()
    yield
    MT5_CLIENTS.clear()


@pytest.mark.asyncio
async def test_external_rpyc_connect_disconnect_lifecycle(monkeypatch, clean_factory_cache):
    """
    Test the connect/disconnect lifecycle of MetaTrader5Client in EXTERNAL_RPYC mode.
    """
    # 1. Setup fake bridge and mock rpyc.connect
    fake_connection = make_fake_mt5_rpyc_connection()
    fake_root = fake_connection.root

    def mock_rpyc_connect(host, port, config=None, keepalive=False):
        return fake_connection

    monkeypatch.setattr(rpyc, "connect", mock_rpyc_connect)

    # 2. Setup NautilusTrader components
    loop = asyncio.get_running_loop()
    clock = LiveClock()
    msgbus = MessageBus(TraderId("TEST-1"), clock)
    cache = Cache()

    # 3. Setup configuration for EXTERNAL_RPYC
    external_rpyc_config = ExternalRPyCTerminalConfig(
        host="127.0.0.1",
        port=18812,
        keep_alive=True,
        timeout_secs=30.0
    )

    config = MetaTrader5DataClientConfig(
        client_id=1,
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=external_rpyc_config
    )

    # 4. Use factory to get and start the client
    # The factory calls client.start() automatically
    client = get_resolved_mt5_client(
        loop=loop,
        msgbus=msgbus,
        cache=cache,
        clock=clock,
        config=config
    )

    try:
        # 5. Wait for connection (lifecycle connect)
        # wait_until_ready calls _is_client_ready.wait()
        # _start_async calls _connect()
        await client.wait_until_ready(timeout=5)

        # 6. Verify connection calls
        # Based on connection.py: _connect -> _initialize_and_connect -> _fetch_terminal_info
        # _initialize_and_connect creates MetaTrader5 which calls rpyc.connect
        # _fetch_terminal_info calls terminal_info()

        calls = fake_root.calls
        method_names = [c.method for c in calls]
        print(f"\nCalls recorded during connect: {method_names}")

        assert "initialize" in method_names
        assert "terminal_info" in method_names

        # 7. Disconnect
        # client.stop() initiates _stop_async
        client.stop()

        # Give some time for stop_async to run
        # _stop_async calls _clear_clients which sets _mt5_client = {'mt5': None, 'ea': None}
        # But wait, looking at client.py, _stop_async also calls shutdown if it's there
        # Let's check MetaTrader5Client._stop_async in client.py

        # Actually MetaTrader5Client._stop_async calls:
        # if self._mt5_client.get('mt5'):
        #     if hasattr(self._mt5_client['mt5'], 'disconnect'):
        #         self._mt5_client['mt5'].disconnect()
        #     elif hasattr(self._mt5_client['mt5'], 'shutdown'):
        #         try:
        #             self._mt5_client['mt5'].shutdown()

        # MetaTrader5.py has shutdown() which calls self.__conn.root.exposed_shutdown()

        # Wait for shutdown to be called on fake root
        # We'll poll for a short period
        for _ in range(20):
            if any(c.method == "shutdown" for c in fake_root.calls):
                break
            await asyncio.sleep(0.1)

        calls = fake_root.calls
        method_names = [c.method for c in calls]
        assert "shutdown" in method_names

        # Verify order: initialize (if it was called) should be before shutdown
        if "initialize" in method_names:
            init_idx = method_names.index("initialize")
            shutdown_idx = method_names.index("shutdown")
            assert init_idx < shutdown_idx

    finally:
        # Ensure client is stopped even if assertions fail
        client.stop()
        # Wait a bit for cleanup
        await asyncio.sleep(0.5)

    # 8. Assertions on used configs
    assert config.managed_terminal is None
    assert config.dockerized_gateway is None
    assert config.terminal_access == MT5TerminalAccessMode.EXTERNAL_RPYC
