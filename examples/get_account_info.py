from nautilus_mt5.metatrader5 import MetaTrader5, RpycConnectionConfig

config = RpycConnectionConfig(host="localhost", port=18812)
client = MetaTrader5(config=config)
client.connect()
print(client.is_connected())

print(client.get_accounts())

client.disconnect()
