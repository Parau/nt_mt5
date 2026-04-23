import os

from nautilus_trader.config import LiveDataEngineConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.config import RoutingConfig
from nautilus_trader.config import TradingNodeConfig
from nautilus_trader.examples.strategies.subscribe import SubscribeStrategy
from nautilus_trader.examples.strategies.subscribe import SubscribeStrategyConfig
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.book import OrderBook
from nautilus_trader.model.data import QuoteTick, Bar, BarType, BarSpecification
from nautilus_trader.model.enums import AggregationSource, BarAggregation, PriceType

from nautilus_mt5.client.types import MT5TerminalAccessMode
from nautilus_mt5.constants import MT5_VENUE
from nautilus_mt5.data_types import MT5Symbol
from nautilus_mt5.config import (
    ExternalRPyCTerminalConfig,
    MetaTrader5DataClientConfig,
    MetaTrader5ExecClientConfig,
    MetaTrader5InstrumentProviderConfig,
)
from nautilus_mt5.factories import MT5LiveDataClientFactory, MT5LiveExecClientFactory

from dotenv import load_dotenv

load_dotenv()

# Use an already running gateway
EXTERNAL_HOST = os.environ.get("MT5_HOST", "localhost")
EXTERNAL_PORT = int(os.environ.get("MT5_PORT", 18812))

external_rpyc = ExternalRPyCTerminalConfig(
    host=EXTERNAL_HOST,
    port=EXTERNAL_PORT,
)

BROKER_SERVER = os.environ.get("MT5_SERVER", "MetaQuotes-Demo")
mt5_symbols = [
    MT5Symbol(symbol="EURUSD", broker=BROKER_SERVER),
]

instrument_provider = MetaTrader5InstrumentProviderConfig(
    load_symbols=frozenset(mt5_symbols),
)

config_node = TradingNodeConfig(
    trader_id="TESTER-EXTERNAL",
    logging=LoggingConfig(log_level="INFO"),
    data_clients={
        "MT5": MetaTrader5DataClientConfig(
            client_id=1,
            terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
            external_rpyc=external_rpyc,
            instrument_provider=instrument_provider,
        ),
    },
    exec_clients={
        "MT5": MetaTrader5ExecClientConfig(
            client_id=1,
            account_id=os.environ.get("MT5_ACCOUNT_NUMBER"),
            terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
            external_rpyc=external_rpyc,
            instrument_provider=instrument_provider,
            routing=RoutingConfig(
                default=True,
            ),
        ),
    },
    data_engine=LiveDataEngineConfig(
        time_bars_timestamp_on_close=False,
        validate_data_sequence=True,
    ),
)

node = TradingNode(config=config_node)

# Register client factories with the node
node.add_data_client_factory("MT5", MT5LiveDataClientFactory)
node.add_exec_client_factory("MT5", MT5LiveExecClientFactory)

node.build()

if __name__ == "__main__":
    print(f"Connecting to external MT5 RPyC gateway at {EXTERNAL_HOST}:{EXTERNAL_PORT}...")
    try:
        node.run()
    finally:
        node.dispose()
