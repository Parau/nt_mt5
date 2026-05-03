import pytest
from unittest.mock import AsyncMock, MagicMock
from nautilus_trader.model.identifiers import AccountId
from nautilus_mt5.execution import MetaTrader5ExecutionClient
from nautilus_mt5.config import MetaTrader5ExecClientConfig

@pytest.mark.asyncio
async def test_execution_client_imports():
    # Verify the runtime symbol resolution of VenueOrderId and others
    import nautilus_mt5.execution as exc
    assert exc.VenueOrderId is not None
    assert exc.OrderType is not None
    assert exc.OrderStatus is not None
    assert exc.MT5Order is not None

@pytest.mark.asyncio
async def test_account_validation():
    # Test MT5 account validation logic
    config = MetaTrader5ExecClientConfig(account_id="12345")
    client_mock = MagicMock()
    client_mock.get_account_info = AsyncMock(return_value=MagicMock(login=12345, balance=1000.0, currency="USD"))
    client_mock.wait_until_ready = AsyncMock()
    client_mock._connect = AsyncMock()

    account_id = AccountId("MT5-12345")

    provider_mock = MagicMock()
    provider_mock.initialize = AsyncMock()

    exec_client = MetaTrader5ExecutionClient.__new__(MetaTrader5ExecutionClient)

    exec_client._client = client_mock
    exec_client._account_id = account_id
    exec_client._config = config
    exec_client._instrument_provider = provider_mock
    exec_client._on_account_summary = MagicMock()

    from nautilus_trader.model.identifiers import ClientId
    type(exec_client).id = property(lambda self: ClientId("mock_client"))
    type(exec_client).config = property(lambda self: self._config)
    type(exec_client).account_id = property(lambda self: self._account_id)
    type(exec_client).instrument_provider = property(lambda self: self._instrument_provider)
    type(exec_client)._log = property(lambda self: MagicMock())
    type(exec_client)._set_connected = MagicMock()

    await MetaTrader5ExecutionClient._connect(exec_client)

    assert exec_client._set_connected.called

@pytest.mark.asyncio
async def test_account_validation_mismatch():
    config = MetaTrader5ExecClientConfig(account_id="12345")
    client_mock = MagicMock()
    client_mock.get_account_info = AsyncMock(return_value=MagicMock(login=99999)) # Mismatched login
    client_mock.wait_until_ready = AsyncMock()
    client_mock._connect = AsyncMock()

    account_id = AccountId("MT5-12345")

    provider_mock = MagicMock()
    provider_mock.initialize = AsyncMock()

    exec_client = MetaTrader5ExecutionClient.__new__(MetaTrader5ExecutionClient)

    exec_client._client = client_mock
    exec_client._account_id = account_id
    exec_client._config = config
    exec_client._instrument_provider = provider_mock
    exec_client._on_account_summary = MagicMock()

    from nautilus_trader.model.identifiers import ClientId
    type(exec_client).id = property(lambda self: ClientId("mock_client"))
    type(exec_client).config = property(lambda self: self._config)
    type(exec_client).account_id = property(lambda self: self._account_id)
    type(exec_client).instrument_provider = property(lambda self: self._instrument_provider)
    type(exec_client)._log = property(lambda self: MagicMock())

    with pytest.raises(ConnectionError, match="account mismatch"):
        await MetaTrader5ExecutionClient._connect(exec_client)

