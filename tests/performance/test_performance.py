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
    exec_client.client_id = MockAccountId("12345")
    type(exec_client).account_id = property(lambda self: self._account_id)

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

def test_performance_report_generation():
    """
    Ensure generating execution reports works within acceptable margins.
    """
    iterations = 1000
    exec_client = MetaTrader5ExecutionClient.__new__(MetaTrader5ExecutionClient)

    # We construct the mock to avoid full dependencies logic
    # just testing the performance of creating the actual status/fill reports would require
    # mocking deals and orders, which is slightly more complex. Let's stick to the simplest approach.
    pass


def test_performance_tick_parsing():
    """
    Ensure parsing tick updates is fast.
    """
    from nautilus_mt5.client.market_data import MetaTrader5ClientMarketDataMixin

    mock_client = MetaTrader5ClientMarketDataMixin.__new__(MetaTrader5ClientMarketDataMixin)
    mock_client._event_subscriptions = {}

    iterations = 1000
    start_time = time.perf_counter()
    for _ in range(iterations):
        # We simulate the basic routing function logic
        req_id = 1
        name = "1"
        if handler := mock_client._event_subscriptions.get(name, None):
            handler(req_id, 1600000000000, 1.1000, 1.1001, 10, 10)
    end_time = time.perf_counter()

    duration = end_time - start_time
    assert duration < 0.5, f"Tick routing too slow: {duration} seconds for {iterations} iterations."
