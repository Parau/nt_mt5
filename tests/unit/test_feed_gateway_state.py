"""Unit tests for InboundFeedGateway Hello symbol-state waiters."""
from __future__ import annotations

import asyncio

import pytest

from nautilus_mt5.feed.config import FeedGatewayConfig
from nautilus_mt5.feed.gateway import InboundFeedGateway
from nautilus_mt5.feed.messages import HelloMessage


def _gateway() -> InboundFeedGateway:
    return InboundFeedGateway(
        config=FeedGatewayConfig(enabled=True, hello_timeout_secs=0.5),
    )


@pytest.mark.asyncio
async def test_g01_wait_absent_returns_immediately_when_already_absent() -> None:
    gw = _gateway()
    await gw._record_hello(HelloMessage(session="s1", symbols=()))
    hello = await gw.wait_for_symbols_absent(["ENQU26"], timeout_secs=0.2)
    assert hello.session == "s1"
    assert "ENQU26" not in hello.symbols


@pytest.mark.asyncio
async def test_g02_wait_absent_completes_on_later_hello() -> None:
    gw = _gateway()
    await gw._record_hello(HelloMessage(session="s1", symbols=("ENQU26",)))

    async def _later() -> None:
        await asyncio.sleep(0.05)
        await gw._record_hello(HelloMessage(session="s2", symbols=()))

    task = asyncio.create_task(_later())
    hello = await gw.wait_for_symbols_absent(["ENQU26"], timeout_secs=1.0)
    await task
    assert hello.session == "s2"
    assert "ENQU26" not in hello.symbols


@pytest.mark.asyncio
async def test_g03_unrelated_symbol_remaining_still_succeeds() -> None:
    gw = _gateway()
    await gw._record_hello(HelloMessage(session="s1", symbols=("MNQU26", "ENQU26")))

    async def _later() -> None:
        await asyncio.sleep(0.05)
        await gw._record_hello(HelloMessage(session="s2", symbols=("MNQU26",)))

    task = asyncio.create_task(_later())
    hello = await gw.wait_for_symbols_absent(["ENQU26"], timeout_secs=1.0)
    await task
    assert hello.symbols == ("MNQU26",)


@pytest.mark.asyncio
async def test_g04_target_still_present_keeps_waiting_until_timeout() -> None:
    gw = _gateway()
    await gw._record_hello(HelloMessage(session="s1", symbols=("ENQU26",)))

    async def _noise() -> None:
        await asyncio.sleep(0.05)
        await gw._record_hello(HelloMessage(session="s2", symbols=("ENQU26", "MNQU26")))

    task = asyncio.create_task(_noise())
    with pytest.raises(TimeoutError):
        await gw.wait_for_symbols_absent(["ENQU26"], timeout_secs=0.2)
    await task


@pytest.mark.asyncio
async def test_g05_timeout_raises() -> None:
    gw = _gateway()
    await gw._record_hello(HelloMessage(session="s1", symbols=("ENQU26",)))
    with pytest.raises(TimeoutError):
        await gw.wait_for_symbols_absent(["ENQU26"], timeout_secs=0.1)


@pytest.mark.asyncio
async def test_g06_stop_clears_hello_so_old_state_is_not_reused() -> None:
    gw = _gateway()
    await gw._record_hello(HelloMessage(session="old", symbols=()))
    await gw.stop()
    assert gw.last_hello is None

    with pytest.raises(TimeoutError):
        await gw.wait_for_symbols_absent(["ENQU26"], timeout_secs=0.1)
