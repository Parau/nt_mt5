from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_trader.model.identifiers import InstrumentId, Symbol, TraderId, Venue

from nautilus_mt5.client.client import MetaTrader5Client
from nautilus_mt5.client.tick_poll import is_quote_tick_subscription
from nautilus_mt5.client.types import MT5TerminalAccessMode, TerminalConnectionMode
from nautilus_mt5.data_types import MT5Symbol
from nautilus_mt5.metatrader5 import RpycConnectionConfig


_VENUE = Venue("METATRADER_5")
_BTCUSD_ID = InstrumentId(Symbol("BTCUSD"), _VENUE)


def _make_client() -> MetaTrader5Client:
    clock = LiveClock()
    msgbus = MessageBus(TraderId("TEST-1"), clock)
    cache = Cache()
    loop = asyncio.get_event_loop()
    client = MetaTrader5Client(
        loop=loop,
        msgbus=msgbus,
        cache=cache,
        clock=clock,
        connection_mode=TerminalConnectionMode.IPC,
        mt5_config={"rpyc": RpycConnectionConfig(), "ea": MagicMock()},
        client_id=1,
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
    )
    client._mt5_client["mt5"] = MagicMock()
    return client


def test_is_quote_tick_subscription() -> None:
    assert is_quote_tick_subscription("BidAsk")
    assert is_quote_tick_subscription("bid_ask")
    assert not is_quote_tick_subscription("AllLast")


@pytest.mark.asyncio
async def test_subscribe_ticks_bidask_skipped_when_live_feed_enabled() -> None:
    client = _make_client()
    client.live_quote_feed_enabled = True

    await client.subscribe_ticks(
        instrument_id=_BTCUSD_ID,
        symbol=MT5Symbol(symbol="BTCUSD"),
        tick_type="BidAsk",
        ignore_size=False,
    )

    assert client._subscriptions._req_id_to_name == {}


@pytest.mark.asyncio
async def test_subscribe_ticks_bidask_registers_when_live_feed_disabled() -> None:
    client = _make_client()
    client._mt5_client["mt5"].req_tick_by_tick_data = None
    client._mt5_client["mt5"].cancel_tick_by_tick_data = None

    await client.subscribe_ticks(
        instrument_id=_BTCUSD_ID,
        symbol=MT5Symbol(symbol="BTCUSD"),
        tick_type="BidAsk",
        ignore_size=False,
    )

    assert len(client._subscriptions._req_id_to_name) == 1


def test_should_poll_quote_ticks() -> None:
    client = _make_client()

    assert client._should_poll_quote_ticks("BidAsk") is True
    client.live_quote_feed_enabled = True
    assert client._should_poll_quote_ticks("BidAsk") is False
    assert client._should_poll_quote_ticks("AllLast") is True
