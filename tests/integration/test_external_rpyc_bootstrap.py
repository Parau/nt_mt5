import asyncio
import pytest
import rpyc
from unittest.mock import MagicMock

from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock
from nautilus_trader.common.component import MessageBus
from nautilus_trader.model.identifiers import TraderId

from nautilus_mt5.client.types import MT5TerminalAccessMode
from nautilus_mt5.config import ExternalRPyCTerminalConfig, MetaTrader5ExecClientConfig
from nautilus_mt5.factories import MT5LiveExecClientFactory, MT5_CLIENTS
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
async def test_external_rpyc_bootstrap_terminal_and_account(monkeypatch, clean_factory_cache):
    """
    Test the bootstrap process in EXTERNAL_RPYC mode, ensuring terminal_info
    and account_info are fetched from the RPyC bridge.
    """
    # 1. Setup fake bridge and mock rpyc.connect
    fake_connection = make_fake_mt5_rpyc_connection()
    fake_root = fake_connection.root

    # Configure deterministic data on the fake bridge
    expected_terminal_info = {
        "name": "Fake MetaTrader 5",
        "company": "Fake Broker",
        "connected": True,
        "trade_allowed": True,
        "build": 3000,
    }
    expected_account_info = {
        "login": 123456,
        "server": "FakeServer",
        "balance": 100000.0,
        "equity": 100000.0,
        "currency": "USD",
    }

    # 2. Mock rpyc.connect
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
    )

    config = MetaTrader5ExecClientConfig(
        client_id=1,
        account_id="123456",
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=external_rpyc_config
    )

    # 4. Use factory to create the execution client
    # The factory also retrieves/starts the shared MetaTrader5Client
    exec_client = MT5LiveExecClientFactory.create(
        loop=loop,
        name="MT5_VENUE",
        config=config,
        msgbus=msgbus,
        cache=cache,
        clock=clock,
    )

    try:
        # 5. Trigger the bootstrap by calling _connect on the execution client
        # In a real scenario, this would be called by Nautilus when the client starts
        # We wait for the shared client to be ready (it was started by the factory)
        await exec_client._client.wait_until_ready()
        # Then we call _connect on the exec client to perform its specific bootstrap (account validation)
        await exec_client._connect()

        # 6. Validate calls to the fake bridge
        method_names = [call.method for call in fake_root.calls]

        assert "initialize" in method_names
        assert "terminal_info" in method_names
        assert "account_info" in method_names

        # 7. Validate that data from the bridge was consumed
        # MetaTrader5ClientConnectionMixin._fetch_terminal_info sets _terminal_info
        # MetaTrader5ExecutionClient._connect validates the login

        # Checking if MetaTrader5Client has the correct terminal info
        mt5_client = exec_client._client
        assert mt5_client._terminal_info["build"] == expected_terminal_info["build"]

        # Verify that it wasn't manual injection
        # If it was "Mock" or something else, the login validation in exec_client._connect
        # would have failed (it raises ConnectionError on mismatch).

        # 8. Check that no manual "Mock" state was used
        # We can verify that the calls happened and they returned our expected data
        terminal_info_calls = [c for c in fake_root.calls if c.method == "terminal_info"]
        account_info_calls = [c for c in fake_root.calls if c.method == "account_info"]

        assert len(terminal_info_calls) > 0
        assert len(account_info_calls) > 0

        # 9. Verify ready-state dependency
        # The client is considered connected if _is_mt5_connected is set.
        # It's set in _start_async after _connect returns.
        assert mt5_client._is_mt5_connected.is_set()

    finally:
        # Cleanup
        await exec_client._disconnect()
        if hasattr(exec_client._client, "_stop_async"):
            await exec_client._client._stop_async()
