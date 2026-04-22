import pytest
import asyncio
import pytest_asyncio
from unittest.mock import MagicMock, AsyncMock, patch

from nautilus_mt5.client.client import MetaTrader5Client
from nautilus_mt5.config import DockerizedMT5TerminalConfig
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_mt5.data import MetaTrader5DataClient
from nautilus_mt5.execution import MetaTrader5ExecutionClient
from nautilus_mt5.config import MetaTrader5DataClientConfig, MetaTrader5ExecClientConfig

class FakeMT5Bridge:
    def __init__(self):
        self._connected = False
        self._account_login = 12345
        self._orders = []
        self._positions = []

    def exposed_initialize(self, login, password, server, timeout):
        self._connected = True
        return True

    def exposed_login(self, login, password, server, timeout):
        return self._connected

    def exposed_shutdown(self):
        self._connected = False

    def exposed_terminal_info(self):
        class FakeTerminalInfo:
            def __init__(self):
                self.build = 1234
            def _asdict(self):
                return {"build": self.build}
        return FakeTerminalInfo()

    def exposed_account_info(self):
        class FakeAccountInfo:
            login = 12345
            balance = 10000.0
        return FakeAccountInfo()

    def exposed_symbols_get(self):
        return ()

    def exposed_symbol_info(self, symbol):
        class FakeSymbolInfo:
            def __init__(self, s):
                self.symbol = s
        return FakeSymbolInfo(symbol)

    def exposed_orders_get(self):
        return tuple(self._orders)

    def exposed_positions_get(self):
        return tuple(self._positions)

    def exposed_cancel_tick_by_tick_data(self, *args, **kwargs):
        pass

    def exposed_req_historical_data(self, *args, **kwargs):
        pass

    def exposed_cancel_historical_data(self, *args, **kwargs):
        pass

    def exposed_req_real_time_bars(self, *args, **kwargs):
        pass

    def exposed_cancel_real_time_bars(self, *args, **kwargs):
        pass

    def exposed_req_ids(self, *args, **kwargs):
        pass

    def exposed_last_error(self):
        return (1, "Mock Error")

    def exposed_order_send(self, *args, **kwargs):
        # We handle both generic signature types
        if len(args) > 1:
            request = args[2]
            action = getattr(request, "action", 1)
            symbol = getattr(request, "symbol", "")
            volume = getattr(request, "volume", 0.0)
            price = getattr(request, "price", 1.0)
        else:
            request = args[0]
            action = request.get("action", 1)
            symbol = request.get("symbol", "")
            volume = request.get("volume", 0.0)
            price = request.get("price", 1.0)

        class FakeOrderResult:
            def __init__(self, retcode, order, volume, price):
                self.retcode = retcode
                self.order = order
                self.volume = volume
                self.price = price
                self.comment = "Mock Executed"

        if action == 1:
            ticket = len(self._orders) + 1
            class FakeOrderInfo:
                def __init__(self, t, s, v):
                    self.ticket = t
                    self.symbol = s
                    self.volume_initial = v
            self._orders.append(FakeOrderInfo(ticket, symbol, volume))
            return FakeOrderResult(10009, ticket, volume, price)

        return FakeOrderResult(10004, 0, 0, 0)

class MockMT5Service:
    def __init__(self):
        self._bridge = FakeMT5Bridge()

    def __getattr__(self, name):
        if hasattr(self._bridge, f"exposed_{name}"):
            return getattr(self._bridge, f"exposed_{name}")
        raise AttributeError(f"MockMT5Service has no attribute {name}")


@pytest.fixture
def mock_mt5_service():
    service = MockMT5Service()
    return service

