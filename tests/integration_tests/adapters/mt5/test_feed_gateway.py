from __future__ import annotations

import asyncio
import json
import socket

import pytest
import websockets

from nautilus_mt5.feed.config import FeedGatewayConfig
from nautilus_mt5.feed.gateway import InboundFeedGateway
from nautilus_mt5.feed.messages import HelloMessage, TickBatchMessage


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


@pytest.mark.asyncio
async def test_gateway_hello_subscribe_and_ticks() -> None:
    port = _free_port()
    events: list[object] = []

    async def on_event(event: object) -> None:
        events.append(event)

    gateway = InboundFeedGateway(
        config=FeedGatewayConfig(
            enabled=True,
            host="127.0.0.1",
            port=port,
            path="/mt5-feed",
            hello_timeout_secs=5.0,
        ),
        on_event=on_event,
    )

    await gateway.start()
    try:
        uri = f"ws://127.0.0.1:{port}/mt5-feed"
        async with websockets.connect(uri) as ws:
            await ws.send(
                json.dumps(
                    {
                        "op": "hello",
                        "session": "nt5-test",
                        "account": 25339175,
                        "symbols": ["BTCUSD"],
                    }
                )
            )

            hello = await gateway.wait_for_hello(timeout_secs=2.0)
            assert isinstance(hello, HelloMessage)
            assert hello.session == "nt5-test"

            await gateway.subscribe(["EURUSD"])
            subscribe_raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
            subscribe_msg = json.loads(subscribe_raw)
            assert subscribe_msg == {"op": "subscribe", "symbols": ["EURUSD"]}

            await ws.send(
                json.dumps(
                    {
                        "op": "ticks",
                        "symbol": "BTCUSD",
                        "cursor": 1000,
                        "data": [
                            {
                                "time_msc": 1000,
                                "bid": 1.0,
                                "ask": 1.1,
                                "last": 0.0,
                                "volume": 0,
                                "flags": 6,
                            }
                        ],
                    }
                )
            )
            await asyncio.sleep(0.05)

        tick_events = [e for e in events if isinstance(e, TickBatchMessage)]
        assert len(tick_events) == 1
        assert tick_events[0].symbol == "BTCUSD"
        assert tick_events[0].cursor == 1000
    finally:
        await gateway.stop()