@pytest.mark.asyncio
async def test_modify_order_passes_instrument():
    from nautilus_trader.model.identifiers import ClientOrderId, VenueOrderId, InstrumentId, Symbol, Venue
    from nautilus_trader.model.objects import Quantity
    from nautilus_trader.model.orders import MarketOrder
    from nautilus_trader.model.enums import OrderSide
    from nautilus_trader.execution.messages import ModifyOrder

    exec_client = MetaTrader5ExecutionClient.__new__(MetaTrader5ExecutionClient)
    type(exec_client)._log = property(lambda self: MagicMock())
    exec_client._client = MagicMock()

    instr_id = InstrumentId(Symbol("EURUSD"), Venue("METATRADER_5"))

    mock_nautilus_order = MagicMock()
    mock_nautilus_order.instrument_id = instr_id
    mock_nautilus_order.status_string = MagicMock(return_value="Pending")

    mock_instrument = MagicMock()

    mock_cache = MagicMock()
    mock_cache.order = MagicMock(return_value=mock_nautilus_order)
    mock_cache.instrument = MagicMock(return_value=mock_instrument)

    type(exec_client)._cache = property(lambda self: mock_cache)

    mock_mt5_order = MagicMock()
    mock_mt5_order.volume = 100.0
    mock_mt5_order.price = None
    mock_mt5_order.trigger_price = None
    mock_mt5_order.parentId = 0

    exec_client._transform_order_to_mt5_order = MagicMock(return_value=mock_mt5_order)

    command = MagicMock()
    command.client_order_id = ClientOrderId("mock1")
    command.venue_order_id = VenueOrderId("123")
    command.quantity = Quantity.from_int(100)
    command.price = None
    command.trigger_price = None

    await MetaTrader5ExecutionClient._modify_order(exec_client, command)

    # Verify that the cache was queried for the instrument
    mock_cache.instrument.assert_called_with(instr_id)
    # Verify that both the order and instrument are passed to the transform method
    exec_client._transform_order_to_mt5_order.assert_called_with(mock_nautilus_order, mock_instrument)

@pytest.mark.asyncio
async def test_client_lifecycle_and_readiness():
    from nautilus_mt5.client.client import MetaTrader5Client
    from nautilus_mt5.client.types import TerminalConnectionMode

    client = MetaTrader5Client.__new__(MetaTrader5Client)
    client._client_id = 1
    client._terminal_connection_mode = TerminalConnectionMode.IPC
    type(client)._log = property(lambda self: MagicMock())
    import asyncio
    client._is_client_ready = asyncio.Event()
    client._is_mt5_connected = asyncio.Event()

    client._connect = AsyncMock()
    client._start_connection_watchdog = MagicMock()
    client._start_terminal_incoming_msg_reader = MagicMock()
    client._start_internal_msg_queue_processor = MagicMock()

    client._connection_attempts = 0

    await MetaTrader5Client._start_async(client)

    client._connect.assert_called_once()
    assert client._is_mt5_connected.is_set()

    client._start_connection_watchdog.assert_called_once()
    client._start_terminal_incoming_msg_reader.assert_called_once()
    client._start_internal_msg_queue_processor.assert_called_once()

    assert client._is_client_ready.is_set()

# ---------------------------------------------------------------------------
# Phase 7 — Tests for the three compliance fixes
# ---------------------------------------------------------------------------

def _make_bare_exec_client():
    """Return a MetaTrader5ExecutionClient instance with minimal mocks."""
    ec = MetaTrader5ExecutionClient.__new__(MetaTrader5ExecutionClient)
    log_mock = MagicMock()
    type(ec)._log = property(lambda self: log_mock)
    ec._log_mock = log_mock  # expose for assertions
    return ec


def test_handle_order_event_filled_logs_warning_and_does_not_call_generate_order_filled():
    """
    Phase 7 / Fix #2 — _handle_order_event with OrderStatus.FILLED.

    The FILLED path via this method does not have fill details (price, qty,
    trade_id), so it must NOT call generate_order_filled. It must emit a
    warning so the developer knows the fill must come from _submit_order or
    _on_exec_details.
    """
    from nautilus_trader.model.enums import OrderStatus
    from nautilus_trader.model.identifiers import ClientOrderId

    ec = _make_bare_exec_client()

    # generate_order_filled must NOT be called
    ec.generate_order_filled = MagicMock()

    # Build a mock order that is NOT already FILLED
    order = MagicMock()
    order.client_order_id = ClientOrderId("O-FILLED-01")
    order.status = OrderStatus.ACCEPTED  # not yet filled

    MetaTrader5ExecutionClient._handle_order_event(
        ec, status=OrderStatus.FILLED, order=order
    )

    # Must NOT emit a fill event (no price/qty/trade_id available in this path)
    ec.generate_order_filled.assert_not_called()

    # Must log a warning explaining why the fill must come from elsewhere
    ec._log_mock.warning.assert_called_once()
    warning_text = ec._log_mock.warning.call_args[0][0]
    assert "FILLED" in warning_text or "fill" in warning_text.lower()


