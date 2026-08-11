"""A05 Actor → DataEngine → adapter → DataResponse → Actor (x04 §3).

Purpose/Single Responsibility:
    Prove bounded historical TradeTicks use the real Nautilus request/response
    plumbing without monkeypatching ``_handle_trade_ticks``.

Data Flow & Dependencies:
    Recording Actor.request_trade_ticks → LiveDataEngine → MetaTrader5DataClient
    → fake EXTERNAL_RPyC bridge → DataResponse → Actor.on_historical_data /
    completion callback.

Premises & Limitations:
    Tier 1 only (fake bridge). Failure case asserts no success callback within a
    short harness window; B07 owns production timeout semantics.
"""
from __future__ import annotations

import asyncio
from typing import Any

import numpy as np
import pandas as pd
import pytest
import pytest_asyncio
from nautilus_trader.common.actor import Actor
from nautilus_trader.config import ActorConfig
from nautilus_trader.live.data_engine import LiveDataEngine
from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.portfolio.portfolio import Portfolio

from nautilus_mt5.client.types import MT5TerminalAccessMode
from nautilus_mt5.config import (
    ExternalRPyCTerminalConfig,
    MetaTrader5DataClientConfig,
    MetaTrader5InstrumentProviderConfig,
)
from nautilus_mt5.data_types import MT5Symbol
from nautilus_mt5.factories import MT5LiveDataClientFactory
from nautilus_mt5.metatrader5.tick_transport import MT5_TICK_DTYPE
from nautilus_mt5.venue_profile import XP_B3_PROFILE

_VENUE = Venue("METATRADER_5")
_WIN_DOLLAR_ID = InstrumentId(Symbol("WIN$"), _VENUE)
_OBSERVE_SECS = 0.4


class _RecordingHistoricalActor(Actor):
    """Minimal actor that records historical TradeTicks and request completions."""

    def __init__(self) -> None:
        super().__init__(ActorConfig(component_id="A05-HIST-REC"))
        self.historical: list[TradeTick] = []
        self.completions: list[Any] = []

    def on_historical_data(self, data: Any) -> None:
        if isinstance(data, TradeTick):
            self.historical.append(data)

    def on_request_complete(self, request_id: Any) -> None:
        self.completions.append(request_id)


def _data_config() -> MetaTrader5DataClientConfig:
    return MetaTrader5DataClientConfig(
        client_id=1,
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=ExternalRPyCTerminalConfig(host="127.0.0.1", port=18812),
        venue_profile=XP_B3_PROFILE,
        instrument_provider=MetaTrader5InstrumentProviderConfig(
            load_symbols=frozenset({MT5Symbol(symbol="WIN$")}),
        ),
    )


async def _wait_completion(
    actor: _RecordingHistoricalActor,
    request_id: Any,
    timeout: float,
) -> bool:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if request_id in actor.completions and not actor.is_pending_request(request_id):
            return True
        await asyncio.sleep(0.02)
    return False


@pytest_asyncio.fixture
async def a05_actor_stack(clean_factory_cache, nautilus_components, nautilus_mt5_harness):
    """LiveDataEngine + connected MT5 data client + recording Actor."""
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()
    fake_conn = nautilus_mt5_harness

    portfolio = Portfolio(msgbus=msgbus, cache=cache, clock=clock)
    engine = LiveDataEngine(loop=loop, msgbus=msgbus, cache=cache, clock=clock)
    engine.start()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop,
        name="MT5",
        config=_data_config(),
        msgbus=msgbus,
        cache=cache,
        clock=clock,
    )
    engine.register_client(data_client)
    await data_client._connect()

    actor = _RecordingHistoricalActor()
    actor.register_base(portfolio=portfolio, msgbus=msgbus, cache=cache, clock=clock)
    actor.start()

    yield {
        "actor": actor,
        "data_client": data_client,
        "engine": engine,
        "fake_conn": fake_conn,
    }

    try:
        actor.stop()
    finally:
        engine.stop()


