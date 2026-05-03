
import pandas as pd

from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.enums import OrderStatus
from nautilus_trader.model.enums import OrderType
from nautilus_trader.model.enums import TimeInForce

# MT5 Trade actions
TRADE_ACTION_DEAL = 1
TRADE_ACTION_PENDING = 5

# MT5 Trade retcodes
TRADE_RETCODE_PLACED = 10008       # order placed (pending), not yet executed
TRADE_RETCODE_DONE = 10009         # request completed (market order filled / pending placed)
TRADE_RETCODE_DONE_PARTIAL = 10010 # only part of the request was completed

# MT5 Deal types
DEAL_TYPE_BUY = 0
DEAL_TYPE_SELL = 1
TRADE_ACTION_SLTP = 6
TRADE_ACTION_MODIFY = 7
TRADE_ACTION_REMOVE = 8
TRADE_ACTION_CLOSE_BY = 10

# MT5 Order types
ORDER_TYPE_BUY = 0
ORDER_TYPE_SELL = 1
ORDER_TYPE_BUY_LIMIT = 2
ORDER_TYPE_SELL_LIMIT = 3
ORDER_TYPE_BUY_STOP = 4
ORDER_TYPE_SELL_STOP = 5
ORDER_TYPE_BUY_STOP_LIMIT = 6
ORDER_TYPE_SELL_STOP_LIMIT = 7

# MT5 Time in force
ORDER_TIME_GTC = 0
ORDER_TIME_DAY = 1
ORDER_TIME_SPECIFIED = 2
ORDER_TIME_SPECIFIED_DAY = 3

# MT5 Order Filling
ORDER_FILLING_FOK = 0
ORDER_FILLING_IOC = 1
ORDER_FILLING_RETURN = 2
ORDER_FILLING_BOC = 3

MAP_TIME_IN_FORCE: dict[int, int] = {
    TimeInForce.GTC: ORDER_TIME_GTC,
    TimeInForce.DAY: ORDER_TIME_DAY,
    TimeInForce.FOK: ORDER_TIME_GTC,  # Handled via type_filling
    TimeInForce.IOC: ORDER_TIME_GTC,  # Handled via type_filling
}

# ---------------------------------------------------------------------------
# Pre-venue validation
# ---------------------------------------------------------------------------

# Order types that this adapter can translate to MT5 native requests.
# Anything outside this set must be rejected before hitting the bridge.
SUPPORTED_ORDER_TYPES: frozenset[OrderType] = frozenset({
    OrderType.MARKET,
    OrderType.LIMIT,
    OrderType.STOP_MARKET,
    OrderType.STOP_LIMIT,
})

# Time-in-force values that this adapter maps correctly to MT5 semantics.
# GTD, AT_THE_OPEN, AT_THE_CLOSE, ON_CLOSE, etc. are not supported.
SUPPORTED_TIME_IN_FORCE: frozenset[TimeInForce] = frozenset({
    TimeInForce.GTC,
    TimeInForce.DAY,
    TimeInForce.FOK,
    TimeInForce.IOC,
})


def validate_order_pre_venue(order_type: OrderType, time_in_force: TimeInForce) -> None:
    """
    Raise ``ValueError`` if ``order_type`` or ``time_in_force`` is not
    supported by this adapter.  Call this before any bridge interaction so
    the execution client can emit ``OrderRejected`` without touching MT5.

    Parameters
    ----------
    order_type : OrderType
    time_in_force : TimeInForce

    Raises
    ------
    ValueError
        If the order type or TIF is not in the supported set.
    """
    if order_type not in SUPPORTED_ORDER_TYPES:
        supported = ", ".join(sorted(t.name for t in SUPPORTED_ORDER_TYPES))
        raise ValueError(
            f"MT5 adapter does not support OrderType.{order_type.name}. "
            f"Supported types: {supported}."
        )
    if time_in_force not in SUPPORTED_TIME_IN_FORCE:
        supported = ", ".join(sorted(t.name for t in SUPPORTED_TIME_IN_FORCE))
        raise ValueError(
            f"MT5 adapter does not support TimeInForce.{time_in_force.name}. "
            f"Supported values: {supported}."
        )


