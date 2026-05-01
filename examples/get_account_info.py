import os
from nautilus_mt5.metatrader5 import MetaTrader5, RpycConnectionConfig

config = RpycConnectionConfig(
    host=os.environ.get("MT5_HOST", "127.0.0.1"),
    port=int(os.environ.get("MT5_PORT", 18812)),
)
client = MetaTrader5(config=config)
client.connect()
print(client.is_connected())

print(client.get_accounts())

client.disconnect()