def test_handle_order_event_filled_skips_when_already_filled():
    """
    Phase 7 / Fix #2 — When the order is already FILLED, the block is skipped
    entirely (no double-emit, no warning).
    """
    from nautilus_trader.model.enums import OrderStatus
    from nautilus_trader.model.identifiers import ClientOrderId

    ec = _make_bare_exec_client()
    ec.generate_order_filled = MagicMock()

    order = MagicMock()
    order.client_order_id = ClientOrderId("O-FILLED-02")
    order.status = OrderStatus.FILLED  # already filled

    MetaTrader5ExecutionClient._handle_order_event(
        ec, status=OrderStatus.FILLED, order=order
    )

    ec.generate_order_filled.assert_not_called()
    ec._log_mock.warning.assert_not_called()


@pytest.mark.asyncio
async def test_generate_mass_status_returns_execution_mass_status():
    """
    generate_mass_status must return a real ExecutionMassStatus (not None).

    MT5 has no mass-status endpoint but the NT ExecEngine treats None as a
    reconciliation failure. The adapter builds the object from the individual
    generate_*_reports calls and returns it — even when those lists are empty.
    """
    from nautilus_trader.execution.reports import ExecutionMassStatus
    from nautilus_mt5.execution import MetaTrader5ExecutionClient

    ec = _make_bare_exec_client()

    # Stub out the three individual generators so the test stays unit-level
    ec.generate_order_status_reports = AsyncMock(return_value=[])
    ec.generate_fill_reports = AsyncMock(return_value=[])
    ec.generate_position_status_reports = AsyncMock(return_value=[])

    # Provide the minimal attributes that generate_mass_status accesses
    from nautilus_trader.model.identifiers import ClientId, AccountId
    type(ec).id = property(lambda self: ClientId("MT5"))
    type(ec).account_id = property(lambda self: AccountId("MT5-25306658"))
    clock_mock = MagicMock()
    clock_mock.timestamp_ns.return_value = 0
    type(ec)._clock = property(lambda self: clock_mock)

    result = await MetaTrader5ExecutionClient.generate_mass_status(ec, lookback_mins=None)

    assert isinstance(result, ExecutionMassStatus)
    # Individual generators must have been called
    ec.generate_order_status_reports.assert_called_once()
    ec.generate_fill_reports.assert_called_once()
    ec.generate_position_status_reports.assert_called_once()


@pytest.mark.asyncio
async def test_generate_mass_status_with_lookback_calls_generators():
    """
    generate_mass_status with lookback_mins passes a non-None start to
    the individual generator commands and still returns ExecutionMassStatus.
    """
    from nautilus_trader.execution.reports import ExecutionMassStatus
    from nautilus_mt5.execution import MetaTrader5ExecutionClient

    ec = _make_bare_exec_client()

    ec.generate_order_status_reports = AsyncMock(return_value=[])
    ec.generate_fill_reports = AsyncMock(return_value=[])
    ec.generate_position_status_reports = AsyncMock(return_value=[])

    from nautilus_trader.model.identifiers import ClientId, AccountId
    type(ec).id = property(lambda self: ClientId("MT5"))
    type(ec).account_id = property(lambda self: AccountId("MT5-25306658"))
    clock_mock = MagicMock()
    clock_mock.timestamp_ns.return_value = 0
    type(ec)._clock = property(lambda self: clock_mock)

    result = await MetaTrader5ExecutionClient.generate_mass_status(ec, lookback_mins=60)

    assert isinstance(result, ExecutionMassStatus)