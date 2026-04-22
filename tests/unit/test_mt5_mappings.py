import pytest

from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.enums import OrderType

from nautilus_mt5.parsing.execution import (
    MT5_ORDER_TYPE_TO_ORDER_SIDE,
    MT5_ORDER_TYPE_TO_ORDER_TYPE,
    ORDER_TYPE_BUY,
    ORDER_TYPE_SELL,
    ORDER_TYPE_BUY_LIMIT,
    ORDER_TYPE_SELL_LIMIT,
    ORDER_TYPE_BUY_STOP,
    ORDER_TYPE_SELL_STOP,
    ORDER_TYPE_BUY_STOP_LIMIT,
    ORDER_TYPE_SELL_STOP_LIMIT,
    ORDER_TIME_SPECIFIED,
    ORDER_TIME_SPECIFIED_DAY,
)
from nautilus_mt5.execution import MetaTrader5ExecutionClient
from nautilus_mt5.metatrader5.models import Order as MT5Order
from unittest.mock import AsyncMock, MagicMock


def test_order_side_mapping():
    assert MT5_ORDER_TYPE_TO_ORDER_SIDE[ORDER_TYPE_BUY] == OrderSide.BUY
    assert MT5_ORDER_TYPE_TO_ORDER_SIDE[ORDER_TYPE_BUY_LIMIT] == OrderSide.BUY
    assert MT5_ORDER_TYPE_TO_ORDER_SIDE[ORDER_TYPE_BUY_STOP] == OrderSide.BUY
    assert MT5_ORDER_TYPE_TO_ORDER_SIDE[ORDER_TYPE_BUY_STOP_LIMIT] == OrderSide.BUY

    assert MT5_ORDER_TYPE_TO_ORDER_SIDE[ORDER_TYPE_SELL] == OrderSide.SELL
    assert MT5_ORDER_TYPE_TO_ORDER_SIDE[ORDER_TYPE_SELL_LIMIT] == OrderSide.SELL
    assert MT5_ORDER_TYPE_TO_ORDER_SIDE[ORDER_TYPE_SELL_STOP] == OrderSide.SELL
    assert MT5_ORDER_TYPE_TO_ORDER_SIDE[ORDER_TYPE_SELL_STOP_LIMIT] == OrderSide.SELL


def test_order_type_mapping():
    assert MT5_ORDER_TYPE_TO_ORDER_TYPE[ORDER_TYPE_BUY] == OrderType.MARKET
    assert MT5_ORDER_TYPE_TO_ORDER_TYPE[ORDER_TYPE_SELL] == OrderType.MARKET

    assert MT5_ORDER_TYPE_TO_ORDER_TYPE[ORDER_TYPE_BUY_LIMIT] == OrderType.LIMIT
    assert MT5_ORDER_TYPE_TO_ORDER_TYPE[ORDER_TYPE_SELL_LIMIT] == OrderType.LIMIT

    assert MT5_ORDER_TYPE_TO_ORDER_TYPE[ORDER_TYPE_BUY_STOP] == OrderType.STOP_MARKET
    assert MT5_ORDER_TYPE_TO_ORDER_TYPE[ORDER_TYPE_SELL_STOP] == OrderType.STOP_MARKET

    assert MT5_ORDER_TYPE_TO_ORDER_TYPE[ORDER_TYPE_BUY_STOP_LIMIT] == OrderType.STOP_LIMIT
    assert MT5_ORDER_TYPE_TO_ORDER_TYPE[ORDER_TYPE_SELL_STOP_LIMIT] == OrderType.STOP_LIMIT


@pytest.mark.asyncio
async def test_expire_time_parsing():
    exec_client = MetaTrader5ExecutionClient.__new__(MetaTrader5ExecutionClient)

    mock_instrument = MagicMock()
    mock_instrument.id = MagicMock()
    mock_instrument.make_price = MagicMock(return_value=None)

    provider_mock = MagicMock()
    provider_mock.find_with_symbol_id = AsyncMock(return_value=mock_instrument)
    type(exec_client).instrument_provider = property(lambda self: provider_mock)

    type(exec_client).account_id = property(lambda self: MagicMock())
    type(exec_client)._log = property(lambda self: MagicMock())

    mock_clock = MagicMock()
    mock_clock.timestamp_ns = MagicMock(return_value=123)
    type(exec_client)._clock = property(lambda self: mock_clock)

    # 1. Test with ORDER_TIME_SPECIFIED
    mt5_order = MT5Order(
        order_id=1,
        type=ORDER_TYPE_BUY_LIMIT,
        type_time=ORDER_TIME_SPECIFIED,
        expire_time="2023-01-01 12:00:00 UTC",
            orderRef="client1",
            volume=1.5
    )

    report = await exec_client._parse_mt5_order_to_order_status_report(mt5_order)
    assert report.expire_time is not None
    assert str(report.expire_time.value) == "1672574400000000000" # pd.Timestamp("2023-01-01 12:00:00", tz="UTC")
    assert report.order_side == OrderSide.BUY
    assert report.order_type == OrderType.LIMIT

    # 2. Test with ORDER_TIME_SPECIFIED_DAY
    mt5_order.type_time = ORDER_TIME_SPECIFIED_DAY
    report = await exec_client._parse_mt5_order_to_order_status_report(mt5_order)
    assert report.expire_time is not None

    # 3. Test with ORDER_TIME_GTC (should not parse expire_time)
    mt5_order.type_time = 0 # ORDER_TIME_GTC
    report = await exec_client._parse_mt5_order_to_order_status_report(mt5_order)
    assert report.expire_time is None
