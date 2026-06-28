"""Hold bar subscription open until killed — validates Service v1.04 onDisconnect cleanup."""
from __future__ import annotations

import asyncio
import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.data.messages import SubscribeBars, SubscribeQuoteTicks
from nautilus_trader.model.identifiers import InstrumentId, Symbol, TraderId, Venue

from nautilus_mt5 import TICKMILL_DEMO_PROFILE
from nautilus_mt5.client.types import MT5TerminalAccessMode
from nautilus_mt5.config import (
    ExternalRPyCTerminalConfig,
    FeedGatewayConfig,
    MetaTrader5DataClientConfig,
    MetaTrader5InstrumentProviderConfig,
)
from nautilus_mt5.data_types import MT5Symbol
from nautilus_mt5.factories import MT5LiveDataClientFactory
from homologation.support.clients import reset_mt5_client_cache

_VENUE = Venue("METATRADER_5")
_HOLD_SECS = int(os.environ.get("V104_HOLD_SECS", "600"))


async def main() -> int:
    os.environ.setdefault("MT5_FEED_ENABLED", "1")
    host = os.environ.get("MT5_HOST", "127.0.0.1")
    port = int(os.environ.get("MT5_PORT", "18812"))
    symbol = os.environ.get("MT5_SYMBOL", "BTCUSD")
    broker = os.environ.get("MT5_BROKER", "Tickmill-Demo")
    feed_port = int(os.environ.get("MT5_FEED_PORT", "8765"))

    print("=" * 64)
    print("  v1.04 BAR DISCONNECT HOLD")
    print(f"  WS gateway : 0.0.0.0:{feed_port}/mt5-feed")
    print(f"  Symbol     : {symbol} M1 bars")
    print(f"  Hold       : {_HOLD_SECS}s (kill this process after MT5 shows subscribed bars)")
    print("=" * 64)
    print(f"  PID        : {os.getpid()}")
    print("  >>> Watch MT5 journal for: subscribed bars BTCUSD:M1")
    print("  >>> Then run taskkill on the PID listening on port 8765 (see chat)")
    print("=" * 64, flush=True)

    reset_mt5_client_cache()
    rpyc_cfg = ExternalRPyCTerminalConfig(host=host, port=port, keep_alive=True)
    provider = MetaTrader5InstrumentProviderConfig(
        load_symbols=frozenset({MT5Symbol(symbol=symbol, broker=broker)}),
    )
    feed = FeedGatewayConfig(
        enabled=True,
        host="0.0.0.0",
        port=feed_port,
        path="/mt5-feed",
        hello_timeout_secs=30.0,
    )
    config = MetaTrader5DataClientConfig(
        client_id=9,
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=rpyc_cfg,
        instrument_provider=provider,
        venue_profile=TICKMILL_DEMO_PROFILE,
        feed=feed,
    )
    loop = asyncio.get_running_loop()
    clock = LiveClock()
    msgbus = MessageBus(TraderId("V104-HOLD"), clock)
    cache = Cache()
    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=config, msgbus=msgbus, cache=cache, clock=clock,
    )

    await data_client._connect()
    inst_id = InstrumentId(Symbol(symbol), _VENUE)
    if cache.instrument(inst_id) is None:
        print("FAIL: instrument not in cache", flush=True)
        return 1

    await data_client._subscribe_quote_ticks(
        SubscribeQuoteTicks(
            instrument_id=inst_id,
            client_id=data_client.id,
            venue=_VENUE,
            command_id=UUID4(),
            ts_init=clock.timestamp_ns(),
        )
    )
    from nautilus_trader.model.data import BarAggregation, BarSpecification, BarType
    from nautilus_trader.model.enums import AggregationSource, PriceType
    from nautilus_trader.data.messages import SubscribeBars

    bar_type = BarType(
        inst_id,
        BarSpecification(1, BarAggregation.MINUTE, PriceType.LAST),
        AggregationSource.EXTERNAL,
    )
    await data_client._subscribe_bars(
        SubscribeBars(
            bar_type=bar_type,
            client_id=data_client.id,
            venue=_VENUE,
            command_id=UUID4(),
            ts_init=clock.timestamp_ns(),
        )
    )
    print("Adapter sent subscribe + subscribe_bars — waiting (no unsubscribe until kill)", flush=True)

    deadline = time.monotonic() + _HOLD_SECS
    while time.monotonic() < deadline:
        await asyncio.sleep(1.0)

    print("Hold timeout reached — exiting cleanly", flush=True)
    await data_client._disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
