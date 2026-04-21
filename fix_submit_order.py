import re
with open("nautilus_mt5/execution.py", "r") as f:
    content = f.read()

# Fix the calling of `_transform_order_to_mt5_order(command.order)` to include instrument
content = re.sub(
    r'mt5_order: MT5Order = self\._transform_order_to_mt5_order\(command\.order\)',
    r'''instrument = self._cache.instrument(command.order.instrument_id)
            mt5_order: MT5Order = self._transform_order_to_mt5_order(command.order, instrument)''',
    content
)

content = re.sub(
    r'mt5_order = self\._transform_order_to_mt5_order\(order\)',
    r'''instrument = self._cache.instrument(order.instrument_id)
                mt5_order = self._transform_order_to_mt5_order(order, instrument)''',
    content
)

with open("nautilus_mt5/execution.py", "w") as f:
    f.write(content)