def map_order_type_and_action(order_type: OrderType, side: OrderSide) -> tuple[int, int]:
    if order_type == OrderType.MARKET:
        action = TRADE_ACTION_DEAL
        mt5_type = ORDER_TYPE_BUY if side == OrderSide.BUY else ORDER_TYPE_SELL
    elif order_type == OrderType.LIMIT:
        action = TRADE_ACTION_PENDING
        mt5_type = ORDER_TYPE_BUY_LIMIT if side == OrderSide.BUY else ORDER_TYPE_SELL_LIMIT
    elif order_type == OrderType.STOP_MARKET:
        action = TRADE_ACTION_PENDING
        mt5_type = ORDER_TYPE_BUY_STOP if side == OrderSide.BUY else ORDER_TYPE_SELL_STOP
    elif order_type == OrderType.STOP_LIMIT:
        action = TRADE_ACTION_PENDING
        mt5_type = ORDER_TYPE_BUY_STOP_LIMIT if side == OrderSide.BUY else ORDER_TYPE_SELL_STOP_LIMIT
    else:
        raise ValueError(f"Unsupported OrderType: {order_type}")
    return action, mt5_type

MAP_ORDER_STATUS = {
    0: OrderStatus.SUBMITTED,  # ORDER_STATE_STARTED
    1: OrderStatus.ACCEPTED,   # ORDER_STATE_PLACED
    2: OrderStatus.CANCELED,   # ORDER_STATE_CANCELED
    3: OrderStatus.FILLED,     # ORDER_STATE_PARTIAL
    4: OrderStatus.FILLED,     # ORDER_STATE_FILLED
    5: OrderStatus.REJECTED,   # ORDER_STATE_REJECTED
    6: OrderStatus.EXPIRED,    # ORDER_STATE_EXPIRED
    7: OrderStatus.ACCEPTED,   # ORDER_STATE_REQUEST_ADD
    8: OrderStatus.ACCEPTED,   # ORDER_STATE_REQUEST_MODIFY
    9: OrderStatus.ACCEPTED,   # ORDER_STATE_REQUEST_CANCEL
}

def map_filling_type(time_in_force: TimeInForce) -> int:
    if time_in_force == TimeInForce.FOK:
        return ORDER_FILLING_FOK
    elif time_in_force == TimeInForce.IOC:
        return ORDER_FILLING_IOC
    return ORDER_FILLING_RETURN

def timestring_to_timestamp(timestring: str) -> pd.Timestamp:
    dt, tz = timestring.rsplit(" ", 1)
    return pd.Timestamp(dt, tz=tz)

from nautilus_trader.model.enums import TriggerType

MAP_TRIGGER_METHOD: dict[int, int] = {
    TriggerType.DEFAULT: 0,
    TriggerType.LAST_PRICE: 2,
    TriggerType.BID_ASK: 4,
}

MT5_ORDER_TYPE_TO_ORDER_SIDE: dict[int, OrderSide] = {
    ORDER_TYPE_BUY: OrderSide.BUY,
    ORDER_TYPE_BUY_LIMIT: OrderSide.BUY,
    ORDER_TYPE_BUY_STOP: OrderSide.BUY,
    ORDER_TYPE_BUY_STOP_LIMIT: OrderSide.BUY,
    ORDER_TYPE_SELL: OrderSide.SELL,
    ORDER_TYPE_SELL_LIMIT: OrderSide.SELL,
    ORDER_TYPE_SELL_STOP: OrderSide.SELL,
    ORDER_TYPE_SELL_STOP_LIMIT: OrderSide.SELL,
}

MT5_ORDER_TYPE_TO_ORDER_TYPE: dict[int, OrderType] = {
    ORDER_TYPE_BUY: OrderType.MARKET,
    ORDER_TYPE_SELL: OrderType.MARKET,
    ORDER_TYPE_BUY_LIMIT: OrderType.LIMIT,
    ORDER_TYPE_SELL_LIMIT: OrderType.LIMIT,
    ORDER_TYPE_BUY_STOP: OrderType.STOP_MARKET,
    ORDER_TYPE_SELL_STOP: OrderType.STOP_MARKET,
    ORDER_TYPE_BUY_STOP_LIMIT: OrderType.STOP_LIMIT,
    ORDER_TYPE_SELL_STOP_LIMIT: OrderType.STOP_LIMIT,
}
