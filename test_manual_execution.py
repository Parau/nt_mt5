import asyncio
import logging
from decimal import Decimal
import uuid

from nautilus_trader.live.node import LiveNode
from nautilus_trader.config import LiveExecEngineConfig, LiveRiskEngineConfig
from nautilus_trader.model.identifiers import TraderId, InstrumentId, ClientId, AccountId, StrategyId, Venue
from nautilus_trader.model.objects import Quantity
from nautilus_trader.model.enums import OrderType, TimeInForce, OrderSide
from nautilus_trader.core.message import Event
from nautilus_trader.test_kit.providers import TestInstrumentProvider
from nautilus_trader.model.orders import MarketOrder
from nautilus_trader.model.identifiers import ClientOrderId
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.execution.messages import SubmitOrder

from nautilus_mt5.config import MetaTrader5ExecClientConfig
from nautilus_mt5.client.types import TerminalConnectionMode
from nautilus_mt5.metatrader5 import RpycConnectionConfig
from nautilus_mt5.execution import MetaTrader5ExecutionClient
from nautilus_mt5.client.client import MetaTrader5Client
from nautilus_mt5.providers import MetaTrader5InstrumentProvider
from nautilus_mt5.config import MetaTrader5InstrumentProviderConfig
from nautilus_mt5.data_types import MT5Symbol
from nautilus_trader.common import Environment

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Test")

async def main():
    rpyc_config = RpycConnectionConfig(
        host="0.tcp.sa.ngrok.io",
        port=18526,
    )

    exec_config = MetaTrader5ExecClientConfig(
        mode=TerminalConnectionMode.IPC,
        rpyc_config=rpyc_config,
    )

    client_id = ClientId("METATRADER_5")

    ustec = TestInstrumentProvider.equity()

    instrument_id = InstrumentId.from_str("USTEC.METATRADER_5")

    def mt5_exec_factory(msg_bus, cache, clock):
        mt5_client = MetaTrader5Client(
            loop=asyncio.get_event_loop(),
            msgbus=msg_bus,
            cache=cache,
            clock=clock,
            connection_mode=TerminalConnectionMode.IPC,
            mt5_config=exec_config,
        )

        instrument_provider_config = MetaTrader5InstrumentProviderConfig(
            load_symbols=frozenset({MT5Symbol("USTEC")})
        )
        instrument_provider = MetaTrader5InstrumentProvider(
            client=mt5_client,
            config=instrument_provider_config
        )

        return MetaTrader5ExecutionClient(
            loop=asyncio.get_event_loop(),
            client=mt5_client,
            account_id=AccountId("METATRADER_5-001"),
            msgbus=msg_bus,
            cache=cache,
            clock=clock,
            instrument_provider=instrument_provider,
            config=exec_config
        )

    node = (
        LiveNode.builder("EXEC-TEST", TraderId("EXEC-TEST"), Environment.SANDBOX)
        .with_risk_engine_config(LiveRiskEngineConfig(bypass=True))
        .with_exec_engine_config(LiveExecEngineConfig(reconciliation=True))
        .add_exec_client(
            client_id,
            mt5_exec_factory,
            exec_config
        )
        .build()
    )

    from nautilus_trader.model.instruments import Equity
    dummy_ustec = Equity(
        instrument_id=instrument_id,
        raw_symbol="USTEC",
        asset_class=ustec.asset_class,
        instrument_class=ustec.instrument_class,
        quote_currency=ustec.quote_currency,
        is_inverse=ustec.is_inverse,
        price_precision=2,
        price_increment=Decimal("0.25"),
        size_precision=1,
        size_increment=Decimal("0.1"),
        multiplier=Decimal("1"),
        lot_size=Decimal("1"),
        margin_init=Decimal("0"),
        margin_maint=Decimal("0"),
        maker_fee=Decimal("0"),
        taker_fee=Decimal("0"),
        activation_time=None,
        expiration_time=None,
    )
    node.cache.add_instrument(dummy_ustec)

    node.message_bus.subscribe(
        topic="*",
        handler=lambda msg: logger.info(f"MSG: {msg}")
    )

    logger.info("Starting Node...")

    run_task = asyncio.create_task(node.run())

    logger.info("Node starting. Wait for reconciliation...")
    await asyncio.sleep(5)

    orders = node.cache.orders()
    logger.info(f"Orders in cache: {len(orders)}")
    positions = node.cache.positions()
    logger.info(f"Positions in cache: {len(positions)}")

    client_order_id = ClientOrderId(str(uuid.uuid4()))
    order = MarketOrder(
        trader_id=TraderId("EXEC-TEST"),
        strategy_id=StrategyId("EXEC-TEST"),
        instrument_id=instrument_id,
        client_order_id=client_order_id,
        order_side=OrderSide.BUY,
        quantity=Quantity.from_str("0.1"),
        time_in_force=TimeInForce.GTC,
        init_id=UUID4(),
        ts_init=node.clock.timestamp_ns(),
    )

    logger.info("Submitting Market Order...")
    node.exec_engine.submit_order(order)

    await asyncio.sleep(10)

    orders = node.cache.orders()
    logger.info(f"Orders in cache after submit: {len(orders)}")
    positions = node.cache.positions()
    logger.info(f"Positions in cache after submit: {len(positions)}")

    logger.info("Stopping...")
    await node.stop()
    node.dispose()

if __name__ == "__main__":
    asyncio.run(main())
