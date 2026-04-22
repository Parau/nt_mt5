import pytest
import time
from unittest.mock import MagicMock
from decimal import Decimal
import pandas as pd

from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue, ClientOrderId
from nautilus_trader.model.enums import OrderSide, OrderType, TimeInForce
from nautilus_trader.model.objects import Quantity

from nautilus_mt5.data_types import MT5SymbolDetails
from nautilus_mt5.execution import MetaTrader5ExecutionClient
from nautilus_mt5.parsing.instruments import mt5_symbol_to_instrument_id_simplified_symbology
from nautilus_mt5.data_types import MT5Symbol

class MockOrder:
    def __init__(self):
        self.instrument_id = InstrumentId(Symbol("EURUSD"), Venue("METATRADER_5"))
        self.quantity = Quantity.from_int(100)
        self.client_order_id = ClientOrderId("client1")
        self.side = OrderSide.BUY
        self.type = OrderType.MARKET
        self.price = None
        self.time_in_force = TimeInForce.GTC
        self.is_post_only = False
        self.tags = []

def test_performance_instrument_parsing():
    """
    Ensure that parsing instrument symbology happens within a reasonable time.
    """
    iterations = 1000
    mt5_sym = MT5Symbol(symbol="EURUSD", broker="METATRADER_5")

    start_time = time.perf_counter()
    for _ in range(iterations):
        mt5_symbol_to_instrument_id_simplified_symbology(mt5_sym)
    end_time = time.perf_counter()

    duration = end_time - start_time
    assert duration < 0.5, f"Symbology parsing too slow: {duration} seconds for {iterations} iterations."

def test_performance_order_transform():
    """
    Ensure order transformation mapping works within acceptable performance margins.
    """
    iterations = 1000
    order = MockOrder()

    provider_mock = MagicMock()
    mock_details = MT5SymbolDetails(filling_mode=1)
    provider_mock.symbol_details = {order.instrument_id.value: mock_details}

    exec_client = MetaTrader5ExecutionClient.__new__(MetaTrader5ExecutionClient)
    exec_client._instrument_provider = provider_mock

    class MockAccountId:
        def __init__(self, val):
            self.value = val
        def get_id(self):
            return self.value

    exec_client._account_id = MockAccountId("12345")
    type(exec_client).account_id = property(lambda self: self._account_id)
    type(exec_client).client_id = property(lambda self: self._account_id)

    class MockInstrument:
        def __init__(self):
            self.info = {"symbol": {"symbol": "EURUSD", "broker": "METATRADER_5"}}

    mock_instrument = MockInstrument()

    start_time = time.perf_counter()
    for _ in range(iterations):
        exec_client._transform_order_to_mt5_order(order, mock_instrument)
    end_time = time.perf_counter()

    duration = end_time - start_time
    assert duration < 0.5, f"Order transform too slow: {duration} seconds for {iterations} iterations."

@pytest.mark.asyncio
async def test_performance_report_generation():
    """
    Ensure generating execution reports works within acceptable margins.
    """
    iterations = 100
    exec_client = MetaTrader5ExecutionClient.__new__(MetaTrader5ExecutionClient)
    exec_client._client = MagicMock()

    # Mocking MT5 Order
    class MockMT5Order:
        def __init__(self, t, s, v):
            self.ticket = t
            self.symbol = s
            self.volume_initial = v
            self.type = 0 # BUY
            self.volume_current = v
            self.price_open = 1.0
            self.state = 1
            self.time_setup = 1600000000
            self.time_setup_msc = 1600000000000
            self.time_update = 1600000000
            self.time_update_msc = 1600000000000
            self.price_current = 1.0
            self.sl = 0.0
            self.tp = 0.0
            self.comment = "MockOrder"
            self.external_id = str(t)

    orders = [MockMT5Order(i, "EURUSD", 10.0) for i in range(10)]

    # Mock out _client._requests
    from unittest.mock import AsyncMock
    exec_client._client.get_orders = AsyncMock(return_value=orders)
    exec_client._client.get_positions = AsyncMock(return_value=[])
    exec_client._generate_order_status_reports = MagicMock(side_effect=lambda a,b,c: [1,2,3])
    type(exec_client)._log = property(lambda self: MagicMock())
    type(exec_client).venue = property(lambda self: Venue("METATRADER_5"))

    mock_account_id = MagicMock()
    mock_account_id.get_id = MagicMock(return_value="MT5-12345")
    type(exec_client).account_id = property(lambda self: mock_account_id)
    type(exec_client).client_id = property(lambda self: mock_account_id)

    mock_instrument = MagicMock()
    mock_instrument.info = {"symbol": {"symbol": "EURUSD", "broker": "METATRADER_5"}}

    mock_provider = MagicMock()
    mock_provider.find_by_symbol.return_value = mock_instrument
    exec_client._instrument_provider = mock_provider

    from nautilus_trader.execution.messages import GenerateOrderStatusReports
    # Mocking since Cython struct initialization can conflict if fields are unset
    command = MagicMock()
    command.client_id = exec_client.client_id

    start_time = time.perf_counter()
    for _ in range(iterations):
        # Simply testing the wrapper/mock logic iteration handling overhead to avoid cython faults
        await exec_client.generate_order_status_reports(command)
    end_time = time.perf_counter()

    duration = end_time - start_time
    assert duration < 1.0, f"Report generation too slow: {duration} seconds for {iterations} iterations."

def test_performance_tick_parsing():
    """
    Ensure parsing tick updates is fast using real adapter processing.
    """
    from nautilus_mt5.client.client import MetaTrader5Client
    from nautilus_trader.model.identifiers import InstrumentId
    import asyncio

    client = MetaTrader5Client.__new__(MetaTrader5Client)
    client._loop = MagicMock()
    client._subscriptions = MagicMock()
    client._subscriptions._name_to_obj = {
        "1": MagicMock(args=[MagicMock(symbol="EURUSD")], req_id=1)
    }

    from unittest.mock import AsyncMock
    # We mock process_tick_by_tick_bid_ask to measure the _process_message mapping overhead
    client.process_tick_by_tick_bid_ask = AsyncMock()

    iterations = 1000
    start_time = time.perf_counter()

    # Manually run the async loop for testing performance
    async def run_iterations():
        for _ in range(iterations):
            msg = {
                "type": "tick",
                "data": {
                    "time_msc": 1600000000000,
                    "bid": 1.1000,
                    "ask": 1.1001,
                },
                "symbol": "EURUSD"
            }
            await client._process_message(msg)

    asyncio.run(run_iterations())

    end_time = time.perf_counter()

    duration = end_time - start_time
    assert duration < 0.5, f"Tick routing/parsing too slow: {duration} seconds for {iterations} iterations."
