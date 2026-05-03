import pytest

from nautilus_mt5.client.types import MT5TerminalAccessMode, ManagedTerminalBackend
from nautilus_mt5.config import (
    DockerizedMT5TerminalConfig,
    ManagedTerminalConfig,
    MetaTrader5DataClientConfig,
    MetaTrader5ExecClientConfig,
    MetaTrader5InstrumentProviderConfig,
)
from nautilus_mt5.factories import MT5LiveDataClientFactory, MT5LiveExecClientFactory

def test_dockerized_gateway_config():
    """
    Ensure DockerizedMT5TerminalConfig doesn't have broken attributes like read_only_api.
    """
    config = DockerizedMT5TerminalConfig(
        account_number="123456",
        password="password123",
        server="MyBroker-Server"
    )

    assert config.account_number == "123456"
    assert config.password == "password123"
    assert config.server == "MyBroker-Server"
    assert config.timeout == 300

    # Asserting that repr does not throw an AttributeError
    repr_str = repr(config)
    assert "timeout=300" in repr_str
    assert "read_only_api" not in repr_str

def test_client_configs():
    """
    Ensure client configs use `client_id` and have correct nested managed_terminal defaults.
    """
    dockerized_gateway = DockerizedMT5TerminalConfig(
        account_number="123", password="abc", server="srv"
    )
    managed_terminal = ManagedTerminalConfig(
        backend=ManagedTerminalBackend.DOCKERIZED,
        dockerized=dockerized_gateway,
    )

    data_config = MetaTrader5DataClientConfig(
        client_id=1,
        terminal_access=MT5TerminalAccessMode.MANAGED_TERMINAL,
        managed_terminal=managed_terminal,
    )

    exec_config = MetaTrader5ExecClientConfig(
        client_id=1,
        account_id="123",
        terminal_access=MT5TerminalAccessMode.MANAGED_TERMINAL,
        managed_terminal=managed_terminal,
    )

    assert data_config.client_id == 1
    assert data_config.terminal_access == MT5TerminalAccessMode.MANAGED_TERMINAL
    assert data_config.managed_terminal.dockerized is dockerized_gateway

    assert exec_config.client_id == 1
    assert exec_config.account_id == "123"
    assert exec_config.terminal_access == MT5TerminalAccessMode.MANAGED_TERMINAL
    assert exec_config.managed_terminal.dockerized is dockerized_gateway

    # Should not have `mt5_client_id`
    with pytest.raises(AttributeError):
        _ = data_config.mt5_client_id

    with pytest.raises(AttributeError):
        _ = exec_config.mt5_client_id

def test_factories_importable():
    """
    Verify factories are importable and we can check their type or minimal behavior.
    """
    assert MT5LiveDataClientFactory is not None
    assert MT5LiveExecClientFactory is not None
