from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class WireTick:
    time_msc: int
    bid: float
    ask: float
    last: float = 0.0
    volume: int = 0
    flags: int = 0


@dataclass(frozen=True, slots=True)
class WireBar:
    symbol: str
    timeframe: str
    time: int
    open: float
    high: float
    low: float
    close: float
    tick_volume: int = 0
    real_volume: int = 0
    spread: int = 0


@dataclass(frozen=True, slots=True)
class HelloMessage:
    session: str
    symbols: tuple[str, ...]
    bars: tuple[str, ...] = ()
    terminal: str | None = None
    account: str | None = None


@dataclass(frozen=True, slots=True)
class TickBatchMessage:
    symbol: str
    cursor: int
    ticks: tuple[WireTick, ...]


@dataclass(frozen=True, slots=True)
class BarMessage:
    bar: WireBar


@dataclass(frozen=True, slots=True)
class HeartbeatMessage:
    ts_msc: int


@dataclass(frozen=True, slots=True)
class PongMessage:
    pass


@dataclass(frozen=True, slots=True)
class ErrorMessage:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class SubscribeCommand:
    symbols: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class UnsubscribeCommand:
    symbols: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SubscribeBarsCommand:
    symbols: tuple[str, ...]
    timeframe: str


@dataclass(frozen=True, slots=True)
class UnsubscribeBarsCommand:
    symbols: tuple[str, ...]
    timeframe: str


@dataclass(frozen=True, slots=True)
class PingCommand:
    pass


WireInboundMessage = (
    HelloMessage
    | TickBatchMessage
    | BarMessage
    | HeartbeatMessage
    | PongMessage
    | ErrorMessage
)
WireOutboundCommand = (
    SubscribeCommand
    | UnsubscribeCommand
    | SubscribeBarsCommand
    | UnsubscribeBarsCommand
    | PingCommand
)


def _symbols_tuple(raw: Any) -> tuple[str, ...]:
    if not isinstance(raw, list):
        return ()
    return tuple(str(s) for s in raw if s)


def _bars_tuple(raw: Any) -> tuple[str, ...]:
    if not isinstance(raw, list):
        return ()
    out: list[str] = []
    for item in raw:
        if not item:
            continue
        out.append(str(item))
    return tuple(out)


def _parse_tick(raw: dict[str, Any]) -> WireTick:
    return WireTick(
        time_msc=int(raw["time_msc"]),
        bid=float(raw.get("bid", 0.0)),
        ask=float(raw.get("ask", 0.0)),
        last=float(raw.get("last", 0.0)),
        volume=int(raw.get("volume", 0)),
        flags=int(raw.get("flags", 0)),
    )


def _parse_bar(payload: dict[str, Any]) -> WireBar:
    symbol = payload.get("symbol")
    timeframe = payload.get("timeframe")
    bar_time = payload.get("time")
    if not isinstance(symbol, str) or not symbol:
        raise ValueError("bar missing symbol")
    if not isinstance(timeframe, str) or not timeframe:
        raise ValueError("bar missing timeframe")
    if bar_time is None:
        raise ValueError("bar missing time")
    return WireBar(
        symbol=symbol,
        timeframe=timeframe,
        time=int(bar_time),
        open=float(payload.get("open", 0.0)),
        high=float(payload.get("high", 0.0)),
        low=float(payload.get("low", 0.0)),
        close=float(payload.get("close", 0.0)),
        tick_volume=int(payload.get("tick_volume", 0)),
        real_volume=int(payload.get("real_volume", 0)),
        spread=int(payload.get("spread", 0)),
    )


def parse_wire_message(raw: str | bytes) -> WireInboundMessage:
    """
    Parse one inbound JSON frame from the MQL5 Service.

    Raises:
        json.JSONDecodeError: invalid JSON.
        ValueError: unknown or malformed message.
    """
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")

    payload: dict[str, Any] = json.loads(raw)
    op = payload.get("op")
    if not isinstance(op, str):
        raise ValueError("wire message missing string 'op' field")

    if op == "hello":
        session = payload.get("session")
        if not isinstance(session, str) or not session:
            raise ValueError("hello missing session")
        return HelloMessage(
            session=session,
            symbols=_symbols_tuple(payload.get("symbols")),
            bars=_bars_tuple(payload.get("bars")),
            terminal=payload.get("terminal") if payload.get("terminal") is not None else None,
            account=str(payload["account"]) if payload.get("account") is not None else None,
        )

    if op == "ticks":
        symbol = payload.get("symbol")
        if not isinstance(symbol, str) or not symbol:
            raise ValueError("ticks missing symbol")
        cursor = payload.get("cursor")
        if cursor is None:
            raise ValueError("ticks missing cursor")
        data = payload.get("data")
        if not isinstance(data, list):
            raise ValueError("ticks missing data[]")
        ticks = tuple(_parse_tick(item) for item in data if isinstance(item, dict))
        return TickBatchMessage(symbol=symbol, cursor=int(cursor), ticks=ticks)

    if op == "bar":
        return BarMessage(bar=_parse_bar(payload))

    if op == "heartbeat":
        ts_msc = payload.get("ts_msc")
        if ts_msc is None:
            raise ValueError("heartbeat missing ts_msc")
        return HeartbeatMessage(ts_msc=int(ts_msc))

    if op == "pong":
        return PongMessage()

    if op == "error":
        code = payload.get("code")
        message = payload.get("message")
        if not isinstance(code, str) or not isinstance(message, str):
            raise ValueError("error missing code/message")
        return ErrorMessage(code=code, message=message)

    raise ValueError(f"unsupported wire op: {op!r}")


def build_subscribe_command(symbols: list[str] | tuple[str, ...]) -> str:
    return json.dumps({"op": "subscribe", "symbols": list(symbols)}, separators=(",", ":"))


def build_unsubscribe_command(symbols: list[str] | tuple[str, ...]) -> str:
    return json.dumps({"op": "unsubscribe", "symbols": list(symbols)}, separators=(",", ":"))


def build_subscribe_bars_command(
    symbols: list[str] | tuple[str, ...],
    timeframe: str,
) -> str:
    return json.dumps(
        {"op": "subscribe_bars", "symbols": list(symbols), "timeframe": timeframe},
        separators=(",", ":"),
    )


def build_unsubscribe_bars_command(
    symbols: list[str] | tuple[str, ...],
    timeframe: str,
) -> str:
    return json.dumps(
        {"op": "unsubscribe_bars", "symbols": list(symbols), "timeframe": timeframe},
        separators=(",", ":"),
    )


def build_ping_command() -> str:
    return json.dumps({"op": "ping"}, separators=(",", ":"))


def parse_bar_spec(spec: str) -> tuple[str, str] | None:
    """Parse ``SYMBOL:M1`` wire hello bar spec."""
    if ":" not in spec:
        return None
    symbol, timeframe = spec.split(":", 1)
    symbol = symbol.strip()
    timeframe = timeframe.strip()
    if not symbol or not timeframe:
        return None
    return symbol, timeframe
