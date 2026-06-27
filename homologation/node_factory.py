"""Build a TradingNode wired to the MT5 adapter via EXTERNAL_RPYC."""
from __future__ import annotations

from nautilus_trader.config import LiveDataEngineConfig, LoggingConfig, RoutingConfig, TradingNodeConfig
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue

from nautilus_mt5 import TICKMILL_DEMO_PROFILE
from nautilus_mt5.client.types import MT5TerminalAccessMode
from nautilus_mt5.config import (
    ExternalRPyCTerminalConfig,
    FeedGatewayConfig,
    MetaTrader5DataClientConfig,
    MetaTrader5ExecClientConfig,
    MetaTrader5InstrumentProviderConfig,
)
from nautilus_mt5.data_types import MT5Symbol
from nautilus_mt5.factories import MT5LiveDataClientFactory, MT5LiveExecClientFactory

from homologation.config import HomologationConfig

_VENUE = Venue("METATRADER_5")


def instrument_id(symbol: str) -> InstrumentId:
    return InstrumentId(Symbol(symbol), _VENUE)


def build_trading_node(cfg: HomologationConfig, trader_id: str = "HOMOLOG-001") -> TradingNode:
    external_rpyc = ExternalRPyCTerminalConfig(host=cfg.host, port=cfg.port, keep_alive=True)
    instrument_provider = MetaTrader5InstrumentProviderConfig(
        load_symbols=frozenset([MT5Symbol(symbol=cfg.symbol, broker=cfg.broker)]),
    )

    feed_config = FeedGatewayConfig(
        enabled=cfg.feed_enabled,
        host=cfg.feed_host,
        port=cfg.feed_port,
        path=cfg.feed_path,
        hello_timeout_secs=cfg.feed_hello_timeout_secs,
    )

    config_node = TradingNodeConfig(
        trader_id=trader_id,
        logging=LoggingConfig(log_level="INFO"),
        data_clients={
            "MT5": MetaTrader5DataClientConfig(
                client_id=1,
                terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
                external_rpyc=external_rpyc,
                instrument_provider=instrument_provider,
                venue_profile=TICKMILL_DEMO_PROFILE,
                feed=feed_config,
            ),
        },
        exec_clients={
            "MT5": MetaTrader5ExecClientConfig(
                client_id=1,
                account_id=cfg.account_number,
                terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
                external_rpyc=external_rpyc,
                instrument_provider=instrument_provider,
                routing=RoutingConfig(default=True),
                cancel_on_stop=True,
                close_on_stop=False,
            ),
        },
        data_engine=LiveDataEngineConfig(
            time_bars_timestamp_on_close=False,
            validate_data_sequence=True,
        ),
    )

    node = TradingNode(config=config_node)
    node.add_data_client_factory("MT5", MT5LiveDataClientFactory)
    node.add_exec_client_factory("MT5", MT5LiveExecClientFactory)
    node.build()
    return node
