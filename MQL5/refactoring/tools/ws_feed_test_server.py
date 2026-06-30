#!/usr/bin/env python3
"""
Minimal WS server for NT5TickFeedService MVP validation.

Protocol: res/especificacao_novo_adaptador_nautilus_mt5.md §9

Usage (host, before starting MQL5 Service):
    python MQL5/refactoring/tools/ws_feed_test_server.py --host 0.0.0.0 --port 8765 -v
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
from typing import Any

import websockets
from websockets.asyncio.server import serve
from websockets.server import WebSocketServerProtocol

LOG = logging.getLogger("nt5_ws_test")


async def handle_client(ws: WebSocketServerProtocol) -> None:
    peer = ws.remote_address
    LOG.info("Service connected from %s", peer)
    tick_batches = 0
    tick_count = 0
    bar_count = 0

    try:
        async for raw in ws:
            try:
                msg: dict[str, Any] = json.loads(raw)
            except json.JSONDecodeError:
                LOG.warning("Invalid JSON: %s", raw[:200])
                continue

            op = msg.get("op")
            if op == "hello":
                LOG.info(
                    "HELLO session=%s account=%s symbols=%s bars=%s",
                    msg.get("session"),
                    msg.get("account"),
                    msg.get("symbols"),
                    msg.get("bars"),
                )
            elif op == "ticks":
                batch = msg.get("data") or []
                n = len(batch)
                tick_batches += 1
                tick_count += n
                LOG.info(
                    "TICKS symbol=%s cursor=%s count=%d (total_batches=%d total_ticks=%d)",
                    msg.get("symbol"),
                    msg.get("cursor"),
                    n,
                    tick_batches,
                    tick_count,
                )
            elif op == "bar":
                bar_count += 1
                LOG.info(
                    "BAR symbol=%s timeframe=%s time=%s close=%s (total_bars=%d)",
                    msg.get("symbol"),
                    msg.get("timeframe"),
                    msg.get("time"),
                    msg.get("close"),
                    bar_count,
                )
            elif op == "subscribe_bars":
                LOG.info(
                    "SUBSCRIBE_BARS symbols=%s timeframe=%s",
                    msg.get("symbols"),
                    msg.get("timeframe"),
                )
            elif op == "unsubscribe_bars":
                LOG.info(
                    "UNSUBSCRIBE_BARS symbols=%s timeframe=%s",
                    msg.get("symbols"),
                    msg.get("timeframe"),
                )
            elif op == "subscribe":
                LOG.info("SUBSCRIBE from adapter/service echo symbols=%s", msg.get("symbols"))
            elif op == "unsubscribe":
                LOG.info("UNSUBSCRIBE symbols=%s", msg.get("symbols"))
            elif op == "heartbeat":
                LOG.debug("heartbeat ts_msc=%s", msg.get("ts_msc"))
            elif op == "pong":
                LOG.debug("pong")
            elif op == "error":
                LOG.error("Service error: %s — %s", msg.get("code"), msg.get("message"))
            else:
                LOG.info("Message op=%s payload=%s", op, msg)
    except websockets.ConnectionClosed as exc:
        LOG.info(
            "Service disconnected from %s (%s) batches=%d ticks=%d bars=%d",
            peer,
            exc,
            tick_batches,
            tick_count,
            bar_count,
        )


async def main(host: str, port: int, path: str) -> None:
    async with serve(handle_client, host, port, ping_interval=None):
        LOG.info("Listening on ws://%s:%s%s", host, port, path)
        await asyncio.Future()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NT5 feed WS test server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--path", default="/mt5-feed")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if args.path != "/mt5-feed":
        LOG.warning("Path argument ignored; websockets.serve binds by port only.")

    asyncio.run(main(args.host, args.port, args.path))
