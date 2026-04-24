import asyncio
import pytest
import rpyc
from unittest.mock import MagicMock

from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock
from nautilus_trader.common.component import MessageBus
from nautilus_trader.model.identifiers import TraderId

from nautilus_mt5.client.client import MetaTrader5Client
from nautilus_mt5.client.types import MT5TerminalAccessMode
from nautilus_mt5.config import (
    ExternalRPyCTerminalConfig,
    MetaTrader5DataClientConfig,
    MetaTrader5InstrumentProviderConfig
)
from nautilus_mt5.factories import get_resolved_mt5_client, MT5_CLIENTS
from tests.support.fake_mt5_rpyc_bridge import FakeMT5RPyCRoot, FakeMT5RPyCConnection

class FakeRootWithoutSymbolInfoTick(FakeMT5RPyCRoot):
    """
    Fake RPyC root that deliberately lacks the exposed_symbol_info_tick method.
    """
    def __getattribute__(self, name):
        if name == "exposed_symbol_info_tick":
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
        return super().__getattribute__(name)

@pytest.fixture
def clean_factory_cache():
    """
    Ensure MT5_CLIENTS factory cache is clean before and after each test.
    """
    MT5_CLIENTS.clear()
    yield
    MT5_CLIENTS.clear()

@pytest.mark.asyncio
async def test_external_rpyc_fails_on_missing_method(monkeypatch, clean_factory_cache):
    """
    Test that the adapter fails with a controlled RuntimeError when a remote method is missing.
    """
    # 1. Setup fake bridge with missing method
    fake_connection = FakeMT5RPyCConnection()
    fake_connection.root = FakeRootWithoutSymbolInfoTick()

    def mock_rpyc_connect(host, port, config=None, keepalive=False):
        return fake_connection

    monkeypatch.setattr(rpyc, "connect", mock_rpyc_connect)

    # Mock component properties to avoid Cython setter issues
    monkeypatch.setattr(MetaTrader5Client, "_cache", MagicMock(), raising=False)
    monkeypatch.setattr(MetaTrader5Client, "_clock", MagicMock(), raising=False)
    monkeypatch.setattr(MetaTrader5Client, "_msgbus", MagicMock(), raising=False)

    # 2. Setup NautilusTrader components
    loop = asyncio.get_running_loop()
    clock = LiveClock()
    msgbus = MessageBus(TraderId("TEST-1"), clock)
    cache = Cache()

    # 3. Setup configuration for EXTERNAL_RPYC
    external_rpyc_config = ExternalRPyCTerminalConfig(
        host="127.0.0.1",
        port=18812
    )

    config = MetaTrader5DataClientConfig(
        client_id=1,
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=external_rpyc_config,
        instrument_provider=MetaTrader5InstrumentProviderConfig()
    )

    # 4. Get the client
    mt5_client = get_resolved_mt5_client(
        loop=loop,
        msgbus=msgbus,
        cache=cache,
        clock=clock,
        config=config
    )

    try:
        await mt5_client.wait_until_ready(timeout=5)

        # 5. Exercise the missing capability
        # We expect a RuntimeError with a clear message
        with pytest.raises(RuntimeError) as excinfo:
            mt5_client._mt5_client['mt5'].symbol_info_tick("EURUSD")

        # 6. Validate error message
        error_msg = str(excinfo.value).lower()
        assert "missing rpc method" in error_msg or "does not expose required method" in error_msg
        assert "symbol_info_tick" in error_msg
        assert "external_rpyc" in error_msg or "gateway" in error_msg

        # 7. Validate it's not a raw AttributeError or NotImplementedError
        assert excinfo.type is RuntimeError
        assert excinfo.type is not AttributeError
        assert excinfo.type is not NotImplementedError

    finally:
        mt5_client.stop()
        await asyncio.sleep(0.1)
