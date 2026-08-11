from __future__ import annotations

from dataclasses import dataclass, field

from nautilus_mt5.feed.messages import (
    BarMessage,
    ErrorMessage,
    HeartbeatMessage,
    HelloMessage,
    PongMessage,
    TickBatchMessage,
    WireBar,
    WireInboundMessage,
    WireTick,
    parse_bar_spec,
    parse_wire_message,
)


@dataclass
class SymbolFeedState:
    last_cursor: int = 0
    last_tick: WireTick | None = None


@dataclass
class BarFeedState:
    last_closed_time: int = 0


@dataclass
class SubscriptionState:
    """Tracks adapter-side subscriptions and Service-reported active symbols/bars."""

    pending_subscribe: set[str] = field(default_factory=set)
    pending_unsubscribe: set[str] = field(default_factory=set)
    service_symbols: frozenset[str] = frozenset()
    pending_bar_subscribe: set[tuple[str, str]] = field(default_factory=set)
    pending_bar_unsubscribe: set[tuple[str, str]] = field(default_factory=set)
    service_bars: frozenset[tuple[str, str]] = frozenset()
    session: str | None = None

    def mark_subscribe(self, symbols: list[str] | tuple[str, ...]) -> None:
        for symbol in symbols:
            self.pending_subscribe.add(symbol)
            self.pending_unsubscribe.discard(symbol)

    def mark_unsubscribe(self, symbols: list[str] | tuple[str, ...]) -> None:
        for symbol in symbols:
            self.pending_unsubscribe.add(symbol)
            self.pending_subscribe.discard(symbol)

    def mark_subscribe_bars(
        self,
        symbols: list[str] | tuple[str, ...],
        timeframe: str,
    ) -> None:
        tf = timeframe.upper()
        for symbol in symbols:
            key = (symbol, tf)
            self.pending_bar_subscribe.add(key)
            self.pending_bar_unsubscribe.discard(key)

    def mark_unsubscribe_bars(
        self,
        symbols: list[str] | tuple[str, ...],
        timeframe: str,
    ) -> None:
        tf = timeframe.upper()
        for symbol in symbols:
            key = (symbol, tf)
            self.pending_bar_unsubscribe.add(key)
            self.pending_bar_subscribe.discard(key)

    def apply_hello(self, hello: HelloMessage) -> None:
        self.session = hello.session
        self.service_symbols = frozenset(hello.symbols)
        self.pending_subscribe -= set(hello.symbols)

        service_bars: set[tuple[str, str]] = set()
        for spec in hello.bars:
            parsed = parse_bar_spec(spec)
            if parsed is not None:
                service_bars.add((parsed[0], parsed[1].upper()))
        self.service_bars = frozenset(service_bars)
        self.pending_bar_subscribe -= self.service_bars


def _tick_key(tick: WireTick) -> tuple[int, float, float, int, int]:
    return (tick.time_msc, tick.bid, tick.ask, tick.volume, tick.flags)


def _bar_key(bar: WireBar) -> tuple[str, str, int]:
    return (bar.symbol, bar.timeframe.upper(), bar.time)


@dataclass
class InboundFeedHandler:
    """
    Parse inbound WS JSON, dedup ticks/bars, track subscriptions.

    Does not decide QuoteTick vs TradeTick emission — that belongs to
    ``route_wire_tick_to_nautilus``. Invalid Bid/Ask alone must not drop a row.

    Spec: res/especificacao_novo_adaptador_nautilus_mt5.md §10.4
    """

    subscription_state: SubscriptionState = field(default_factory=SubscriptionState)
    _symbol_state: dict[str, SymbolFeedState] = field(default_factory=dict)
    _bar_state: dict[tuple[str, str], BarFeedState] = field(default_factory=dict)

    def reset(self) -> None:
        self.subscription_state = SubscriptionState()
        self._symbol_state.clear()
        self._bar_state.clear()

    def state_for(self, symbol: str) -> SymbolFeedState:
        if symbol not in self._symbol_state:
            self._symbol_state[symbol] = SymbolFeedState()
        return self._symbol_state[symbol]

    def bar_state_for(self, symbol: str, timeframe: str) -> BarFeedState:
        key = (symbol, timeframe.upper())
        if key not in self._bar_state:
            self._bar_state[key] = BarFeedState()
        return self._bar_state[key]

    def dedup_ticks(self, batch: TickBatchMessage) -> tuple[WireTick, ...]:
        state = self.state_for(batch.symbol)
        if batch.cursor < state.last_cursor:
            return ()

        out: list[WireTick] = []
        for tick in batch.ticks:
            if tick.time_msc < state.last_cursor:
                continue
            if state.last_tick is not None and _tick_key(tick) == _tick_key(state.last_tick):
                continue
            # Do not filter on bid/ask here — Quote vs Trade emission is decided by
            # route_wire_tick_to_nautilus (flags + BBO / trade conversion).
            out.append(tick)

        if out:
            state.last_cursor = batch.cursor
            state.last_tick = out[-1]

        return tuple(out)

    def dedup_bar(self, message: BarMessage) -> BarMessage | None:
        bar = message.bar
        if bar.time <= 0 or bar.close <= 0.0:
            return None

        state = self.bar_state_for(bar.symbol, bar.timeframe)
        if bar.time <= state.last_closed_time:
            return None

        state.last_closed_time = bar.time
        return message

    def handle_message(
        self,
        message: WireInboundMessage,
    ) -> WireInboundMessage | TickBatchMessage | BarMessage | None:
        if isinstance(message, HelloMessage):
            self.subscription_state.apply_hello(message)
            return message

        if isinstance(message, TickBatchMessage):
            deduped = self.dedup_ticks(message)
            if not deduped:
                return None
            return TickBatchMessage(symbol=message.symbol, cursor=message.cursor, ticks=deduped)

        if isinstance(message, BarMessage):
            return self.dedup_bar(message)

        if isinstance(message, (HeartbeatMessage, PongMessage, ErrorMessage)):
            return message

        return message

    def handle_raw(self, raw: str | bytes) -> WireInboundMessage | TickBatchMessage | BarMessage | None:
        return self.handle_message(parse_wire_message(raw))
