import asyncio
import pytest
from unittest.mock import MagicMock
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_mt5.client.types import MT5TerminalAccessMode, TerminalConnectionMode
from nautilus_mt5.config import (
    MetaTrader5DataClientConfig,
    ExternalRPyCTerminalConfig,
    ManagedTerminalConfig,
    ManagedTerminalBackend,
)
from nautilus_mt5.factories import get_resolved_mt5_client, MT5_CLIENTS

@pytest.fixture
def mock_components():
    return {
        "loop": asyncio.get_event_loop(),
        "msgbus": MagicMock(spec=MessageBus),
        "cache": MagicMock(spec=Cache),
        "clock": MagicMock(spec=LiveClock),
    }

def test_get_resolved_mt5_client_external_rpyc(mock_components):
    # Clear cache
    MT5_CLIENTS.clear()

    config = MetaTrader5DataClientConfig(
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=ExternalRPyCTerminalConfig(host="1.2.3.4", port=12345),
        client_id=10,
    )

    # We mock MetaTrader5Client since it tries to connect on start()
    with pytest.MonkeyPatch.context() as mp:
        mock_client_class = MagicMock()
        mp.setattr("nautilus_mt5.factories.MetaTrader5Client", mock_client_class)

        client = get_resolved_mt5_client(
            loop=mock_components["loop"],
            msgbus=mock_components["msgbus"],
            cache=mock_components["cache"],
            clock=mock_components["clock"],
            config=config,
        )

        assert len(MT5_CLIENTS) == 1
        mock_client_class.assert_called_once()
        args, kwargs = mock_client_class.call_args
        assert kwargs["terminal_access"] == MT5TerminalAccessMode.EXTERNAL_RPYC
        assert kwargs["mt5_config"]["rpyc"].host == "1.2.3.4"
        assert kwargs["mt5_config"]["rpyc"].port == 12345

def test_get_resolved_mt5_client_caching(mock_components):
    MT5_CLIENTS.clear()

    config1 = MetaTrader5DataClientConfig(
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=ExternalRPyCTerminalConfig(host="1.2.3.4", port=12345),
        client_id=1,
    )

    config2 = MetaTrader5DataClientConfig(
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=ExternalRPyCTerminalConfig(host="1.2.3.4", port=12345),
        client_id=1,
    )

    with pytest.MonkeyPatch.context() as mp:
        mock_client_class = MagicMock()
        mp.setattr("nautilus_mt5.factories.MetaTrader5Client", mock_client_class)

        client1 = get_resolved_mt5_client(
            mock_components["loop"], mock_components["msgbus"], mock_components["cache"], mock_components["clock"], config1
        )
        client2 = get_resolved_mt5_client(
            mock_components["loop"], mock_components["msgbus"], mock_components["cache"], mock_components["clock"], config2
        )

        assert client1 is client2
        assert len(MT5_CLIENTS) == 1
        assert mock_client_class.call_count == 1

def test_get_resolved_mt5_client_managed_terminal_not_implemented(mock_components):
    config = MetaTrader5DataClientConfig(
        terminal_access=MT5TerminalAccessMode.MANAGED_TERMINAL,
        managed_terminal=ManagedTerminalConfig(backend=ManagedTerminalBackend.LOCAL_PROCESS),
    )

    with pytest.raises(RuntimeError, match="MANAGED_TERMINAL access mode was recognized, but the backend .* is not yet implemented in this phase"):
        get_resolved_mt5_client(
            mock_components["loop"], mock_components["msgbus"], mock_components["cache"], mock_components["clock"], config
        )

def test_get_resolved_mt5_client_missing_config_raises_error(mock_components):
    config = MetaTrader5DataClientConfig(
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=None,
    )

    with pytest.raises(ValueError, match="external_rpyc config is required"):
        get_resolved_mt5_client(
            mock_components["loop"], mock_components["msgbus"], mock_components["cache"], mock_components["clock"], config
        )
