"""
test_data_client_external_rpyc.py
Nautilus-level data client integration tests for EXTERNAL_RPYC mode.

Exercises the path:
    MT5LiveDataClientFactory.create(...)
    → MetaTrader5DataClient._connect()
    → MetaTrader5InstrumentProvider.initialize()
    → MetaTrader5DataClient._subscribe_quote_ticks()
    → MetaTrader5Client.subscribe_ticks()     [partial: no live stream]
    → MetaTrader5DataClient._subscribe_bars()
    → MetaTrader5Client.subscribe_historical_bars()  [partial: no live stream]

No real MT5, no live env vars.

Capability notes (current state):
- Instrument loading via provider: Supported (full parse_instrument pipeline)
- QuoteTick subscription: Partial — subscription is registered but ticks do not
  flow without a real RPyC streaming server.
- Bar subscription: Partial — same reason.
"""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from nautilus_trader.data.messages import SubscribeBars, SubscribeQuoteTicks
from nautilus_trader.model.data import BarType, BarSpecification
from nautilus_trader.model.enums import AggregationSource, BarAggregation, PriceType
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.core.uuid import UUID4

from nautilus_mt5.client.types import MT5TerminalAccessMode
from nautilus_mt5.config import (
    ExternalRPyCTerminalConfig,
    MetaTrader5DataClientConfig,
    MetaTrader5InstrumentProviderConfig,
)
from nautilus_mt5.constants import MT5_VENUE
from nautilus_mt5.data_types import MT5Symbol
from nautilus_mt5.factories import MT5LiveDataClientFactory
from nautilus_mt5.venue_profile import TICKMILL_DEMO_PROFILE


_RPYC_CONFIG = ExternalRPyCTerminalConfig(host="127.0.0.1", port=18812)
_VENUE = Venue("METATRADER_5")
_USTEC_ID = InstrumentId(Symbol("USTEC"), _VENUE)


def _data_config(*symbols: str) -> MetaTrader5DataClientConfig:
    load = frozenset(MT5Symbol(symbol=s) for s in symbols) if symbols else None
    return MetaTrader5DataClientConfig(
        client_id=1,
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=_RPYC_CONFIG,
        venue_profile=TICKMILL_DEMO_PROFILE,
        instrument_provider=MetaTrader5InstrumentProviderConfig(
            load_symbols=load,
        ),
    )


@pytest.mark.asyncio
async def test_data_client_connect_pipeline(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    _connect() on the data client runs the full Factory → MT5Client → fake pipeline
    without raising.  The underlying MT5Client's fake RPyC connection is used.
    """
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=_data_config(),
        msgbus=msgbus, cache=cache, clock=clock,
    )

    # _connect() calls the full pipeline: self._client._connect() + provider.initialize()
    await data_client._connect()

    # No exception means the pipeline is wired correctly end-to-end.
    # The underlying MT5Client received an initialize() call via fake RPyC.
    assert data_client._client is not None


@pytest.mark.asyncio
async def test_data_client_loads_ustec_on_connect(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    When load_symbols includes USTEC, _connect() populates the Nautilus cache with
    a parsed USTEC instrument.
    """
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=_data_config("USTEC"),
        msgbus=msgbus, cache=cache, clock=clock,
    )

    await data_client._connect()

    instrument = data_client._cache.instrument(_USTEC_ID)
    assert instrument is not None, "USTEC instrument not found in Nautilus cache after _connect()"
    assert instrument.id.symbol.value == "USTEC"


@pytest.mark.asyncio
async def test_data_client_subscribe_quote_ticks_reaches_mt5_client(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    _subscribe_quote_ticks() calls subscribe_ticks() on MetaTrader5Client
    when the instrument is in the cache.

    Capability: Partial — subscription is attempted; live ticks require a real gateway.
    """
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=_data_config("USTEC"),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await data_client._connect()

    subscribe_ticks_calls = []

    async def _spy_subscribe_ticks(**kwargs):
        subscribe_ticks_calls.append(kwargs)

    data_client._client.subscribe_ticks = _spy_subscribe_ticks

    command = SubscribeQuoteTicks(
        client_id=data_client.id,
        venue=None,
        instrument_id=_USTEC_ID,
        command_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )
    await data_client._subscribe_quote_ticks(command)

    assert len(subscribe_ticks_calls) == 1
    assert subscribe_ticks_calls[0]["instrument_id"] == _USTEC_ID
    assert subscribe_ticks_calls[0]["tick_type"] == "BidAsk"


@pytest.mark.asyncio
async def test_data_client_subscribe_quote_ticks_unknown_instrument_logs_error(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    _subscribe_quote_ticks() with an instrument not in cache logs an error
    and does NOT call subscribe_ticks on the MT5 client.
    """
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=_data_config(),  # no load_symbols
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await data_client._connect()

    subscribe_ticks_calls = []

    async def _spy_subscribe_ticks(**kwargs):
        subscribe_ticks_calls.append(kwargs)

    data_client._client.subscribe_ticks = _spy_subscribe_ticks

    unknown_id = InstrumentId(Symbol("UNKNOWN"), _VENUE)
    command = SubscribeQuoteTicks(
        client_id=data_client.id,
        venue=None,
        instrument_id=unknown_id,
        command_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )
    await data_client._subscribe_quote_ticks(command)

    # subscribe_ticks should NOT have been called
    assert len(subscribe_ticks_calls) == 0


@pytest.mark.asyncio
async def test_data_client_subscribe_bars_reaches_mt5_client(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    _subscribe_bars() calls subscribe_historical_bars() on MetaTrader5Client
    when the instrument is in the cache.

    Capability: Partial — bars do not flow without a real streaming source.
    """
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=_data_config("USTEC"),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await data_client._connect()

    subscribe_historical_calls = []

    async def _spy_subscribe_historical_bars(**kwargs):
        subscribe_historical_calls.append(kwargs)

    data_client._client.subscribe_historical_bars = _spy_subscribe_historical_bars

    bar_type = BarType(
        instrument_id=_USTEC_ID,
        bar_spec=BarSpecification(1, BarAggregation.MINUTE, PriceType.MID),
        aggregation_source=AggregationSource.EXTERNAL,
    )
    command = SubscribeBars(
        bar_type=bar_type,
        client_id=data_client.id,
        venue=None,
        command_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )
    await data_client._subscribe_bars(command)

    assert len(subscribe_historical_calls) == 1
    assert subscribe_historical_calls[0]["bar_type"] == bar_type
