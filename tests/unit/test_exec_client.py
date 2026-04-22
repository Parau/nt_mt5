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

    assert not exec_client._set_connected.called

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

    with pytest.raises(ConnectionError, match="Account mismatch"):
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
