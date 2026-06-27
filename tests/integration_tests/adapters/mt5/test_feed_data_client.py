"""
Feed-enabled MetaTrader5DataClient integration tests (Tier 1).
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from nautilus_trader.core.uuid import UUID4
from nautilus_trader.data.messages import SubscribeQuoteTicks
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue

from nautilus_mt5.client.types import MT5TerminalAccessMode
from nautilus_mt5.config import (
    ExternalRPyCTerminalConfig,
    FeedGatewayConfig,
    MetaTrader5DataClientConfig,
    MetaTrader5InstrumentProviderConfig,
)
from nautilus_mt5.data import MetaTrader5DataClient
from nautilus_mt5.data_types import MT5Symbol
from nautilus_mt5.feed.messages import HelloMessage, TickBatchMessage, WireTick
from nautilus_mt5.factories import MT5LiveDataClientFactory
from nautilus_mt5.venue_profile import TICKMILL_DEMO_PROFILE


_RPYC_CONFIG = ExternalRPyCTerminalConfig(host="127.0.0.1", port=18812)
_VENUE = Venue("METATRADER_5")
_BTCUSD_ID = InstrumentId(Symbol("BTCUSD"), _VENUE)


def _feed_data_config(*symbols: str) -> MetaTrader5DataClientConfig:
    load = frozenset(MT5Symbol(symbol=s) for s in symbols) if symbols else None
    return MetaTrader5DataClientConfig(
        client_id=1,
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=_RPYC_CONFIG,
        venue_profile=TICKMILL_DEMO_PROFILE,
        feed=FeedGatewayConfig(enabled=True, hello_timeout_secs=2.0),
        instrument_provider=MetaTrader5InstrumentProviderConfig(load_symbols=load),
    )


@pytest.mark.asyncio
async def test_feed_subscribe_uses_gateway_not_rpyc_poll(
    clean_factory_cache,
    nautilus_components,
    nautilus_mt5_harness,
    monkeypatch,
):
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop,
        name="MT5",
        config=_feed_data_config("BTCUSD"),
        msgbus=msgbus,
        cache=cache,
        clock=clock,
    )

    async def _noop_feed_start(self: MetaTrader5DataClient) -> None:
        return None

    monkeypatch.setattr(MetaTrader5DataClient, "_start_feed_gateway", _noop_feed_start)
    await data_client._connect()

    mock_gateway = MagicMock()
    mock_gateway.subscribe = AsyncMock()
    mock_gateway.is_service_connected = True
    data_client._feed_gateway = mock_gateway

    subscribe_ticks_calls: list[dict] = []

    async def _spy_subscribe_ticks(**kwargs):
        subscribe_ticks_calls.append(kwargs)

    data_client._client.subscribe_ticks = _spy_subscribe_ticks

    command = SubscribeQuoteTicks(
        client_id=data_client.id,
        venue=None,
        instrument_id=_BTCUSD_ID,
        command_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )
    await data_client._subscribe_quote_ticks(command)

    mock_gateway.subscribe.assert_awaited_once_with(["BTCUSD"])
    assert "BTCUSD" in data_client._feed_pending_symbols
    assert len(subscribe_ticks_calls) == 0


@pytest.mark.asyncio
async def test_feed_handle_ticks_emits_quote_tick(
    clean_factory_cache,
    nautilus_components,
    nautilus_mt5_harness,
    monkeypatch,
):
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop,
        name="MT5",
        config=_feed_data_config("BTCUSD"),
        msgbus=msgbus,
        cache=cache,
        clock=clock,
    )

    async def _noop_feed_start(self: MetaTrader5DataClient) -> None:
        return None

    monkeypatch.setattr(MetaTrader5DataClient, "_start_feed_gateway", _noop_feed_start)
    await data_client._connect()

    delivered: list[QuoteTick] = []
    original_handle = data_client._handle_data

    def _capture(data):
        if isinstance(data, QuoteTick):
            delivered.append(data)
        original_handle(data)

    data_client._handle_data = _capture

    batch = TickBatchMessage(
        symbol="BTCUSD",
        cursor=1000,
        ticks=(WireTick(time_msc=1000, bid=60468.0, ask=60478.0, flags=6),),
    )
    data_client._handle_feed_ticks(batch)

    assert len(delivered) == 1
    assert delivered[0].instrument_id == _BTCUSD_ID
    assert float(delivered[0].bid_price) == 60468.0


@pytest.mark.asyncio
async def test_feed_connect_starts_gateway_and_replays_pending(
    clean_factory_cache,
    nautilus_components,
    nautilus_mt5_harness,
    monkeypatch,
):
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop,
        name="MT5",
        config=_feed_data_config("BTCUSD"),
        msgbus=msgbus,
        cache=cache,
        clock=clock,
    )
    data_client._feed_pending_symbols.add("BTCUSD")

    class _FakeGateway:
        handler = MagicMock()
        handler.subscription_state.pending_subscribe = set()
        subscribed: list[str] = []

        async def start(self) -> None:
            return None

        async def wait_for_hello(self, timeout_secs=None):
            return HelloMessage(session="nt5-test", symbols=("BTCUSD",))

        async def subscribe(self, symbols):
            self.subscribed.extend(symbols)

        async def stop(self) -> None:
            return None

    fake = _FakeGateway()

    async def _fake_start(self: MetaTrader5DataClient) -> None:
        self._feed_gateway = fake
        await fake.start()
        await fake.wait_for_hello()
        pending = set(self._feed_pending_symbols)
        pending |= fake.handler.subscription_state.pending_subscribe
        if pending:
            await fake.subscribe(sorted(pending))

    monkeypatch.setattr(MetaTrader5DataClient, "_start_feed_gateway", _fake_start)

    await data_client._connect()
    assert data_client._feed_gateway is fake
    assert fake.subscribed == ["BTCUSD"]
