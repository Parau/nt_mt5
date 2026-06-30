from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import websockets
from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from nautilus_mt5.feed.config import FeedGatewayConfig
from nautilus_mt5.feed.handler import InboundFeedHandler
from nautilus_mt5.feed.messages import (
    BarMessage,
    HelloMessage,
    TickBatchMessage,
    build_ping_command,
    build_subscribe_bars_command,
    build_subscribe_command,
    build_unsubscribe_bars_command,
    build_unsubscribe_command,
    parse_wire_message,
)

EventCallback = Callable[[Any], Awaitable[None] | None]


def normalize_feed_request_path(request_path: str | None, configured_path: str) -> str:
    """
    Normalize WS request path for comparison.

    MQL5 tarasyyyk client may send the full URL (``ws://host:8765/mt5-feed``)
    in ``request.path`` instead of ``/mt5-feed``.
    """
    expected = configured_path if configured_path.startswith("/") else f"/{configured_path}"
    if not request_path:
        return expected

    raw = request_path.strip()
    if raw.startswith("ws://") or raw.startswith("wss://"):
        # MQL5Book / tarasyyyk: path field may contain the full WS URL string.
        without_scheme = raw.split("://", 1)[1]
        slash = without_scheme.find("/")
        raw = without_scheme[slash:] if slash >= 0 else "/"

    path = raw.split("?", 1)[0]
    if not path.startswith("/"):
        path = f"/{path}"
    return path.rstrip("/") or "/"


def feed_path_matches(request_path: str | None, configured_path: str) -> bool:
    expected = configured_path if configured_path.startswith("/") else f"/{configured_path}"
    actual = normalize_feed_request_path(request_path, configured_path)
    return actual == expected.rstrip("/") or actual == expected


class InboundFeedGateway:
    """
    WebSocket server that accepts one MQL5 Service connection (v1).

    Spec: res/especificacao_novo_adaptador_nautilus_mt5.md §5 / §10.1
    """

    def __init__(
        self,
        config: FeedGatewayConfig,
        handler: InboundFeedHandler | None = None,
        on_event: EventCallback | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._config = config
        self._handler = handler or InboundFeedHandler()
        self._on_event = on_event
        self._log = logger or logging.getLogger(__name__)
        self._server: Any | None = None
        self._service_ws: ServerConnection | None = None
        self._hello_event = asyncio.Event()
        self._last_hello: HelloMessage | None = None
        self._connection_lock = asyncio.Lock()

    @property
    def handler(self) -> InboundFeedHandler:
        return self._handler

    @property
    def last_hello(self) -> HelloMessage | None:
        return self._last_hello

    @property
    def is_service_connected(self) -> bool:
        ws = self._service_ws
        return ws is not None and ws.state.name == "OPEN"

    async def start(self) -> None:
        if self._server is not None:
            return

        self._hello_event.clear()
        self._last_hello = None
        self._server = await serve(
            self._connection_handler,
            self._config.host,
            self._config.port,
            ping_interval=None,
        )
        self._log.info(
            "Inbound feed gateway listening on ws://%s:%s%s",
            self._config.host,
            self._config.port,
            self._config.path,
        )

    async def stop(self) -> None:
        async with self._connection_lock:
            if self._service_ws is not None:
                await self._service_ws.close()
                self._service_ws = None

        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        self._hello_event.clear()
        self._last_hello = None

    async def wait_for_hello(self, timeout_secs: float | None = None) -> HelloMessage:
        timeout = timeout_secs if timeout_secs is not None else self._config.hello_timeout_secs
        await asyncio.wait_for(self._hello_event.wait(), timeout=timeout)
        if self._last_hello is None:
            raise RuntimeError("hello event set but no hello message stored")
        return self._last_hello

    async def subscribe(self, symbols: list[str] | tuple[str, ...]) -> None:
        if not symbols:
            return
        self._handler.subscription_state.mark_subscribe(symbols)
        if self.is_service_connected:
            await self._send(build_subscribe_command(symbols))

    async def unsubscribe(self, symbols: list[str] | tuple[str, ...]) -> None:
        if not symbols:
            return
        self._handler.subscription_state.mark_unsubscribe(symbols)
        if self.is_service_connected:
            await self._send(build_unsubscribe_command(symbols))

    async def subscribe_bars(
        self,
        symbols: list[str] | tuple[str, ...],
        timeframe: str,
    ) -> None:
        if not symbols or not timeframe:
            return
        self._handler.subscription_state.mark_subscribe_bars(symbols, timeframe)
        if self.is_service_connected:
            await self._send(build_subscribe_bars_command(symbols, timeframe))

    async def unsubscribe_bars(
        self,
        symbols: list[str] | tuple[str, ...],
        timeframe: str,
    ) -> None:
        if not symbols or not timeframe:
            return
        self._handler.subscription_state.mark_unsubscribe_bars(symbols, timeframe)
        if self.is_service_connected:
            await self._send(build_unsubscribe_bars_command(symbols, timeframe))

    async def ping(self) -> None:
        await self._send(build_ping_command())

    async def _send(self, payload: str) -> None:
        ws = self._service_ws
        if ws is None or ws.state.name != "OPEN":
            raise RuntimeError("MQL5 feed service is not connected")
        await ws.send(payload)

    async def _connection_handler(self, websocket: ServerConnection) -> None:
        raw_path = websocket.request.path if websocket.request else self._config.path
        if not feed_path_matches(raw_path, self._config.path):
            self._log.warning("Rejecting feed connection on unexpected path: %s", raw_path)
            await websocket.close(1008, "invalid path")
            return

        async with self._connection_lock:
            if self._service_ws is not None and self._service_ws.state.name == "OPEN":
                self._log.warning("Replacing existing MQL5 feed service connection")
                await self._service_ws.close()
            self._service_ws = websocket

        peer = websocket.remote_address
        self._log.info("MQL5 feed service connected from %s", peer)
        if self._config.reconnect_notify:
            self._log.info("Feed service connected (%s)", peer)

        try:
            async for raw in websocket:
                await self._handle_raw(raw)
        except ConnectionClosed as exc:
            self._log.info("MQL5 feed service disconnected from %s (%s)", peer, exc)
        finally:
            async with self._connection_lock:
                if self._service_ws is websocket:
                    self._service_ws = None

    async def _handle_raw(self, raw: str | bytes) -> None:
        try:
            parsed = parse_wire_message(raw)
        except (ValueError, UnicodeDecodeError) as exc:
            self._log.warning("Invalid feed wire message: %s", exc)
            return

        event = self._handler.handle_message(parsed)
        if event is None:
            return

        if isinstance(event, HelloMessage):
            self._last_hello = event
            self._hello_event.set()

        if self._on_event is not None:
            result = self._on_event(event)
            if asyncio.iscoroutine(result):
                await result

        if isinstance(event, TickBatchMessage):
            self._log.debug(
                "Feed ticks %s cursor=%s count=%d",
                event.symbol,
                event.cursor,
                len(event.ticks),
            )
        elif isinstance(event, BarMessage):
            bar = event.bar
            self._log.debug(
                "Feed bar %s:%s time=%s close=%s",
                bar.symbol,
                bar.timeframe,
                bar.time,
                bar.close,
            )
