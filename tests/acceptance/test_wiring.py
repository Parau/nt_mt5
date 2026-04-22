import pytest

from nautilus_mt5.config import DockerizedMT5TerminalConfig
from nautilus_mt5.config import MetaTrader5DataClientConfig
from nautilus_mt5.config import MetaTrader5ExecClientConfig
from nautilus_mt5.config import MetaTrader5InstrumentProviderConfig
from nautilus_mt5.factories import MT5LiveDataClientFactory
from nautilus_mt5.factories import MT5LiveExecClientFactory

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
    Ensure client configs use `client_id` and have correct defaults.
    """
    dockerized_gateway = DockerizedMT5TerminalConfig(
        account_number="123", password="abc", server="srv"
    )

    data_config = MetaTrader5DataClientConfig(
        client_id=1,
        dockerized_gateway=dockerized_gateway
    )

    exec_config = MetaTrader5ExecClientConfig(
        client_id=1,
        account_id="123",
        dockerized_gateway=dockerized_gateway
    )

    assert data_config.client_id == 1
    assert data_config.dockerized_gateway is dockerized_gateway

    assert exec_config.client_id == 1
    assert exec_config.account_id == "123"
    assert exec_config.dockerized_gateway is dockerized_gateway

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
