from __future__ import annotations

from dataclasses import dataclass, field

from nautilus_mt5.feed.messages import (
    ErrorMessage,
    HeartbeatMessage,
    HelloMessage,
    PongMessage,
    TickBatchMessage,
    WireInboundMessage,
    WireTick,
    parse_wire_message,
)


@dataclass
class SymbolFeedState:
    last_cursor: int = 0
    last_tick: WireTick | None = None


@dataclass
class SubscriptionState:
    """Tracks adapter-side symbol subscriptions and Service-reported active symbols."""

    pending_subscribe: set[str] = field(default_factory=set)
    pending_unsubscribe: set[str] = field(default_factory=set)
    service_symbols: frozenset[str] = frozenset()
    session: str | None = None

    def mark_subscribe(self, symbols: list[str] | tuple[str, ...]) -> None:
        for symbol in symbols:
            self.pending_subscribe.add(symbol)
            self.pending_unsubscribe.discard(symbol)

    def mark_unsubscribe(self, symbols: list[str] | tuple[str, ...]) -> None:
        for symbol in symbols:
            self.pending_unsubscribe.add(symbol)
            self.pending_subscribe.discard(symbol)

    def apply_hello(self, hello: HelloMessage) -> None:
        self.session = hello.session
        self.service_symbols = frozenset(hello.symbols)
        self.pending_subscribe -= set(hello.symbols)


def _tick_key(tick: WireTick) -> tuple[int, float, float, int, int]:
    return (tick.time_msc, tick.bid, tick.ask, tick.volume, tick.flags)


@dataclass
class InboundFeedHandler:
    """
    Parse inbound WS JSON, dedup ticks by cursor/time_msc, track subscriptions.

    Spec: res/especificacao_novo_adaptador_nautilus_mt5.md §10.4
    """

    subscription_state: SubscriptionState = field(default_factory=SubscriptionState)
    _symbol_state: dict[str, SymbolFeedState] = field(default_factory=dict)

    def reset(self) -> None:
        self.subscription_state = SubscriptionState()
        self._symbol_state.clear()

    def state_for(self, symbol: str) -> SymbolFeedState:
        if symbol not in self._symbol_state:
            self._symbol_state[symbol] = SymbolFeedState()
        return self._symbol_state[symbol]

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
            if tick.bid <= 0.0 or tick.ask <= 0.0:
                continue
            out.append(tick)

        if out:
            state.last_cursor = batch.cursor
            state.last_tick = out[-1]

        return tuple(out)

    def handle_message(self, message: WireInboundMessage) -> WireInboundMessage | TickBatchMessage | None:
        if isinstance(message, HelloMessage):
            self.subscription_state.apply_hello(message)
            return message

        if isinstance(message, TickBatchMessage):
            deduped = self.dedup_ticks(message)
            if not deduped:
                return None
            return TickBatchMessage(symbol=message.symbol, cursor=message.cursor, ticks=deduped)

        if isinstance(message, (HeartbeatMessage, PongMessage, ErrorMessage)):
            return message

        return message

    def handle_raw(self, raw: str | bytes) -> WireInboundMessage | TickBatchMessage | None:
        return self.handle_message(parse_wire_message(raw))
