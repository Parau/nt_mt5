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
        self.order_type = OrderType.MARKET
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

def test_performance_order_transform(monkeypatch):
    """
    Ensure order transformation mapping works within acceptable performance margins.
    """
    iterations = 1000
    order = MockOrder()

    provider_mock = MagicMock()
    mock_details = MT5SymbolDetails(filling_mode=1)
    provider_mock.symbol_details = {order.instrument_id.value: mock_details}

    # Pure Python stub — avoids patching Cython extension type attributes
    class _StubAccountId:
        value = "12345"
        def get_id(self):
            return self.value

    class _StubExecClient:
        account_id = _StubAccountId()
        _instrument_provider = provider_mock

    stub = _StubExecClient()

    class MockInstrument:
        def __init__(self):
            self.info = {"symbol": {"symbol": "EURUSD", "broker": "METATRADER_5"}}

    mock_instrument = MockInstrument()

    start_time = time.perf_counter()
    for _ in range(iterations):
        MetaTrader5ExecutionClient._transform_order_to_mt5_order(stub, order, mock_instrument)
    end_time = time.perf_counter()

    duration = end_time - start_time
    assert duration < 0.5, f"Order transform too slow: {duration} seconds for {iterations} iterations."

def test_performance_report_generation():
    """
    Ensure execution parsing functions (order type mapping, fill type) work within acceptable margins.
    Uses pure Python to avoid Cython class pollution.
    """
    from nautilus_mt5.parsing.execution import map_order_type_and_action, map_filling_type

    iterations = 5000

    start_time = time.perf_counter()
    for _ in range(iterations):
        map_order_type_and_action(OrderType.MARKET, OrderSide.BUY)
        map_order_type_and_action(OrderType.LIMIT, OrderSide.SELL)
        map_filling_type(TimeInForce.GTC)
        map_filling_type(TimeInForce.FOK)
    end_time = time.perf_counter()

    duration = end_time - start_time
    assert duration < 1.0, f"Execution parsing too slow: {duration} seconds for {iterations} iterations."

def test_performance_tick_parsing():
    """
    Ensure trade ID generation and symbology parsing are fast.
    Uses pure Python to avoid Cython class pollution.
    """
    from nautilus_mt5.parsing.data import generate_trade_id
    from nautilus_mt5.parsing.instruments import mt5_symbol_to_instrument_id_simplified_symbology
    from nautilus_mt5.data_types import MT5Symbol
    from decimal import Decimal

    mt5_sym = MT5Symbol(symbol="EURUSD", broker="METATRADER_5")
    iterations = 1000
    start_time = time.perf_counter()
    for i in range(iterations):
        generate_trade_id(1600000000000 + i, 1.1000 + i * 0.0001, Decimal("1.0"))
        mt5_symbol_to_instrument_id_simplified_symbology(mt5_sym)
    end_time = time.perf_counter()

    duration = end_time - start_time
    assert duration < 2.0, f"Tick parsing too slow: {duration} seconds for {iterations} iterations."
