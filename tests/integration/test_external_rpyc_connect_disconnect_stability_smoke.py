import asyncio
import pytest
import rpyc
from typing import List
from unittest.mock import MagicMock

from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock
from nautilus_trader.common.component import MessageBus
from nautilus_trader.model.identifiers import TraderId

from nautilus_mt5.client.types import MT5TerminalAccessMode
from nautilus_mt5.config import ExternalRPyCTerminalConfig, MetaTrader5DataClientConfig
from nautilus_mt5.factories import get_resolved_mt5_client, MT5_CLIENTS
from tests.support.fake_mt5_rpyc_bridge import make_fake_mt5_rpyc_connection, FakeMT5RPyCConnection


@pytest.fixture
def clean_factory_cache():
    """
    Ensure MT5_CLIENTS factory cache is clean before and after each test.
    """
    MT5_CLIENTS.clear()
    yield
    MT5_CLIENTS.clear()


@pytest.mark.asyncio
async def test_external_rpyc_connect_disconnect_stability(monkeypatch, clean_factory_cache):
    """
    Smoke test for stability of repeated connect/disconnect cycles in EXTERNAL_RPYC mode.
    """
    # 1. Setup
    created_connections: List[FakeMT5RPyCConnection] = []

    def mock_rpyc_connect(host, port, config=None, keepalive=False):
        conn = make_fake_mt5_rpyc_connection()
        created_connections.append(conn)
        return conn

    monkeypatch.setattr(rpyc, "connect", mock_rpyc_connect)

    # NautilusTrader components
    loop = asyncio.get_running_loop()
    clock = LiveClock()
    msgbus = MessageBus(TraderId("TEST-1"), clock)
    cache = Cache()

    # Configuration
    external_rpyc_config = ExternalRPyCTerminalConfig(
        host="127.0.0.1",
        port=18812,
        keep_alive=False,
        timeout_secs=30.0
    )

    config = MetaTrader5DataClientConfig(
        client_id=1,
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=external_rpyc_config
    )

    # Capture initial tasks
    current_task = asyncio.current_task()
    initial_tasks = {t for t in asyncio.all_tasks() if not t.done() and t is not current_task}

    # 2. Execution of cycles
    num_cycles = 5
    for i in range(num_cycles):
        # Clear the factory cache in each cycle to force a fresh client
        # as Component.stop() makes it unusable for restarting
        MT5_CLIENTS.clear()

        client = get_resolved_mt5_client(
            loop=loop,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            config=config
        )

        # Wait for connection
        await client.wait_until_ready(timeout=10)
        assert client._is_client_ready.is_set(), f"Client not ready in cycle {i}"

        # Verify initialize was called on the last connection
        conn = created_connections[-1]
        # Poll for initialize call
        success = False
        for _ in range(100):
            if any(c.method == "initialize" for c in conn.root.calls):
                success = True
                break
            await asyncio.sleep(0.01)
        assert success, f"initialize not called in cycle {i}"

        # Disconnect
        client.stop()

        # Wait for client to stop (polling)
        timeout = 5.0
        start_time = loop.time()
        while client.is_running:
            if loop.time() - start_time > timeout:
                pytest.fail(f"Client did not stop within {timeout}s in cycle {i}")
            await asyncio.sleep(0.1)

        # Verify shutdown was called
        # Poll for shutdown call
        success = False
        for _ in range(100):
            if any(c.method == "shutdown" for c in conn.root.calls):
                success = True
                break
            await asyncio.sleep(0.01)
        assert success, f"shutdown not called in cycle {i}"

    # 3. Final Assertions
    # Final Cache should only have 1 entry
    assert len(MT5_CLIENTS) == 1

    # Check for leaking tasks
    await asyncio.sleep(1.0) # Give some more time for tasks to cleanup
    final_tasks = {t for t in asyncio.all_tasks() if not t.done() and t is not current_task}
    new_tasks = final_tasks - initial_tasks

    # Filtering out tasks that might be unrelated to our client
    leaked_adapter_tasks = [t for t in new_tasks if t.get_name().startswith(("_run_", "MetaTrader5Client"))]
    assert not leaked_adapter_tasks, f"Leaked adapter tasks detected: {[t.get_name() for t in leaked_adapter_tasks]}"

    # Verify that we had exactly num_cycles connections created
    assert len(created_connections) == num_cycles