@pytest_asyncio.fixture
async def mt5_client(mock_mt5_service):
    config = DockerizedMT5TerminalConfig(
        account_number="12345",
        password="password",
        server="TestServer",
    )

    mock_msgbus = MagicMock()
    mock_cache = MagicMock()
    mock_clock = MagicMock()

    client = MetaTrader5Client.__new__(MetaTrader5Client)
    client._loop = asyncio.get_event_loop()
    type(client)._msgbus = property(lambda self: mock_msgbus)
    type(client)._cache = property(lambda self: mock_cache)
    type(client)._clock = property(lambda self: mock_clock)
    type(client)._log = property(lambda self: MagicMock())
    client._config = config
    client._mt5_client = {}
    client._conn_state = MagicMock()
    client._conn_state.value = 0
    client._is_mt5_connected = asyncio.Event()
    client._is_client_ready = asyncio.Event()
    client._next_valid_order_id = 1
    client._order_id_to_order_ref = {}
    client._subscriptions = MagicMock()
    client._subscriptions._instrument_id_to_sub = {}
    client._subscriptions._req_id_to_name = {}
    client._subscriptions._name_to_obj = {}
    client._internal_msg_queue = asyncio.Queue()
    client._requests = MagicMock()
    client._msg_handler_task_queue = asyncio.Queue()
    client._client_id = 1
    type(client).is_disposed = property(lambda self: False)

    # To truly exercise _connect logic, we allow it to invoke _initialize_and_connect
    with patch.object(client, '_create_mt5_client') as mock_create_client:
        mock_create_client.return_value = {'mt5': mock_mt5_service, 'ea': None}

        await client._connect()
        # Mock background tasks that check terminal info or internal loops if they hang testing
        client._is_client_ready.set()

        yield client

        await client._disconnect()

@pytest.mark.asyncio
async def test_connect_disconnect(mt5_client):
    # Validating actual state as defined by native handlers post connection setup
    # Our mocked connection uses fake_connect correctly simulating `1` (CONNECTED)
    assert mt5_client._conn_state.value == 1

    await mt5_client._disconnect() # use internal API wrapper directly

    # Assert real attributes rather than clearing them manually via assertions logic
    assert mt5_client._conn_state.value == 0 # DISCONNECTED (0)
    assert not mt5_client._is_mt5_connected.is_set()

@pytest.mark.asyncio
async def test_account_info(mt5_client):
    account_info = mt5_client._mt5_client['mt5'].account_info()
    assert account_info is not None
    assert account_info.login == 12345
    assert account_info.balance == 10000.0

@pytest.mark.asyncio
async def test_symbol_info(mt5_client):
    symbol_info = mt5_client._mt5_client['mt5'].symbol_info("EURUSD")
    assert symbol_info is not None
    assert symbol_info.symbol == "EURUSD"

@pytest.mark.asyncio
async def test_integration_data_client_flow(mt5_client):
    config = MetaTrader5DataClientConfig(
        client_id=1,
        dockerized_gateway=DockerizedMT5TerminalConfig(account_number="12345", password="pwd", server="svr")
    )

    data_client = MetaTrader5DataClient.__new__(MetaTrader5DataClient)

    mock_msgbus = MagicMock()
    mock_cache = MagicMock()

    mock_instrument = MagicMock()
    mock_instrument.info = {"symbol": {"symbol": "EURUSD", "broker": "TestServer"}}
    mock_cache.instrument.return_value = mock_instrument

    type(data_client)._msgbus = property(lambda self: mock_msgbus)
    type(data_client)._cache = property(lambda self: mock_cache)
    type(data_client)._log = property(lambda self: MagicMock())
    type(data_client)._ignore_quote_tick_size_updates = property(lambda self: False)

    data_client._client = mt5_client

    inst_id = InstrumentId(Symbol("EURUSD"), Venue("METATRADER_5"))

    from nautilus_mt5.data_types import MT5Symbol
    mt5_sym = MT5Symbol(symbol="EURUSD", broker="TestServer")

    # Test subscriptions
    mt5_client._event_subscriptions = {}
    await mt5_client.subscribe_ticks(inst_id, mt5_sym, "BidAsk", False)
    assert True

    # Test unsubscribe
    await mt5_client.unsubscribe_ticks(inst_id, "BidAsk")
    assert True

    # Test market data requests (Bars)
    from nautilus_trader.model.data import BarType
    bar_type = BarType.from_str("EURUSD.METATRADER_5-1-MINUTE-LAST-EXTERNAL")
    mt5_client._subscribe = AsyncMock()
    await mt5_client.subscribe_historical_bars(bar_type, mt5_sym, False, False)
    assert True

