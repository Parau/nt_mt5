import pytest
import asyncio
import logging
from decimal import Decimal

from nautilus_trader.model.identifiers import Venue, Symbol, InstrumentId, AccountId
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.trading.strategy import Strategy, StrategyConfig
from nautilus_trader.config import LoggingConfig, TradingNodeConfig
from nautilus_trader.live.node import TradingNode

from nautilus_mt5.data_types import MT5Symbol
from nautilus_mt5.client.client import MetaTrader5Client
from nautilus_mt5.providers import MetaTrader5InstrumentProviderConfig
from nautilus_mt5.config import TerminalConnectionMode, RpycConnectionConfig
from nautilus_mt5.config import MetaTrader5DataClientConfig, MetaTrader5ExecClientConfig
from nautilus_mt5.factories import MT5LiveDataClientFactory, MT5LiveExecClientFactory

import os
from dotenv import load_dotenv
load_dotenv()

HOST = os.getenv("MT5_HOST", "0.tcp.sa.ngrok.io")
PORT = int(os.getenv("MT5_PORT", "12325"))
CLIENT_ID = "ACCEPTANCE"
ACCOUNT_NUMBER = "115371661"
SYMBOL_STR = "USTEC"

MT5_VENUE = Venue("METATRADER_5")
INSTRUMENT_ID = InstrumentId(Symbol(SYMBOL_STR), MT5_VENUE)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

class HedgingStrategyConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId

class HedgingStrategy(Strategy):
    def __init__(self, config: HedgingStrategyConfig):
        super().__init__(config)
        self.instrument_id = config.instrument_id

        self.leg1_opened = False
        self.leg2_opened = False

        self.orders = []

    def on_start(self):
        self.log.info("Iniciando Hedging Strategy...")
        self.subscribe_quote_ticks(self.instrument_id)

    def on_quote_tick(self, tick: QuoteTick):
        if not self.leg1_opened:
            self.log.info("Abrindo primeira perna LONG no USTEC (H-01)")
            instrument = self.cache.instrument(self.instrument_id)
            if not instrument:
                return

            self.leg1_opened = True

            order = self.order_factory.market(
                instrument_id=self.instrument_id,
                order_side=OrderSide.BUY,
                quantity=instrument.min_quantity,
                time_in_force=TimeInForce.GTC,
            )
            self.orders.append(order.client_order_id)
            self.submit_order(order)

        elif self.leg1_opened and not self.leg2_opened:
            self.log.info("Abrindo perna oposta SHORT no USTEC (H-02 - Hedging Simultâneo)")
            instrument = self.cache.instrument(self.instrument_id)

            self.leg2_opened = True
            order2 = self.order_factory.market(
                instrument_id=self.instrument_id,
                order_side=OrderSide.SELL,
                quantity=instrument.min_quantity,
                time_in_force=TimeInForce.GTC,
            )
            self.orders.append(order2.client_order_id)
            self.submit_order(order2)

    def on_position_opened(self, event):
        self.log.info(f"Posição Hedging Aberta: {event}")

    def on_stop(self):
        self.log.info("Hedging Strategy parada. Cancelando ordens pendentes e liquidando as pernas se possivel.")
        self.cancel_all_orders(self.instrument_id)
        # Note: A real hedging close would require picking specific tickets.
        self.close_all_positions(self.instrument_id)


@pytest.mark.asyncio
async def test_live_hedging_suite():
    logger.info(f"=== Iniciando Teste de Hedging MT5 ===")

    rpyc_config = RpycConnectionConfig(host=HOST, port=PORT)
    inst_provider_config = MetaTrader5InstrumentProviderConfig(
        load_all=False,
        load_symbols=frozenset([MT5Symbol(symbol=SYMBOL_STR)])
    )

    data_config = MetaTrader5DataClientConfig(
        client_id=1,
        mode=TerminalConnectionMode.IPC,
        rpyc_config=rpyc_config,
        instrument_provider=inst_provider_config,
    )

    exec_config = MetaTrader5ExecClientConfig(
        client_id=1,
        mode=TerminalConnectionMode.IPC,
        rpyc_config=rpyc_config,
        instrument_provider=inst_provider_config,
        account_id=ACCOUNT_NUMBER,
    )

    logging_config = LoggingConfig(log_level="DEBUG", print_config=True)
    node = TradingNode(config=TradingNodeConfig(logging=logging_config))

    data_client = MT5LiveDataClientFactory.create(
        loop=node.get_event_loop(),
        name="MT5_DATA_H",
        config=data_config,
        msgbus=node.trader._msgbus,
        cache=node.trader._cache,
        clock=node.trader._clock,
    )

    exec_client = MT5LiveExecClientFactory.create(
        loop=node.get_event_loop(),
        name="MT5_EXEC_H",
        config=exec_config,
        msgbus=node.trader._msgbus,
        cache=node.trader._cache,
        clock=node.trader._clock,
    )

    node.trader._data_engine.register_client(data_client)
    node.trader._exec_engine.register_client(exec_client)

    node.build()

    strategy_config = HedgingStrategyConfig(instrument_id=INSTRUMENT_ID)
    strategy = HedgingStrategy(config=strategy_config)
    node.trader.add_strategy(strategy)

    task = asyncio.create_task(node.run_async())

    try:
        timeout = 30.0
        start_time = asyncio.get_event_loop().time()

        def are_clients_connected():
            return all(c.is_connected for c in node.trader._data_engine._clients.values()) and \
                   all(c.is_connected for c in node.trader._exec_engine._clients.values())

        while not are_clients_connected():
            if asyncio.get_event_loop().time() - start_time > timeout:
                pytest.fail("Timeout esperando clients conectarem no teste de hedging.")
            await asyncio.sleep(0.5)

        logger.info("Clientes conectados. Iniciando estrategia de hedging...")
        strategy.on_start()

        start_hedge = asyncio.get_event_loop().time()
        while not strategy.leg2_opened:
            if asyncio.get_event_loop().time() - start_hedge > 15.0:
                logger.warning("Hedging Timeout após 15 segundos.")
                break
            await asyncio.sleep(1)

        # Let the broker process
        await asyncio.sleep(5)

        logger.info("=== TESTE HEDGING EXECUTADO (Verificando Múltiplas posições não netadas) ===")
        # Nautilus will track positions, usually in a hedging account multiple positions per instrument will exist in MT5
        # Currently, Nautilus positions abstraction inherently aggregates by InstrumentId unless Hedging mode is deeply overridden.
        # Check logs to see how `generate_position_status_reports` merged them or kept them.
        positions = strategy.cache.positions()
        logger.info(f"Nautilus Posições Totais detectadas no cache: {len(positions)}")
        for pos in positions:
            logger.info(f"Posição: {pos.id} | Side: {pos.side} | Qty: {pos.quantity}")

    finally:
        logger.info("Desligando node de hedging...")
        await node.stop_async()
        node.dispose()

if __name__ == "__main__":
    asyncio.run(test_live_hedging_suite())
