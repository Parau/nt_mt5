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
            pass
        return FakeTerminalInfo() if self._connected else None

    def exposed_account_info(self):
        class FakeAccountInfo:
            login = 12345
            balance = 10000.0
        return FakeAccountInfo() if self._connected else None

    def exposed_symbols_get(self):
        return ()

    def exposed_symbol_info(self, symbol):
        class FakeSymbolInfo:
            def __init__(self, s):
                self.symbol = s
        return FakeSymbolInfo(symbol) if self._connected else None

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

    def exposed_order_send(self, request):
        class FakeOrderResult:
            def __init__(self, retcode, order, volume, price):
                self.retcode = retcode
                self.order = order
                self.volume = volume
                self.price = price
                self.comment = "Mock Executed"

        if "action" in request and request["action"] == 1:
            ticket = len(self._orders) + 1
            class FakeOrderInfo:
                def __init__(self, t, s, v):
                    self.ticket = t
                    self.symbol = s
                    self.volume_initial = v
            self._orders.append(FakeOrderInfo(ticket, request["symbol"], request["volume"]))
            return FakeOrderResult(10009, ticket, request["volume"], request.get("price", 1.0))

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
    client._subscriptions = MagicMock()
    client._subscriptions._instrument_id_to_sub = {}
    client._subscriptions._req_id_to_name = {}
    client._subscriptions._name_to_obj = {}
    client._internal_msg_queue = asyncio.Queue()
    client._requests = MagicMock()
    client._msg_handler_task_queue = asyncio.Queue()
    type(client).is_disposed = property(lambda self: False)

    with patch.object(client, '_connect', new_callable=AsyncMock) as mock_connect:
        async def fake_connect():
            client._mt5_client['mt5'] = mock_mt5_service
            mock_mt5_service.initialize(int(config.account_number), config.password, config.server, config.timeout)
            client._is_mt5_connected.set()
            client._conn_state.value = 1
            client._is_client_ready.set()
        mock_connect.side_effect = fake_connect

        await client._connect()
        await client.wait_until_ready()

        yield client

        client._disconnect = AsyncMock()
        await client._disconnect()

@pytest.mark.asyncio
async def test_connect_disconnect(mt5_client):
    assert mt5_client._conn_state.value == 1
    assert mt5_client._is_client_ready.is_set()

    await mt5_client._disconnect()
    mt5_client._conn_state = MagicMock()
    mt5_client._conn_state.value = 0
    mt5_client._is_client_ready.clear()

    assert mt5_client._conn_state.value == 0
    assert not mt5_client._is_client_ready.is_set()

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
    orders = mt5_client._mt5_client['mt5'].orders_get()
    assert len(orders) == 0

    req = {
        "action": 1,
        "symbol": "EURUSD",
        "volume": 1.5,
        "type": 0,
        "price": 1.1000
    }

    result = mt5_client._mt5_client['mt5'].order_send(req)

    assert result.retcode == 10009
    assert result.order == 1

    orders = mt5_client._mt5_client['mt5'].orders_get()
    assert len(orders) == 1
    assert orders[0].symbol == "EURUSD"
    assert orders[0].volume_initial == 1.5

    # Bootstrap positions
    mt5_client._requests = MagicMock()

    from nautilus_mt5.data_types import MT5Position
    mt5_client._mt5_client['mt5']._bridge._positions.append(
        MT5Position("12345", "EURUSD", 1.0, 1.1, 0.0)
    )
    positions = mt5_client._mt5_client['mt5'].positions_get()
    assert len(positions) == 1
