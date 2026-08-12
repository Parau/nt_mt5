"""
Feed-enabled MetaTrader5DataClient integration tests (Tier 1).
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from nautilus_trader.core.uuid import UUID4
from nautilus_trader.data.messages import SubscribeBars, SubscribeQuoteTicks, SubscribeTradeTicks
from nautilus_trader.model.data import Bar, BarAggregation, BarSpecification, BarType, QuoteTick, TradeTick
from nautilus_trader.model.enums import AggressorSide, AggregationSource, PriceType
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
from nautilus_mt5.feed.messages import BarMessage, HelloMessage, TickBatchMessage, WireBar, WireTick
from nautilus_mt5.factories import MT5LiveDataClientFactory
from nautilus_mt5.venue_profile import TICKMILL_DEMO_PROFILE, XP_B3_PROFILE


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

    data_client._feed_pending_symbols.add("BTCUSD")
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


def _xp_feed_data_config(*symbols: str) -> MetaTrader5DataClientConfig:
    load = frozenset(MT5Symbol(symbol=s) for s in symbols) if symbols else None
    return MetaTrader5DataClientConfig(
        client_id=1,
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=_RPYC_CONFIG,
        venue_profile=XP_B3_PROFILE,
        feed=FeedGatewayConfig(enabled=True, hello_timeout_secs=2.0),
        instrument_provider=MetaTrader5InstrumentProviderConfig(load_symbols=load),
    )


_WINQ26_ID = InstrumentId(Symbol("WINQ26"), _VENUE)


@pytest.mark.asyncio
async def test_feed_subscribe_trade_ticks_uses_gateway_not_rpyc(
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
        config=_xp_feed_data_config("WINQ26"),
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
    data_client._feed_gateway = mock_gateway

    subscribe_ticks_calls: list[dict] = []

    async def _spy_subscribe_ticks(**kwargs):
        subscribe_ticks_calls.append(kwargs)

    data_client._client.subscribe_ticks = _spy_subscribe_ticks

    command = SubscribeTradeTicks(
        client_id=data_client.id,
        venue=None,
        instrument_id=_WINQ26_ID,
        command_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )
    await data_client._subscribe_trade_ticks(command)

    mock_gateway.subscribe.assert_awaited_once_with(["WINQ26"])
    assert "WINQ26" in data_client._feed_trade_symbols
    assert "WINQ26" in data_client._feed_pending_symbols
    assert len(subscribe_ticks_calls) == 0


@pytest.mark.asyncio
async def test_feed_handle_trade_tick_xp_aggressor(
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
        config=_xp_feed_data_config("WINQ26"),
        msgbus=msgbus,
        cache=cache,
        clock=clock,
    )

    async def _noop_feed_start(self: MetaTrader5DataClient) -> None:
        return None

    monkeypatch.setattr(MetaTrader5DataClient, "_start_feed_gateway", _noop_feed_start)
    await data_client._connect()

    delivered: list[TradeTick] = []
    original_handle = data_client._handle_data

    def _capture(data):
        if isinstance(data, TradeTick):
            delivered.append(data)
        original_handle(data)

    data_client._handle_data = _capture

    data_client._feed_pending_symbols.add("WINQ26")
    batch = TickBatchMessage(
        symbol="WINQ26",
        cursor=1000,
        ticks=(
            WireTick(time_msc=1000, bid=0.0, ask=0.0, last=174115.0, volume=1, flags=1080),
            WireTick(time_msc=1001, bid=0.0, ask=0.0, last=174110.0, volume=2, flags=1112),
        ),
    )
    data_client._handle_feed_ticks(batch)

    assert len(delivered) == 2
    assert delivered[0].aggressor_side == AggressorSide.BUYER
    assert delivered[1].aggressor_side == AggressorSide.SELLER


@pytest.mark.asyncio
async def test_feed_trade_unsubscribe_keeps_quote_subscription(
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
    mock_gateway.unsubscribe = AsyncMock()
    mock_gateway.wait_for_symbols_absent = AsyncMock(
        return_value=HelloMessage(session="nt5-test", symbols=()),
    )
    mock_gateway.is_service_connected = True
    data_client._feed_gateway = mock_gateway

    quote_cmd = SubscribeQuoteTicks(
        client_id=data_client.id,
        venue=None,
        instrument_id=_BTCUSD_ID,
        command_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )
    trade_cmd = SubscribeTradeTicks(
        client_id=data_client.id,
        venue=None,
        instrument_id=_BTCUSD_ID,
        command_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )
    await data_client._subscribe_quote_ticks(quote_cmd)
    await data_client._subscribe_trade_ticks(trade_cmd)

    from nautilus_trader.data.messages import UnsubscribeTradeTicks

    unsub = UnsubscribeTradeTicks(
        client_id=data_client.id,
        venue=None,
        instrument_id=_BTCUSD_ID,
        command_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )
    await data_client._unsubscribe_trade_ticks(unsub)

    mock_gateway.unsubscribe.assert_not_awaited()
    assert "BTCUSD" in data_client._feed_quote_symbols
    assert "BTCUSD" not in data_client._feed_trade_symbols
    assert "BTCUSD" in data_client._feed_pending_symbols


@pytest.mark.asyncio
async def test_feed_enabled_sets_client_live_quote_feed_flag(
    clean_factory_cache,
    nautilus_components,
    nautilus_mt5_harness,
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

    assert data_client._client.live_quote_feed_enabled is True


_BTCUSD_M1 = BarType(
    _BTCUSD_ID,
    BarSpecification(1, BarAggregation.MINUTE, PriceType.LAST),
    AggregationSource.EXTERNAL,
)


@pytest.mark.asyncio
async def test_feed_subscribe_bars_uses_gateway(
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
    mock_gateway.subscribe_bars = AsyncMock()
    data_client._feed_gateway = mock_gateway

    cmd = SubscribeBars(
        bar_type=_BTCUSD_M1,
        client_id=data_client.id,
        venue=None,
        command_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )
    await data_client._subscribe_bars(cmd)

    mock_gateway.subscribe_bars.assert_awaited_once_with(["BTCUSD"], "M1")


@pytest.mark.asyncio
async def test_feed_handle_bar_emits_bar(
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

    data_client._feed_bar_types[("BTCUSD", "M1")] = _BTCUSD_M1

    delivered: list[Bar] = []
    original_handle = data_client._handle_data

    def _capture(data):
        if isinstance(data, Bar):
            delivered.append(data)
        original_handle(data)

    data_client._handle_data = _capture

    msg = BarMessage(
        bar=WireBar(
            symbol="BTCUSD",
            timeframe="M1",
            time=1_700_000_000,
            open=60000.0,
            high=60100.0,
            low=59900.0,
            close=60050.0,
            tick_volume=10,
        ),
    )
    await data_client._handle_feed_event(msg)

    assert len(delivered) == 1
    assert delivered[0].bar_type == _BTCUSD_M1
    assert float(delivered[0].close) == 60050.0


# --- Feed subscription lifecycle (Issue #18 / T-LIFE-*) ---


@pytest.mark.asyncio
async def test_t_life_01_last_owner_sends_wire_unsubscribe(
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
    mock_gateway.unsubscribe = AsyncMock()
    mock_gateway.wait_for_symbols_absent = AsyncMock(
        return_value=HelloMessage(session="nt5", symbols=()),
    )
    mock_gateway.is_service_connected = True
    data_client._feed_gateway = mock_gateway

    # Seed sole trade ownership without relying on venue trade_ticks capability.
    data_client._feed_trade_symbols.add("BTCUSD")
    data_client._feed_pending_symbols.add("BTCUSD")

    from nautilus_trader.data.messages import UnsubscribeTradeTicks

    await data_client._unsubscribe_trade_ticks(
        UnsubscribeTradeTicks(
            client_id=data_client.id,
            venue=None,
            instrument_id=_BTCUSD_ID,
            command_id=UUID4(),
            ts_init=clock.timestamp_ns(),
        ),
    )

    mock_gateway.unsubscribe.assert_awaited_once_with(["BTCUSD"])
    mock_gateway.wait_for_symbols_absent.assert_awaited()
    assert "BTCUSD" not in data_client._feed_trade_symbols
    assert "BTCUSD" not in data_client._feed_pending_symbols


@pytest.mark.asyncio
async def test_t_life_03_disconnect_unsubscribes_before_stop(
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

    order: list[str] = []

    class _FakeGateway:
        is_service_connected = True
        handler = MagicMock()

        async def unsubscribe(self, symbols):
            order.append(f"unsubscribe:{','.join(symbols)}")

        async def wait_for_symbols_absent(self, symbols, timeout_secs=None):
            order.append(f"wait_absent:{','.join(sorted(symbols))}")
            return HelloMessage(session="nt5", symbols=())

        async def stop(self):
            order.append("stop")

    data_client._feed_gateway = _FakeGateway()
    data_client._feed_pending_symbols = {"ENQU26", "MNQU26"}

    await data_client._disconnect()

    assert order[0].startswith("unsubscribe:")
    assert set(order[0].split(":", 1)[1].split(",")) == {"ENQU26", "MNQU26"}
    assert order[1].startswith("wait_absent:")
    assert order[2] == "stop"
    assert data_client._feed_gateway is None


@pytest.mark.asyncio
async def test_t_life_04_disconnect_cleanup_failure_still_stops(
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

    class _FakeGateway:
        is_service_connected = True
        handler = MagicMock()
        stopped = False

        async def unsubscribe(self, symbols):
            return None

        async def wait_for_symbols_absent(self, symbols, timeout_secs=None):
            raise TimeoutError("no ack")

        async def stop(self):
            self.stopped = True

    fake = _FakeGateway()
    data_client._feed_gateway = fake
    data_client._feed_pending_symbols = {"ENQU26"}

    await data_client._disconnect()

    assert fake.stopped is True
    assert data_client._feed_gateway is None


@pytest.mark.asyncio
async def test_t_life_05_orphan_hello_is_reconciled_on_startup(
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

    calls: list[str] = []

    class _FakeGateway:
        handler = MagicMock()
        handler.subscription_state.pending_subscribe = set()
        handler.subscription_state.pending_bar_subscribe = set()
        is_service_connected = True
        last_hello = None

        async def start(self):
            return None

        async def wait_for_hello(self, timeout_secs=None):
            return HelloMessage(session="nt5", symbols=("ENQU26",))

        async def unsubscribe(self, symbols):
            calls.append(f"unsubscribe:{list(symbols)}")

        async def wait_for_symbols_absent(self, symbols, timeout_secs=None):
            calls.append(f"wait_absent:{sorted(symbols)}")
            hello = HelloMessage(session="nt5-cleared", symbols=())
            self.last_hello = hello
            return hello

        async def subscribe(self, symbols):
            calls.append(f"subscribe:{list(symbols)}")

        async def subscribe_bars(self, symbols, timeframe):
            return None

        async def stop(self):
            return None

    fake = _FakeGateway()

    async def _fake_start(self: MetaTrader5DataClient) -> None:
        self._feed_gateway = fake
        self._feed_handler = fake.handler
        await fake.start()
        hello = await fake.wait_for_hello()
        await self._reconcile_orphan_feed_symbols(hello)
        pending = set(self._feed_pending_symbols)
        if pending:
            await fake.subscribe(sorted(pending))

    monkeypatch.setattr(MetaTrader5DataClient, "_start_feed_gateway", _fake_start)
    data_client._feed_pending_symbols.clear()
    await data_client._connect()

    assert calls == ["unsubscribe:['ENQU26']", "wait_absent:['ENQU26']"]
    assert not any(c.startswith("subscribe:") for c in calls)


@pytest.mark.asyncio
async def test_t_life_06_desired_symbol_not_orphaned_on_reconnect(
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
    mock_gateway.unsubscribe = AsyncMock()
    mock_gateway.wait_for_symbols_absent = AsyncMock()
    data_client._feed_gateway = mock_gateway
    data_client._feed_pending_symbols = {"ENQU26"}

    await data_client._reconcile_orphan_feed_symbols(
        HelloMessage(session="nt5", symbols=("ENQU26",)),
    )

    mock_gateway.unsubscribe.assert_not_awaited()
    mock_gateway.wait_for_symbols_absent.assert_not_awaited()


@pytest.mark.asyncio
async def test_t_life_07_hello_desired_plus_orphan_unsubscribes_only_orphan(
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
    mock_gateway.unsubscribe = AsyncMock()
    mock_gateway.wait_for_symbols_absent = AsyncMock(
        return_value=HelloMessage(session="nt5", symbols=("ENQU26",)),
    )
    data_client._feed_gateway = mock_gateway
    data_client._feed_pending_symbols = {"ENQU26"}

    await data_client._reconcile_orphan_feed_symbols(
        HelloMessage(session="nt5", symbols=("ENQU26", "MNQU26")),
    )

    mock_gateway.unsubscribe.assert_awaited_once_with(["MNQU26"])
    mock_gateway.wait_for_symbols_absent.assert_awaited()


@pytest.mark.asyncio
async def test_t_life_08_batch_without_local_ownership_is_ignored(
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

    delivered: list = []
    original = data_client._handle_data

    def _spy(data):
        delivered.append(data)
        return original(data)

    data_client._handle_data = _spy
    assert not data_client._feed_pending_symbols

    data_client._handle_feed_ticks(
        TickBatchMessage(
            symbol="ENQU26",
            cursor=1000,
            ticks=(WireTick(time_msc=1000, bid=1.0, ask=1.1, last=1.05, volume=1, flags=56),),
        ),
    )

    assert delivered == []


@pytest.mark.asyncio
async def test_t_life_09_batch_with_local_ownership_emits(
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
    original = data_client._handle_data

    def _spy(data):
        if isinstance(data, QuoteTick):
            delivered.append(data)
        return original(data)

    data_client._handle_data = _spy
    data_client._feed_pending_symbols.add("BTCUSD")

    data_client._handle_feed_ticks(
        TickBatchMessage(
            symbol="BTCUSD",
            cursor=1000,
            ticks=(WireTick(time_msc=1000, bid=10.0, ask=11.0, flags=6),),
        ),
    )

    assert len(delivered) == 1
