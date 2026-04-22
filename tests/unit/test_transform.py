import pytest
from unittest.mock import MagicMock
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue, ClientOrderId, TraderId, StrategyId
from nautilus_trader.model.enums import OrderSide, TimeInForce, OrderType
from nautilus_trader.model.objects import Quantity

from nautilus_mt5.execution import MetaTrader5ExecutionClient
from nautilus_mt5.data_types import MT5SymbolDetails

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

def test_transform_market_order_mocked():
    order = MockOrder()

    provider_mock = MagicMock()
    mock_details = MT5SymbolDetails(filling_mode=1) # FOK
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
    mt5_order = exec_client._transform_order_to_mt5_order(order, mock_instrument)

    assert mt5_order.type == 0 # BUY
    assert mt5_order.volume == 100.0
    assert mt5_order.type_time == 0 # GTC

    # The adapter explicitly maps TimeInForce.GTC to ORDER_FILLING_RETURN (2) as the fallback.
    assert mt5_order.type_filling == 2 # RETURN
    assert mt5_order.account == "12345"

def test_transform_limit_order_mocked():
    from nautilus_trader.model.objects import Price

    order = MockOrder()
    order.type = OrderType.LIMIT
    order.price = Price.from_str("1.1500")

    provider_mock = MagicMock()
    mock_details = MT5SymbolDetails(filling_mode=2) # filling_mode IOC
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
    mt5_order = exec_client._transform_order_to_mt5_order(order, mock_instrument)

    assert mt5_order.type == 2 # BUY_LIMIT
    assert mt5_order.price == 1.1500