@pytest.mark.asyncio
@pytest.mark.data_tester
async def test_a05_actor_bounded_non_empty(a05_actor_stack):
    actor = a05_actor_stack["actor"]
    data_client = a05_actor_stack["data_client"]

    start = pd.Timestamp("2023-11-14 22:13:20", tz="UTC")
    end = pd.Timestamp("2023-11-14 22:13:21", tz="UTC")
    req_id = actor.request_trade_ticks(
        instrument_id=_WIN_DOLLAR_ID,
        start=start,
        end=end,
        limit=0,
        client_id=data_client.id,
        callback=actor.on_request_complete,
    )

    assert await _wait_completion(actor, req_id, timeout=2.0)
    assert actor.completions == [req_id]
    assert len(actor.historical) >= 1
    assert all(isinstance(t, TradeTick) for t in actor.historical)
    assert all(start.value <= t.ts_event <= end.value for t in actor.historical)
    assert not actor.has_pending_requests()


@pytest.mark.asyncio
@pytest.mark.data_tester
async def test_a05_actor_bounded_empty_success(a05_actor_stack):
    actor = a05_actor_stack["actor"]
    data_client = a05_actor_stack["data_client"]
    fake_conn = a05_actor_stack["fake_conn"]

    fake_conn.root.set_copy_ticks_range_override(np.zeros(0, dtype=MT5_TICK_DTYPE))

    start = pd.Timestamp("2023-11-14 22:13:20", tz="UTC")
    end = pd.Timestamp("2023-11-14 22:13:21", tz="UTC")
    req_id = actor.request_trade_ticks(
        instrument_id=_WIN_DOLLAR_ID,
        start=start,
        end=end,
        limit=0,
        client_id=data_client.id,
        callback=actor.on_request_complete,
    )

    assert await _wait_completion(actor, req_id, timeout=2.0)
    assert actor.completions == [req_id]
    assert actor.historical == []
    assert not actor.has_pending_requests()


@pytest.mark.asyncio
@pytest.mark.data_tester
async def test_a05_actor_bounded_sequential_requests(a05_actor_stack):
    actor = a05_actor_stack["actor"]
    data_client = a05_actor_stack["data_client"]
    fake_conn = a05_actor_stack["fake_conn"]

    start1 = pd.Timestamp("2023-11-14 22:13:20", tz="UTC")
    end1 = pd.Timestamp("2023-11-14 22:13:21", tz="UTC")
    start2 = pd.Timestamp("2023-11-14 22:13:22", tz="UTC")
    end2 = pd.Timestamp("2023-11-14 22:13:23", tz="UTC")

    req1 = actor.request_trade_ticks(
        instrument_id=_WIN_DOLLAR_ID,
        start=start1,
        end=end1,
        limit=0,
        client_id=data_client.id,
        callback=actor.on_request_complete,
    )
    assert await _wait_completion(actor, req1, timeout=2.0)
    hist_after_first = list(actor.historical)

    fake_conn.root.set_copy_ticks_range_override(np.zeros(0, dtype=MT5_TICK_DTYPE))
    req2 = actor.request_trade_ticks(
        instrument_id=_WIN_DOLLAR_ID,
        start=start2,
        end=end2,
        limit=0,
        client_id=data_client.id,
        callback=actor.on_request_complete,
    )
    assert await _wait_completion(actor, req2, timeout=2.0)

    assert actor.completions == [req1, req2]
    assert req1 != req2
    assert len(hist_after_first) >= 1
    assert len(actor.historical) == len(hist_after_first)
    assert not actor.has_pending_requests()


@pytest.mark.asyncio
@pytest.mark.data_tester
async def test_a05_actor_provider_failure_no_success_callback(a05_actor_stack):
    actor = a05_actor_stack["actor"]
    data_client = a05_actor_stack["data_client"]
    fake_conn = a05_actor_stack["fake_conn"]

    fake_conn.root.set_copy_ticks_range_override(None)

    start = pd.Timestamp("2023-11-14 22:13:20", tz="UTC")
    end = pd.Timestamp("2023-11-14 22:13:21", tz="UTC")
    req_id = actor.request_trade_ticks(
        instrument_id=_WIN_DOLLAR_ID,
        start=start,
        end=end,
        limit=0,
        client_id=data_client.id,
        callback=actor.on_request_complete,
    )

    await asyncio.sleep(_OBSERVE_SECS)
    assert actor.completions == []
    assert actor.historical == []
    assert actor.is_pending_request(req_id)

    # Explicit harness cleanup for the orphan pending request (no error DataResponse).
    actor.stop()
    a05_actor_stack["engine"].stop()
