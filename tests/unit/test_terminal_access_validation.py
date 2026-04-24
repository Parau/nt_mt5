import asyncio
import pytest
from unittest.mock import MagicMock
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_mt5.client.types import (
    MT5TerminalAccessMode,
    ManagedTerminalBackend,
)
from nautilus_mt5.config import (
    MetaTrader5DataClientConfig,
    MetaTrader5ExecClientConfig,
    ExternalRPyCTerminalConfig,
    ManagedTerminalConfig,
    DockerizedMT5TerminalConfig,
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

@pytest.mark.parametrize("config_cls", [
    MetaTrader5DataClientConfig,
    MetaTrader5ExecClientConfig,
])
class TestTerminalAccessValidation:

    def test_external_rpyc_missing_config_raises_error(self, config_cls, mock_components):
        # 1. EXTERNAL_RPYC sem external_rpyc
        config = config_cls(
            terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
            external_rpyc=None,
        )
        with pytest.raises(ValueError, match="external_rpyc.*required|external_rpyc.*obrig"):
            get_resolved_mt5_client(**mock_components, config=config)

    def test_external_rpyc_with_managed_config_raises_error(self, config_cls, mock_components):
        # 2. EXTERNAL_RPYC com managed_terminal
        config = config_cls(
            terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
            external_rpyc=ExternalRPyCTerminalConfig(host="127.0.0.1", port=18812),
            managed_terminal=ManagedTerminalConfig(backend=ManagedTerminalBackend.DOCKERIZED),
        )
        with pytest.raises(ValueError, match="managed_terminal.*None|managed_terminal.*ausente"):
            get_resolved_mt5_client(**mock_components, config=config)

    def test_managed_terminal_missing_config_raises_error(self, config_cls, mock_components):
        # 3. MANAGED_TERMINAL sem managed_terminal
        config = config_cls(
            terminal_access=MT5TerminalAccessMode.MANAGED_TERMINAL,
            managed_terminal=None,
        )
        with pytest.raises(ValueError, match="managed_terminal.*required|managed_terminal.*obrig"):
            get_resolved_mt5_client(**mock_components, config=config)

    def test_managed_terminal_with_external_config_raises_error(self, config_cls, mock_components):
        # 4. MANAGED_TERMINAL com external_rpyc
        config = config_cls(
            terminal_access=MT5TerminalAccessMode.MANAGED_TERMINAL,
            external_rpyc=ExternalRPyCTerminalConfig(host="127.0.0.1", port=18812),
            managed_terminal=ManagedTerminalConfig(backend=ManagedTerminalBackend.DOCKERIZED),
        )
        with pytest.raises(ValueError, match="external_rpyc.*None|external_rpyc.*ausente"):
            get_resolved_mt5_client(**mock_components, config=config)

    def test_managed_terminal_with_legacy_gateway_fails(self, config_cls, mock_components):
        # 5. MANAGED_TERMINAL com dockerized_gateway top-level legado
        config = config_cls(
            terminal_access=MT5TerminalAccessMode.MANAGED_TERMINAL,
            managed_terminal=ManagedTerminalConfig(backend=ManagedTerminalBackend.DOCKERIZED),
            dockerized_gateway=DockerizedMT5TerminalConfig(),
        )
        with pytest.raises(ValueError, match="dockerized_gateway.*legacy|dockerized_gateway.*legado"):
            get_resolved_mt5_client(**mock_components, config=config)

    def test_managed_terminal_not_implemented_raises_runtime_error(self, config_cls, mock_components):
        # 6. MANAGED_TERMINAL válido estruturalmente, mas backend ainda não implementado
        config = config_cls(
            terminal_access=MT5TerminalAccessMode.MANAGED_TERMINAL,
            managed_terminal=ManagedTerminalConfig(backend=ManagedTerminalBackend.DOCKERIZED),
        )
        with pytest.raises(RuntimeError, match="MANAGED_TERMINAL.*recognized|MANAGED_TERMINAL.*reconhecido"):
            get_resolved_mt5_client(**mock_components, config=config)

    def test_external_rpyc_valid_structurally(self, config_cls, mock_components):
        # 7. EXTERNAL_RPYC válido estruturalmente
        config = config_cls(
            terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
            external_rpyc=ExternalRPyCTerminalConfig(host="127.0.0.1", port=18812),
        )

        # We mock MetaTrader5Client since it tries to connect on start()
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("nautilus_mt5.factories.MetaTrader5Client", MagicMock())
            # Should not raise any validation error
            get_resolved_mt5_client(**mock_components, config=config)

    def test_external_rpyc_with_legacy_rpyc_config_fails(self, config_cls, mock_components):
        from nautilus_mt5.metatrader5 import RpycConnectionConfig
        config = config_cls(
            terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
            external_rpyc=ExternalRPyCTerminalConfig(host="127.0.0.1", port=18812),
            rpyc_config=RpycConnectionConfig(host="127.0.0.1", port=18812),
        )
        with pytest.raises(ValueError, match="rpyc_config.*legacy|rpyc_config.*legado"):
            get_resolved_mt5_client(**mock_components, config=config)

    def test_managed_terminal_with_legacy_rpyc_config_fails(self, config_cls, mock_components):
        from nautilus_mt5.metatrader5 import RpycConnectionConfig
        config = config_cls(
            terminal_access=MT5TerminalAccessMode.MANAGED_TERMINAL,
            managed_terminal=ManagedTerminalConfig(backend=ManagedTerminalBackend.DOCKERIZED),
            rpyc_config=RpycConnectionConfig(host="127.0.0.1", port=18812),
        )
        with pytest.raises(ValueError, match="rpyc_config.*legacy|rpyc_config.*legado"):
            get_resolved_mt5_client(**mock_components, config=config)

    def test_external_rpyc_with_legacy_gateway_fails(self, config_cls, mock_components):
        config = config_cls(
            terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
            external_rpyc=ExternalRPyCTerminalConfig(host="127.0.0.1", port=18812),
            dockerized_gateway=DockerizedMT5TerminalConfig(),
        )
        with pytest.raises(ValueError, match="dockerized_gateway.*legacy|dockerized_gateway.*legado"):
            get_resolved_mt5_client(**mock_components, config=config)
