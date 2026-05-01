import asyncio
import pytest
import rpyc
from unittest.mock import MagicMock

from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock
from nautilus_trader.common.component import MessageBus
from nautilus_trader.model.identifiers import TraderId
from nautilus_trader.model.identifiers import AccountId

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


@pytest.fixture
def nautilus_components(event_loop):
    loop = event_loop
    clock = LiveClock()
    msgbus = MessageBus(TraderId("TEST-1"), clock)
    cache = Cache()
    return loop, clock, msgbus, cache


def get_exec_config(account_id: str):
    external_rpyc_config = ExternalRPyCTerminalConfig(
        host="127.0.0.1",
        port=18812,
        keep_alive=True,
        timeout_secs=30.0
    )

    return MetaTrader5ExecClientConfig(
        client_id=1,
        account_id=account_id,
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=external_rpyc_config
    )


@pytest.mark.asyncio
async def test_execution_account_validation_success(monkeypatch, clean_factory_cache, nautilus_components):
    """
    Test that execution client bootstrap succeeds when accounts match.
    """
    fake_connection = make_fake_mt5_rpyc_connection()
    # Default fake bridge returns login: 123456
    monkeypatch.setattr(rpyc, "connect", lambda *a, **k: fake_connection)

    loop, clock, msgbus, cache = nautilus_components
    config = get_exec_config("123456")

    exec_client = MT5LiveExecClientFactory.create(
        loop=loop,
        name="MT5",
        config=config,
        msgbus=msgbus,
        cache=cache,
        clock=clock,
    )

    # Call _connect directly to ensure it finishes in this test context
    await exec_client._connect()

    assert exec_client._client._is_client_ready.is_set()
    # verify exposed_account_info was called
    assert any(call.method == "account_info" for call in fake_connection.root.calls)


@pytest.mark.asyncio
async def test_execution_account_validation_mismatch(monkeypatch, clean_factory_cache, nautilus_components):
    """
    Test that execution client bootstrap fails when accounts mismatch.
    """
    fake_connection = make_fake_mt5_rpyc_connection()
    # Default fake bridge returns login: 123456
    monkeypatch.setattr(rpyc, "connect", lambda *a, **k: fake_connection)

    loop, clock, msgbus, cache = nautilus_components
    config = get_exec_config("999999") # Expected 999999, but gateway has 123456

    exec_client = MT5LiveExecClientFactory.create(
        loop=loop,
        name="MT5",
        config=config,
        msgbus=msgbus,
        cache=cache,
        clock=clock,
    )

    # Call _connect and expect RuntimeError
    with pytest.raises(RuntimeError, match="external_rpyc execution account mismatch"):
        await exec_client._connect()

    # Message should contain expected and actual
    with pytest.raises(RuntimeError) as excinfo:
        await exec_client._connect()
    assert "expected account 999999" in str(excinfo.value)
    assert "actual account 123456" in str(excinfo.value)


@pytest.mark.asyncio
async def test_execution_account_validation_missing_login(monkeypatch, clean_factory_cache, nautilus_components):
    """
    Test that execution client bootstrap fails when account_info is missing login.
    """
    fake_connection = make_fake_mt5_rpyc_connection()
    fake_root = fake_connection.root

    # Return account_info without 'login'
    monkeypatch.setattr(fake_root, "exposed_account_info", lambda *a, **k: {
        "server": "FakeServer",
        "balance": 100000.0,
        "currency": "USD",
    })

    monkeypatch.setattr(rpyc, "connect", lambda *a, **k: fake_connection)

    loop, clock, msgbus, cache = nautilus_components
    config = get_exec_config("123456")

    exec_client = MT5LiveExecClientFactory.create(
        loop=loop,
        name="MT5",
        config=config,
        msgbus=msgbus,
        cache=cache,
        clock=clock,
    )

    with pytest.raises(RuntimeError, match="external_rpyc account_info invalid or login missing"):
        await exec_client._connect()