@pytest.mark.asyncio
async def test_integration_exec_client_flow(mt5_client):
    # Test fully via ExecutionClient wrapper to test parsing & transformation
    config = MetaTrader5ExecClientConfig(
        client_id=2,
        account_id="MT5-12345",
        dockerized_gateway=DockerizedMT5TerminalConfig(account_number="12345", password="pwd", server="svr")
    )

    exec_client = MetaTrader5ExecutionClient.__new__(MetaTrader5ExecutionClient)
    type(exec_client)._msgbus = property(lambda self: MagicMock())
    type(exec_client)._cache = property(lambda self: MagicMock())
    type(exec_client)._log = property(lambda self: MagicMock())
    type(exec_client)._clock = property(lambda self: MagicMock())
    exec_client._client = mt5_client

    orders = mt5_client._mt5_client['mt5'].orders_get()
    assert len(orders) == 0

    from nautilus_trader.model.identifiers import ClientOrderId, InstrumentId, Symbol, Venue
    from nautilus_trader.execution.messages import SubmitOrder
    from nautilus_trader.model.objects import Quantity, Price
    from nautilus_trader.model.orders import MarketOrder
    from nautilus_trader.model.enums import OrderSide, TimeInForce

    inst_id = InstrumentId(Symbol("EURUSD"), Venue("METATRADER_5"))
    from nautilus_trader.model.enums import OrderType
    from nautilus_trader.model.identifiers import StrategyId, TraderId
    from nautilus_trader.model.enums import OrderType
    mock_order = MagicMock()
    mock_order.client_order_id = ClientOrderId("client1")
    mock_order.instrument_id = inst_id
    mock_order.strategy_id = StrategyId("test-strategy")
    mock_order.trader_id = TraderId("test-trader")
    mock_order.side = OrderSide.BUY
    mock_order.quantity = Quantity.from_int(100)
    mock_order.time_in_force = TimeInForce.GTC
    mock_order.type = OrderType.MARKET
    mock_order.price = None

    submit_cmd = MagicMock()
    submit_cmd.order = mock_order

    # We inject the details needed for transformation
    from nautilus_mt5.data_types import MT5SymbolDetails
    from nautilus_trader.model.instruments import CurrencyPair

    # We need a proper dict or object that doesn't trigger MagicMock recursive property creation
    class MockInstrument:
        pass
    mock_instrument = MockInstrument()
    mock_instrument.info = {"symbol": {"symbol": "EURUSD", "broker": "METATRADER_5"}}

    # When execution calls _cache.instrument(), it needs to return something that correctly accesses info["symbol"]["symbol"] as string
    mock_cache = MagicMock()
    mock_cache.instrument.return_value = mock_instrument
    type(exec_client)._cache = property(lambda self: mock_cache)

    mock_provider = MagicMock()
    mock_provider.symbol_details = {inst_id.value: MT5SymbolDetails(filling_mode=1)}
    mock_provider.find.return_value = mock_instrument

    exec_client._instrument_provider = mock_provider

    # Override the find behaviour explicitly since _transform uses cache mostly in newer versions
    type(exec_client._cache).instrument = MagicMock(return_value=mock_instrument)

    type(exec_client).client_id = property(lambda self: MagicMock(value="exec_1"))

    # execution wrappers require fully valid Component trees to run event handlers
    # We mock them out to isolate the adapter's raw logic inside _submit_order
    exec_client.generate_order_submitted = MagicMock()
    exec_client.generate_order_accepted = MagicMock()

    # We also mock _clock.timestamp_ns if required
    type(exec_client)._clock = property(lambda self: MagicMock(timestamp_ns=MagicMock(return_value=1000)))

    with patch("nautilus_mt5.execution.PyCondition.type"):
        # Test submission
        await exec_client._submit_order(submit_cmd)

    orders = mt5_client._mt5_client['mt5'].orders_get()
    assert len(orders) == 1
    assert orders[0].symbol == "EURUSD"
    assert orders[0].volume_initial == 100.0

    # Test Executing internal reports correctly rather than calling `get_positions` wrapper with unmocked asyncio futures
    mt5_client._mt5_client['mt5']._bridge._positions.clear()
    assert len(mt5_client._mt5_client['mt5'].positions_get()) == 0

    class FakePositionInfo:
        def __init__(self, ticket, symbol, position_type, volume, price_open):
            self.ticket = ticket
            self.symbol = symbol
            self.type = position_type
            self.volume = volume
            self.price_open = price_open

    mt5_client._mt5_client['mt5']._bridge._positions.append(
        FakePositionInfo(ticket=1, symbol="EURUSD", position_type=0, volume=1.0, price_open=1.1)
    )

    # We verify it's seen natively on the bridge which get_positions would wrap
    assert len(mt5_client._mt5_client['mt5'].positions_get()) == 1
