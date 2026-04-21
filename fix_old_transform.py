import re

with open("nautilus_mt5/execution.py", "r") as f:
    content = f.read()

# I noticed earlier that my attempt to replace `_transform_order_to_mt5_order` silently failed or was undone.
# Let's replace it robustly now since it still has Interactive Brokers comments and IB fields like `totalQuantity`.

new_transform = """
    def _transform_order_to_mt5_order(
        self, order: Order
    ) -> MT5Order:
        mt5_order = MT5Order()

        details = self.instrument_provider.symbol_details.get(order.instrument_id.value)
        if not details:
            raise ValueError(f"Instrument {order.instrument_id.value} not found in provider.")

        mt5_order.symbol = details.symbol.symbol if details.symbol else order.instrument_id.symbol.value
        mt5_order.volume_initial = float(order.quantity.as_double())
        mt5_order.account = self.account_id.get_id()
        mt5_order.orderRef = order.client_order_id.value

        if order.order_side == OrderSide.BUY:
            if order.order_type == OrderType.MARKET:
                mt5_order.type = 0 # ORDER_TYPE_BUY
            elif order.order_type == OrderType.LIMIT:
                mt5_order.type = 2 # ORDER_TYPE_BUY_LIMIT
            elif order.order_type == OrderType.STOP_MARKET:
                mt5_order.type = 4 # ORDER_TYPE_BUY_STOP
            elif order.order_type == OrderType.STOP_LIMIT:
                mt5_order.type = 6 # ORDER_TYPE_BUY_STOP_LIMIT
        else:
            if order.order_type == OrderType.MARKET:
                mt5_order.type = 1 # ORDER_TYPE_SELL
            elif order.order_type == OrderType.LIMIT:
                mt5_order.type = 3 # ORDER_TYPE_SELL_LIMIT
            elif order.order_type == OrderType.STOP_MARKET:
                mt5_order.type = 5 # ORDER_TYPE_SELL_STOP
            elif order.order_type == OrderType.STOP_LIMIT:
                mt5_order.type = 7 # ORDER_TYPE_SELL_STOP_LIMIT

        if getattr(order, "price", None):
            mt5_order.price_open = float(order.price.as_double())

        if getattr(order, "trigger_price", None):
            mt5_order.price_stoplimit = float(order.trigger_price.as_double())

        # mapping time in force
        if order.time_in_force == TimeInForce.GTC:
            mt5_order.type_time = 0 # ORDER_TIME_GTC
        elif order.time_in_force == TimeInForce.DAY:
            mt5_order.type_time = 1 # ORDER_TIME_DAY
        elif order.time_in_force == TimeInForce.FOK:
            mt5_order.type_filling = 0 # ORDER_FILLING_FOK
        elif order.time_in_force == TimeInForce.IOC:
            mt5_order.type_filling = 1 # ORDER_FILLING_IOC

        # Add basic action for compatibility with some downstream code logic although bridge translates it
        return mt5_order

    async def _submit_order(self, command: SubmitOrder) -> None:
"""

# We'll use a precise split to replace the old function.
start_idx = content.find("    def _transform_order_to_mt5_order(")
end_idx = content.find("    async def _submit_order(self, command: SubmitOrder) -> None:")

if start_idx != -1 and end_idx != -1:
    content = content[:start_idx] + new_transform + content[end_idx + len("    async def _submit_order(self, command: SubmitOrder) -> None:"):]

with open("nautilus_mt5/execution.py", "w") as f:
    f.write(content)
