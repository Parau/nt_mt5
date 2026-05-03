import pytest
from unittest.mock import AsyncMock, MagicMock
from nautilus_trader.model.identifiers import AccountId
from nautilus_mt5.execution import MetaTrader5ExecutionClient
from nautilus_mt5.config import MetaTrader5ExecClientConfig

@pytest.mark.asyncio
async def test_account_bootstrap_injection():
    config = MetaTrader5ExecClientConfig(account_id="12345")

    client_mock = MagicMock()
    # Mocking MT5 account_info to have the needed properties
    mock_account_info = MagicMock(
        login=12345,
        balance=1000.0,
        currency="USD",
        margin_initial=100.0,
        margin_maintenance=50.0,
        equity=900.0,
        margin_free=800.0
    )
    client_mock.get_account_info = AsyncMock(return_value=mock_account_info)
    client_mock.wait_until_ready = AsyncMock()
    client_mock._connect = AsyncMock()

    provider_mock = MagicMock()
    provider_mock.initialize = AsyncMock()

    exec_client = MetaTrader5ExecutionClient.__new__(MetaTrader5ExecutionClient)

    # Bypass standard init
    exec_client._client = client_mock
    exec_client._config = config
    exec_client._instrument_provider = provider_mock

    # We want to track calls to _on_account_summary to see if FullAvailableFunds is injected
    exec_client._on_account_summary = MagicMock()

    from nautilus_trader.model.identifiers import ClientId
    type(exec_client).id = property(lambda self: ClientId("mock_client"))
    type(exec_client).config = property(lambda self: self._config)
    type(exec_client).account_id = property(lambda self: AccountId("MT5-12345"))
    type(exec_client).instrument_provider = property(lambda self: self._instrument_provider)
    type(exec_client)._log = property(lambda self: MagicMock())
    type(exec_client)._set_connected = MagicMock()

    await MetaTrader5ExecutionClient._connect(exec_client)

    # Verify that the 4 necessary fields were injected using _on_account_summary
    calls = exec_client._on_account_summary.call_args_list
    tags_injected = [call[0][0] for call in calls]

    assert "FullInitMarginReq" in tags_injected
    assert "FullMaintMarginReq" in tags_injected
    assert "NetLiquidation" in tags_injected
    assert "FullAvailableFunds" in tags_injected

    # Check the specific values injected based on mock_account_info
    exec_client._on_account_summary.assert_any_call("FullInitMarginReq", "100.0", "USD")
    exec_client._on_account_summary.assert_any_call("FullMaintMarginReq", "50.0", "USD")
    exec_client._on_account_summary.assert_any_call("NetLiquidation", "900.0", "USD")
    exec_client._on_account_summary.assert_any_call("FullAvailableFunds", "800.0", "USD")

@pytest.mark.asyncio
async def test_generate_account_state_trigger():
    exec_client = MetaTrader5ExecutionClient.__new__(MetaTrader5ExecutionClient)
    exec_client._account_summary_tags = {
        "NetLiquidation",
        "FullAvailableFunds",
        "FullInitMarginReq",
        "FullMaintMarginReq",
    }
    exec_client._account_summary = {}
    type(exec_client)._log = property(lambda self: MagicMock())

    mock_clock = MagicMock()
    mock_clock.timestamp_ns = MagicMock(return_value=123)
    type(exec_client)._clock = property(lambda self: mock_clock)

    type(exec_client)._cache = property(lambda self: MagicMock())

    mock_account_id = MagicMock()
    mock_account_id.get_id = MagicMock(return_value="MT5-12345")
    type(exec_client).account_id = property(lambda self: mock_account_id)
    exec_client._account_summary_loaded = MagicMock()
    exec_client.generate_account_state = MagicMock()

    # Call _on_account_summary sequentially
    exec_client._on_account_summary("FullInitMarginReq", "100.0", "USD")
    assert not exec_client.generate_account_state.called

    exec_client._on_account_summary("FullMaintMarginReq", "50.0", "USD")
    assert not exec_client.generate_account_state.called

    exec_client._on_account_summary("NetLiquidation", "900.0", "USD")
    assert not exec_client.generate_account_state.called

    exec_client._on_account_summary("FullAvailableFunds", "800.0", "USD")
    # All required tags are now present, generate_account_state should be triggered
    assert exec_client.generate_account_state.called


def _make_account_summary_client(total: float, locked: float):
    """Helper: returns an exec_client instance with _on_account_summary ready to call."""
    from nautilus_trader.model.objects import AccountBalance, MarginBalance, Money, Currency

    exec_client = MetaTrader5ExecutionClient.__new__(MetaTrader5ExecutionClient)
    exec_client._account_summary_tags = {
        "NetLiquidation",
        "FullAvailableFunds",
        "FullInitMarginReq",
        "FullMaintMarginReq",
    }
    exec_client._account_summary = {}
    type(exec_client)._log = property(lambda self: MagicMock())

    mock_clock = MagicMock()
    mock_clock.timestamp_ns = MagicMock(return_value=0)
    type(exec_client)._clock = property(lambda self: mock_clock)
    type(exec_client)._cache = property(lambda self: MagicMock())

    mock_account_id = MagicMock()
    mock_account_id.get_id = MagicMock(return_value="MT5-TEST")
    type(exec_client).account_id = property(lambda self: mock_account_id)
    exec_client._account_summary_loaded = MagicMock()

    captured = {}

    def fake_generate_account_state(balances, margins, reported, ts_event):
        captured["balance"] = balances[0]

    exec_client.generate_account_state = fake_generate_account_state

    exec_client._on_account_summary("FullInitMarginReq", "0.0", "USD")
    exec_client._on_account_summary("FullMaintMarginReq", str(locked), "USD")
    exec_client._on_account_summary("NetLiquidation", str(total), "USD")
    exec_client._on_account_summary("FullAvailableFunds", "0.0", "USD")

    return captured["balance"]


def test_account_balance_normal_case():
    """When total > locked, free = total - locked (positive, exact)."""
    balance = _make_account_summary_client(total=1000.0, locked=200.0)
    assert float(balance.total) == 1000.0
    assert float(balance.locked) == 200.0
    assert float(balance.free) == 800.0


def test_account_balance_locked_exceeds_total_clamps_to_zero():
    """
    When locked > total (e.g. margin call scenario), AccountBalance enforces
    total - locked == free, so free cannot be negative.
    The adapter must clamp locked to total so free = 0 is valid.
    Before the fix, a hardcoded 400000 was inserted, masking the real failure.
    After the fix, locked is clamped and free = total - locked = 0.
    """
    balance = _make_account_summary_client(total=10.0, locked=50.0)
    assert float(balance.total) == 10.0
    # locked is clamped to total (10) so the AccountBalance invariant holds
    assert float(balance.locked) == 10.0
    assert float(balance.free) == 0.0


def test_account_balance_exactly_equal_total_and_locked():
    """When total == locked, free = 0.0 (no available funds)."""
    balance = _make_account_summary_client(total=500.0, locked=500.0)
    assert float(balance.free) == 0.0
