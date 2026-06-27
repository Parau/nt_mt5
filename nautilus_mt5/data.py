import asyncio
from operator import attrgetter

import pandas as pd

from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock
from nautilus_trader.common.component import MessageBus
from nautilus_trader.live.data_client import LiveMarketDataClient
from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.identifiers import ClientId
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import Symbol

from nautilus_mt5.client.client import MetaTrader5Client
from nautilus_mt5.constants import MT5_VENUE
from nautilus_mt5.data_types import MT5Symbol
from nautilus_mt5.config import MetaTrader5DataClientConfig
from nautilus_mt5.feed.config import FeedGatewayConfig
from nautilus_mt5.feed.converter import wire_tick_to_quote_tick
from nautilus_mt5.feed.gateway import InboundFeedGateway
from nautilus_mt5.feed.messages import (
    ErrorMessage,
    HelloMessage,
    HeartbeatMessage,
    PongMessage,
    TickBatchMessage,
)
from nautilus_mt5.parsing.data import timedelta_to_duration_str
from nautilus_mt5.providers import MetaTrader5InstrumentProvider
from nautilus_mt5.venue_profile import CapabilityStatus

from nautilus_trader.data.messages import SubscribeData
from nautilus_trader.data.messages import SubscribeInstruments
from nautilus_trader.data.messages import SubscribeInstrument
from nautilus_trader.data.messages import SubscribeOrderBook
from nautilus_trader.data.messages import SubscribeQuoteTicks
from nautilus_trader.data.messages import SubscribeTradeTicks
from nautilus_trader.data.messages import SubscribeBars
from nautilus_trader.data.messages import UnsubscribeData
from nautilus_trader.data.messages import UnsubscribeInstruments
from nautilus_trader.data.messages import UnsubscribeInstrument
from nautilus_trader.data.messages import UnsubscribeOrderBook
from nautilus_trader.data.messages import UnsubscribeQuoteTicks
from nautilus_trader.data.messages import UnsubscribeTradeTicks
from nautilus_trader.data.messages import UnsubscribeBars
from nautilus_trader.data.messages import UnsubscribeInstrumentStatus
from nautilus_trader.data.messages import UnsubscribeInstrumentClose
from nautilus_trader.data.messages import RequestData
from nautilus_trader.data.messages import RequestInstrument
from nautilus_trader.data.messages import RequestInstruments
from nautilus_trader.data.messages import RequestQuoteTicks
from nautilus_trader.data.messages import RequestTradeTicks
from nautilus_trader.data.messages import RequestBars



class MetaTrader5DataClient(LiveMarketDataClient):
    """
    Provides a data client for the MetaTrader5 platform by using the `Terminal` to
    stream market data.

    Parameters
    ----------
    loop : asyncio.AbstractEventLoop
        The event loop for the client.
    client : MetaTrader5Client
        The nautilus MetaTrader5Client using mt5linux.
    msgbus : MessageBus
        The message bus for the client.
    cache : Cache
        The cache for the client.
    clock : LiveClock
        The clock for the client.
    instrument_provider : MetaTrader5InstrumentProvider
        The instrument provider.
    mt5_client_id : int
        Client ID used to connect the Terminal.
    config : MetaTrader5DataClientConfig
        Configuration for the client.
    name : str, optional
        The custom client ID.

    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        client: MetaTrader5Client,
        msgbus: MessageBus,
        cache: Cache,
        clock: LiveClock,
        instrument_provider: MetaTrader5InstrumentProvider,
        mt5_client_id: int,
        config: MetaTrader5DataClientConfig,
        name: str | None = None,
    ) -> None:
        super().__init__(
            loop=loop,
            client_id=ClientId(name or f"{MT5_VENUE.value}-{mt5_client_id:03d}"),
            venue=None,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            instrument_provider=instrument_provider,
            config=config,
        )
        self._client = client
        self._handle_revised_bars = config.handle_revised_bars
        self._use_regular_trading_hours = config.use_regular_trading_hours
        self._ignore_quote_tick_size_updates = config.ignore_quote_tick_size_updates
        self._venue_profile = config.venue_profile
        self._feed_config: FeedGatewayConfig = config.feed
        self._feed_gateway: InboundFeedGateway | None = None
        self._feed_pending_symbols: set[str] = set()

    @property
    def feed_gateway(self) -> InboundFeedGateway | None:
        return self._feed_gateway

    @property
    def instrument_provider(self) -> MetaTrader5InstrumentProvider:
        return self._instrument_provider  # type: ignore

    async def _connect(self):
        if self._venue_profile is None:
            raise ValueError(
                "MetaTrader5DataClient requires a 'venue_profile' to be configured. "
                "Use a pre-built profile (e.g., from nautilus_mt5 import TICKMILL_DEMO_PROFILE) "
                "or define a custom VenueProfile. "
                "Set it via MetaTrader5DataClientConfig(venue_profile=...)."
            )
        # Connect client
        await self._client._connect()
        self._client.registered_nautilus_clients.add(self.id)

        # Start internal tasks if any

        # Load instruments based on config
        await self.instrument_provider.initialize()
        for instrument in self._instrument_provider.list_all():
            self._handle_data(instrument)

        if self._feed_config.enabled:
            await self._start_feed_gateway()

    async def _start_feed_gateway(self) -> None:
        self._feed_gateway = InboundFeedGateway(
            config=self._feed_config,
            on_event=self._handle_feed_event,
        )
        await self._feed_gateway.start()
        try:
            hello = await self._feed_gateway.wait_for_hello()
        except TimeoutError as exc:
            self._log.error(
                "MQL5 feed service did not send hello within "
                f"{self._feed_config.hello_timeout_secs}s",
            )
            await self._feed_gateway.stop()
            self._feed_gateway = None
            raise RuntimeError(
                "MQL5 inbound feed handshake timed out waiting for hello",
            ) from exc

        self._log.info(
            f"MQL5 feed hello session={hello.session} symbols={list(hello.symbols)}",
        )

        pending = set(self._feed_pending_symbols)
        pending |= self._feed_gateway.handler.subscription_state.pending_subscribe
        if pending:
            await self._feed_gateway.subscribe(sorted(pending))

    async def _handle_feed_event(self, event: object) -> None:
        if isinstance(event, HelloMessage):
            if self._feed_config.reconnect_notify:
                self._log.info(
                    f"MQL5 feed reconnected session={event.session} "
                    f"symbols={list(event.symbols)}",
                )
            return

        if isinstance(event, TickBatchMessage):
            self._handle_feed_ticks(event)
            return

        if isinstance(event, ErrorMessage):
            self._log.warning(
                f"MQL5 feed service error code={event.code} message={event.message}",
            )
            return

        if isinstance(event, (HeartbeatMessage, PongMessage)):
            self._log.debug(f"MQL5 feed {event.__class__.__name__}")

    def _handle_feed_ticks(self, batch: TickBatchMessage) -> None:
        instrument_id = InstrumentId(Symbol(batch.symbol), MT5_VENUE)
        instrument = self._cache.instrument(instrument_id)
        if instrument is None:
            self._log.debug(
                f"No cached instrument for feed symbol {batch.symbol}; skipping ticks",
            )
            return

        ts_init = self._clock.timestamp_ns()
        for tick in batch.ticks:
            quote_tick = wire_tick_to_quote_tick(instrument, tick, ts_init)
            if quote_tick is not None:
                self._handle_data(quote_tick)

    def _mt5_symbol_from_instrument(self, instrument) -> str:
        try:
            sym_dict = instrument.info["symbol"]
            return MT5Symbol(**sym_dict).symbol
        except Exception:
            return instrument.id.symbol.value

    async def _disconnect(self):
        self._client.registered_nautilus_clients.discard(self.id)
        if self._feed_gateway is not None:
            await self._feed_gateway.stop()
            self._feed_gateway = None
        if (
            self._client.is_running
            and not self._client.registered_nautilus_clients
        ):
            await self._client._disconnect()

    async def _subscribe(self, command: SubscribeData) -> None:
        self._log.warning("MetaTrader5 adapter does not support _subscribe.")

    async def _subscribe_instruments(self, command: SubscribeInstruments) -> None:
        self._log.warning("MetaTrader5 adapter does not support _subscribe_instruments.")

    async def _subscribe_instrument(self, command: SubscribeInstrument) -> None:
        self._log.warning("MetaTrader5 adapter does not support _subscribe_instrument.")

    async def _subscribe_order_book_deltas(self, command: SubscribeOrderBook) -> None:
        self._log.warning("MetaTrader5 adapter does not support _subscribe_order_book_deltas.")

    async def _subscribe_order_book_snapshots(self, command: SubscribeOrderBook) -> None:
        self._log.warning("MetaTrader5 adapter does not support _subscribe_order_book_snapshots.")

    async def _subscribe_quote_ticks(self, command: SubscribeQuoteTicks) -> None:
        instrument_id = command.instrument_id
        if not (instrument := self._cache.instrument(instrument_id)):
            self._log.error(
                f"Cannot subscribe to QuoteTicks for {instrument_id}, Instrument not found.",
            )
            return

        try:
            sym = MT5Symbol(**instrument.info["symbol"])
        except Exception:
            sym = MT5Symbol(symbol=instrument_id.symbol.value)

        if self._feed_config.enabled:
            mt5_symbol = sym.symbol
            self._feed_pending_symbols.add(mt5_symbol)
            if self._feed_gateway is not None:
                await self._feed_gateway.subscribe([mt5_symbol])
            return

        await self._client.subscribe_ticks(
            instrument_id=instrument_id,
            symbol=sym,
            tick_type="BidAsk",
            ignore_size=self._ignore_quote_tick_size_updates,
        )

    async def _subscribe_trade_ticks(self, command: SubscribeTradeTicks) -> None:
        instrument_id = command.instrument_id
        if not (instrument := self._cache.instrument(instrument_id)):
            self._log.error(
                f"Cannot subscribe to TradeTicks for {instrument_id}, Instrument not found.",
            )
            return

        calc_mode = instrument.info.get("trade_calc_mode", 0) if isinstance(instrument.info, dict) else 0
        try:
            status = self._venue_profile.check_capability(calc_mode, "trade_ticks")
        except ValueError as e:
            self._log.error(str(e))
            return

        if status == CapabilityStatus.UNSUPPORTED:
            self._log.warning(
                f"TradeTicks for {instrument_id} (trade_calc_mode={calc_mode}) are UNSUPPORTED "
                f"per VenueProfile '{self._venue_profile.name}'. Subscription rejected."
            )
            return

        if status in (CapabilityStatus.ASSUMED, CapabilityStatus.OBSERVED):
            self._log.warning(
                f"TradeTicks for {instrument_id} (trade_calc_mode={calc_mode}): "
                f"capability status is {status.value!r} in VenueProfile "
                f"'{self._venue_profile.name}' — behavior not yet verified."
            )

        await self._client.subscribe_ticks(
            instrument_id=instrument_id,
            symbol=MT5Symbol(**instrument.info["symbol"]),
            tick_type="AllLast",
            ignore_size=self._ignore_quote_tick_size_updates,
        )

    async def _subscribe_bars(self, command: SubscribeBars) -> None:
        bar_type = command.bar_type
        if not (instrument := self._cache.instrument(bar_type.instrument_id)):
            self._log.error(f"Cannot subscribe to {bar_type}, Instrument not found.")
            return

        if bar_type.spec.timedelta.total_seconds() == 5:
            await self._client.subscribe_realtime_bars(
                bar_type=bar_type,
                symbol=MT5Symbol(**instrument.info["symbol"]),
                use_rth=self._use_regular_trading_hours,
            )
        else:
            await self._client.subscribe_historical_bars(
                bar_type=bar_type,
                symbol=MT5Symbol(**instrument.info["symbol"]),
                use_rth=self._use_regular_trading_hours,
                handle_revised_bars=self._handle_revised_bars,
            )

    async def _subscribe_instrument_status(self, command: SubscribeInstrument) -> None:
        pass  # Subscribed as part of orderbook

    async def _subscribe_instrument_close(self, command: SubscribeInstrument) -> None:
        pass  # Subscribed as part of orderbook

    async def _unsubscribe(self, command: UnsubscribeData) -> None:
        self._log.warning("MetaTrader5 adapter does not support _unsubscribe.")

    async def _unsubscribe_instruments(self, command: UnsubscribeInstruments) -> None:
        self._log.warning("MetaTrader5 adapter does not support _unsubscribe_instruments.")

    async def _unsubscribe_instrument(self, command: UnsubscribeInstrument) -> None:
        self._log.warning("MetaTrader5 adapter does not support _unsubscribe_instrument.")

    async def _unsubscribe_order_book_deltas(self, command: UnsubscribeOrderBook) -> None:
        self._log.warning("MetaTrader5 adapter does not support _unsubscribe_order_book_deltas.")

    async def _unsubscribe_order_book_snapshots(self, command: UnsubscribeOrderBook) -> None:
        self._log.warning("MetaTrader5 adapter does not support _unsubscribe_order_book_snapshots.")

    async def _unsubscribe_quote_ticks(self, command: UnsubscribeQuoteTicks) -> None:
        instrument_id = command.instrument_id
        if self._feed_config.enabled:
            instrument = self._cache.instrument(instrument_id)
            if instrument is None:
                self._log.error(
                    f"Cannot unsubscribe QuoteTicks for {instrument_id}, Instrument not found.",
                )
                return
            mt5_symbol = self._mt5_symbol_from_instrument(instrument)
            self._feed_pending_symbols.discard(mt5_symbol)
            if self._feed_gateway is not None:
                await self._feed_gateway.unsubscribe([mt5_symbol])
            return

        await self._client.unsubscribe_ticks(instrument_id, "BidAsk")

    async def _unsubscribe_trade_ticks(self, command: UnsubscribeTradeTicks) -> None:
        instrument_id = command.instrument_id
        await self._client.unsubscribe_ticks(instrument_id, "AllLast")

    async def _unsubscribe_bars(self, command: UnsubscribeBars) -> None:
        bar_type = command.bar_type
        if bar_type.spec.timedelta.total_seconds() == 5:
            await self._client.unsubscribe_realtime_bars(bar_type)
        else:
            await self._client.unsubscribe_historical_bars(bar_type)

    async def _unsubscribe_instrument_status(self, command: UnsubscribeInstrumentStatus) -> None:
        pass  # Subscribed as part of orderbook

    async def _unsubscribe_instrument_close(self, command: UnsubscribeInstrumentClose) -> None:
        pass  # Subscribed as part of orderbook

    async def _request(self, request: RequestData) -> None:
        self._log.warning("MetaTrader5 adapter does not support _request.")

    async def _request_instrument(self, request: RequestInstrument) -> None:
        instrument_id = request.instrument_id
        correlation_id = request.correlation_id or request.id
        start = request.start
        end = request.end
        if start is not None:
            self._log.warning(
                f"Requesting instrument {instrument_id} with specified `start` which has no effect.",
            )

        if end is not None:
            self._log.warning(
                f"Requesting instrument {instrument_id} with specified `end` which has no effect.",
            )

        await self.instrument_provider.load_async(instrument_id)
        if instrument := self.instrument_provider.find(instrument_id):
            self._handle_data(instrument)
        else:
            self._log.warning(f"{instrument_id} not available.")
            return
        self._handle_instrument(instrument, correlation_id, start, end, None)

    async def _request_instruments(self, request: RequestInstruments) -> None:
        self._log.warning("MetaTrader5 adapter does not support _request_instruments.")

    async def _request_quote_ticks(self, request: RequestQuoteTicks) -> None:
        instrument_id = request.instrument_id
        limit = request.limit
        correlation_id = request.correlation_id
        start = request.start
        end = request.end
        if not (instrument := self._cache.instrument(instrument_id)):
            self._log.error(
                f"Cannot request QuoteTicks for {instrument_id}, Instrument not found.",
            )
            return

        ticks = await self._handle_ticks_request(
            MT5Symbol(**instrument.info["symbol"]),
            "BID_ASK",
            limit,
            start,
            end,
        )
        if not ticks:
            self._log.warning(f"QuoteTicks not received for {instrument_id}")
            return

        self._handle_quote_ticks(instrument_id, ticks, correlation_id)

    async def _request_trade_ticks(self, request: RequestTradeTicks) -> None:
        instrument_id = request.instrument_id
        limit = request.limit
        correlation_id = request.correlation_id
        start = request.start
        end = request.end
        if not (instrument := self._cache.instrument(instrument_id)):
            self._log.error(
                f"Cannot request TradeTicks for {instrument_id}, Instrument not found.",
            )
            return

        calc_mode = instrument.info.get("trade_calc_mode", 0) if isinstance(instrument.info, dict) else 0
        try:
            status = self._venue_profile.check_capability(calc_mode, "trade_ticks")
        except ValueError as e:
            self._log.error(str(e))
            return

        if status == CapabilityStatus.UNSUPPORTED:
            self._log.warning(
                f"TradeTicks for {instrument_id} (trade_calc_mode={calc_mode}) are UNSUPPORTED "
                f"per VenueProfile '{self._venue_profile.name}'. Request rejected."
            )
            return

        if status in (CapabilityStatus.ASSUMED, CapabilityStatus.OBSERVED):
            self._log.warning(
                f"TradeTicks for {instrument_id} (trade_calc_mode={calc_mode}): "
                f"capability status is {status.value!r} in VenueProfile "
                f"'{self._venue_profile.name}' — behavior not yet verified."
            )

        ticks = await self._handle_ticks_request(
            MT5Symbol(**instrument.info["symbol"]),
            "TRADES",
            limit,
            start,
            end,
        )
        if not ticks:
            self._log.warning(f"TradeTicks not received for {instrument_id}")
            return

        self._handle_trade_ticks(instrument_id, ticks, correlation_id)

    async def _handle_ticks_request(
        self,
        symbol: MT5Symbol,
        tick_type: str,
        limit: int,
        start: pd.Timestamp | None = None,
        end: pd.Timestamp | None = None,
    ) -> list[QuoteTick | TradeTick]:
        if not start:
            limit = self._cache.tick_capacity

        if not end:
            end = pd.Timestamp.utcnow()

        ticks: list[QuoteTick | TradeTick] = []
        while (start and end > start) or (len(ticks) < limit > 0):
            await self._client.wait_until_ready()
            ticks_part = await self._client.get_historical_ticks(
                symbol,
                tick_type,
                end_date_time=end,
                use_rth=self._use_regular_trading_hours,
            )
            if not ticks_part:
                break
            end = pd.Timestamp(
                min(ticks_part, key=attrgetter("ts_init")).ts_init, tz="UTC"
            )
            ticks.extend(ticks_part)

        ticks.sort(key=lambda x: x.ts_init)
        return ticks

    async def _request_bars(self, request: RequestBars) -> None:
        bar_type = request.bar_type
        limit = request.limit
        correlation_id = request.correlation_id
        start = request.start
        end = request.end
        if not (instrument := self._cache.instrument(bar_type.instrument_id)):
            self._log.error(
                f"Cannot request {bar_type}, Instrument not found.",
            )
            return

        if not bar_type.spec.is_time_aggregated():
            self._log.error(
                f"Cannot request {bar_type}: only time bars are aggregated by MetaTrader5.",
            )
            return

        if not start and limit == 0:
            limit = 1000

        if not end:
            end = pd.Timestamp.utcnow()

        if start:
            duration = end - start
            duration_str = timedelta_to_duration_str(duration)
        else:
            duration_str = (
                "7 D" if bar_type.spec.timedelta.total_seconds() >= 60 else "1 D"
            )

        bars: list[Bar] = []
        while (start and end > start) or (len(bars) < limit > 0):
            bars_part: list[Bar] = (
                await self._client.get_historical_bars(  # TODO: consider realtime bars
                    bar_type=bar_type,
                    symbol=MT5Symbol(**instrument.info["symbol"]),
                    use_rth=self._use_regular_trading_hours,
                    end_date_time=end,
                    duration=duration_str,
                )
            )
            bars.extend(bars_part)
            if not bars_part or start:
                break
            end = pd.Timestamp(min(bars, key=attrgetter("ts_event")).ts_event, tz="UTC")

        if bars:
            bars = list(set(bars))
            bars.sort(key=lambda x: x.ts_init)
            self._handle_bars(bar_type, bars, bars[0], correlation_id)
            status_msg = {"id": correlation_id, "status": "Success"}
        else:
            self._log.warning(f"Bar Data not received for {bar_type}")
            status_msg = {"id": correlation_id, "status": "Failed"}

        # Publish Status event
        self._msgbus.publish(
            topic=f"requests.{correlation_id}",
            msg=status_msg,
        )
