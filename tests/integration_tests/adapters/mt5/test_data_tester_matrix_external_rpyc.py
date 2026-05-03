"""
test_data_tester_matrix_external_rpyc.py
=========================================
Tier 1 DataTester matrix for the MT5 adapter — EXTERNAL_RPYC mode.

Exercises the full path:
    MT5LiveDataClientFactory → MetaTrader5DataClient
    → MetaTrader5InstrumentProvider → FakeMT5RPyCConnection (deterministic fake)

No real MT5 terminal, gateway, or network is required.

TC coverage:
  TC-D01  Load specific instrument via provider (USTEC)
  TC-D02  Subscribe all instruments — unsupported; logs warning, no raise
  TC-D03  Request instrument via data client _request_instrument()
  TC-D10  Order book subscription — Unsupported; logs warning, no raise
  TC-D20  Subscribe QuoteTicks — subscription reaches MT5Client.subscribe_ticks()
  TC-D21  Historical QuoteTicks — wiring + end-to-end: QuoteTick objects reach _handle_quote_ticks
  TC-D30  TradeTick — explicit capability decision documented
  TC-D40  Request historical bars — wiring + end-to-end: Bar objects reach _handle_bars
  TC-D41  Subscribe bars — non-5s path (subscribe_historical_bars) + 5s path (subscribe_realtime_bars)
  TC-D70  Unsubscribe on stop — _unsubscribe_quote_ticks / _unsubscribe_bars routes
  TC-D71  Custom subscribe params — explicitly not supported; documented
  TC-D72  Custom request params — explicitly not supported; documented

TC NOT covered (documented explicitly):
  TC-D30/D31  TradeTick — Partial/Undecided; copy_ticks_* maps to QuoteTick, not TradeTick

Markers: @pytest.mark.data_tester
"""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from nautilus_trader.core.uuid import UUID4
from nautilus_trader.data.messages import (
    RequestBars,
    RequestInstrument,
    RequestQuoteTicks,
    RequestTradeTicks,
    SubscribeBars,
    SubscribeQuoteTicks,
    SubscribeTradeTicks,
    UnsubscribeBars,
    UnsubscribeQuoteTicks,
    UnsubscribeTradeTicks,
)
from nautilus_trader.model.data import BarSpecification, BarType
from nautilus_trader.model.enums import AggregationSource, BarAggregation, PriceType
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue

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

_VENUE = Venue("METATRADER_5")
_USTEC_ID = InstrumentId(Symbol("USTEC"), _VENUE)
_EURUSD_ID = InstrumentId(Symbol("EURUSD"), _VENUE)

_BAR_TYPE = BarType(
    instrument_id=_USTEC_ID,
    bar_spec=BarSpecification(1, BarAggregation.MINUTE, PriceType.BID),
    aggregation_source=AggregationSource.EXTERNAL,
)


def _data_config(*symbols: str) -> MetaTrader5DataClientConfig:
    load = frozenset(MT5Symbol(symbol=s) for s in symbols) if symbols else None
    return MetaTrader5DataClientConfig(
        client_id=1,
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=ExternalRPyCTerminalConfig(host="127.0.0.1", port=18812),
        venue_profile=TICKMILL_DEMO_PROFILE,
        instrument_provider=MetaTrader5InstrumentProviderConfig(
            load_symbols=load,
        ),
    )


# ---------------------------------------------------------------------------
# TC-D01: Load specific instrument
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.data_tester
async def test_tc_d01_load_specific_instrument(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    TC-D01: InstrumentProvider.initialize() loads USTEC from the fake bridge.
    Instrument appears in list_all() after connect.
    """
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=_data_config("USTEC"),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await data_client._connect()

    instruments = data_client.instrument_provider.list_all()
    instrument_ids = [i.id for i in instruments]
    assert _USTEC_ID in instrument_ids, (
        f"TC-D01: USTEC not loaded by provider. Got: {instrument_ids}"
    )


# ---------------------------------------------------------------------------
# TC-D03: Request specific instrument
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.data_tester
async def test_tc_d03_request_instrument(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    TC-D03: _request_instrument() loads USTEC into the cache on demand.
    """
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=_data_config("USTEC"),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await data_client._connect()

    req = RequestInstrument(
        instrument_id=_USTEC_ID,
        start=None,
        end=None,
        client_id=data_client.id,
        venue=_VENUE,
        callback=None,
        request_id=UUID4(),
        ts_init=clock.timestamp_ns(),
        params=None,
    )
    await data_client._request_instrument(req)

    cached = cache.instrument(_USTEC_ID)
    assert cached is not None, "TC-D03: USTEC not in cache after _request_instrument()"
    assert cached.id == _USTEC_ID


# ---------------------------------------------------------------------------
# TC-D20: Subscribe QuoteTicks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.data_tester
async def test_tc_d20_subscribe_quote_ticks_reaches_mt5_client(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    TC-D20: _subscribe_quote_ticks() calls MT5Client.subscribe_ticks() with
    tick_type='BidAsk'. Validates subscription wiring (not live tick delivery).
    """
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=_data_config("USTEC"),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await data_client._connect()

    subscribe_calls: list = []

    async def _spy_subscribe_ticks(instrument_id, symbol, tick_type, ignore_size=False):
        subscribe_calls.append({"instrument_id": instrument_id, "tick_type": tick_type})

    data_client._client.subscribe_ticks = _spy_subscribe_ticks

    cmd = SubscribeQuoteTicks(
        instrument_id=_USTEC_ID,
        client_id=data_client.id,
        venue=None,
        command_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )
    await data_client._subscribe_quote_ticks(cmd)

    assert len(subscribe_calls) == 1, "TC-D20: subscribe_ticks not called"
    assert subscribe_calls[0]["instrument_id"] == _USTEC_ID
    assert subscribe_calls[0]["tick_type"] == "BidAsk"


@pytest.mark.asyncio
@pytest.mark.data_tester
async def test_tc_d20_subscribe_quote_ticks_unknown_instrument_no_call(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    TC-D20 (error path): subscription for unknown instrument does not call
    subscribe_ticks (instrument not in cache → logged error).
    """
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=_data_config(),  # no symbols loaded
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await data_client._connect()

    subscribe_calls: list = []

    async def _spy(*a, **kw):
        subscribe_calls.append(a)

    data_client._client.subscribe_ticks = _spy

    cmd = SubscribeQuoteTicks(
        instrument_id=_USTEC_ID,
        client_id=data_client.id,
        venue=None,
        command_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )
    await data_client._subscribe_quote_ticks(cmd)

    assert len(subscribe_calls) == 0, (
        "TC-D20 error path: subscribe_ticks should not be called for unknown instrument"
    )


# ---------------------------------------------------------------------------
# TC-D21: Historical QuoteTicks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.data_tester
async def test_tc_d21_request_quote_ticks_reaches_mt5_client(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    TC-D21: _request_quote_ticks() calls MT5Client.get_historical_ticks().
    Validates request wiring through the data client.
    Note: The fake bridge exposed_copy_ticks_from / exposed_copy_ticks_range
    feed through MetaTrader5Client.get_historical_ticks internally.
    """
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=_data_config("USTEC"),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await data_client._connect()

    historical_tick_calls: list = []
    original = data_client._client.get_historical_ticks

    async def _spy_historical_ticks(*args, **kwargs):
        historical_tick_calls.append({"args": args, "kwargs": kwargs})
        return []  # empty — avoids QuoteTick parse path

    data_client._client.get_historical_ticks = _spy_historical_ticks

    req = RequestQuoteTicks(
        instrument_id=_USTEC_ID,
        start=None,
        end=None,
        limit=10,
        client_id=data_client.id,
        venue=_VENUE,
        callback=None,
        request_id=UUID4(),
        ts_init=clock.timestamp_ns(),
        params=None,
    )
    await data_client._request_quote_ticks(req)

    assert len(historical_tick_calls) >= 1, (
        "TC-D21: get_historical_ticks not called by _request_quote_ticks()"
    )


# ---------------------------------------------------------------------------
# TC-D30/D31: TradeTick — capability decision + behavioral coverage
# ---------------------------------------------------------------------------

@pytest.mark.data_tester
def test_tc_d30_trade_tick_unsupported_decision():
    """
    TC-D30: Capability decision — TradeTick is Unsupported for Tickmill instruments.

    This is now formally declared in TICKMILL_DEMO_PROFILE:
    - SYMBOL_CALC_MODE_FOREX (0):    trade_ticks = UNSUPPORTED  (FX pairs)
    - SYMBOL_CALC_MODE_CFD (2):      trade_ticks = UNSUPPORTED
    - SYMBOL_CALC_MODE_CFDINDEX (3): trade_ticks = UNSUPPORTED  (USTEC, etc.)

    The adapter enforces this via profile-based capability checks in
    _subscribe_trade_ticks() and _request_trade_ticks(). Neither operation
    will proceed past the profile gate for Tickmill instruments.

    Confirmed live 2026-05-02: 'last' field is 0.0 on Tickmill-Demo for FX and
    index CFDs, making TradeTick data semantically invalid even if subscribed.
    """
    from nautilus_mt5.venue_profile import (
        TICKMILL_DEMO_PROFILE,
        CapabilityStatus,
        SYMBOL_CALC_MODE_FOREX,
        SYMBOL_CALC_MODE_CFDINDEX,
    )

    forex_cap = TICKMILL_DEMO_PROFILE.get_capability(SYMBOL_CALC_MODE_FOREX)
    assert forex_cap.trade_ticks == CapabilityStatus.UNSUPPORTED, (
        "FOREX trade_ticks must be UNSUPPORTED in TICKMILL_DEMO_PROFILE"
    )

    cfdindex_cap = TICKMILL_DEMO_PROFILE.get_capability(SYMBOL_CALC_MODE_CFDINDEX)
    assert cfdindex_cap.trade_ticks == CapabilityStatus.UNSUPPORTED, (
        "CFDINDEX trade_ticks must be UNSUPPORTED in TICKMILL_DEMO_PROFILE"
    )


@pytest.mark.asyncio
@pytest.mark.data_tester
async def test_tc_d30_subscribe_trade_ticks_unknown_instrument_no_call(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    TC-D30: _subscribe_trade_ticks() for unknown instrument logs error
    and does not call subscribe_ticks.
    """
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=_data_config(),  # no symbols loaded
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await data_client._connect()

    subscribe_calls: list = []

    async def _spy(*a, **kw):
        subscribe_calls.append(a)

    data_client._client.subscribe_ticks = _spy

    cmd = SubscribeTradeTicks(
        instrument_id=_USTEC_ID,
        client_id=data_client.id,
        venue=None,
        command_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )
    await data_client._subscribe_trade_ticks(cmd)

    assert len(subscribe_calls) == 0, (
        "TC-D30: subscribe_ticks must not be called for unknown instrument"
    )


@pytest.mark.asyncio
@pytest.mark.data_tester
async def test_tc_d30_subscribe_trade_ticks_known_instrument_profile_rejects(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    TC-D30: _subscribe_trade_ticks() for a known CFDINDEX instrument (USTEC)
    is rejected by the VenueProfile (trade_ticks=UNSUPPORTED for CFDINDEX
    in TICKMILL_DEMO_PROFILE). subscribe_ticks() is never called.

    This is the correct, profile-enforced behaviour for Tickmill instruments.
    """
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=_data_config("USTEC"),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await data_client._connect()

    subscribe_calls: list = []

    async def _spy_subscribe_ticks(instrument_id, symbol, tick_type, ignore_size=False):
        subscribe_calls.append({"instrument_id": instrument_id, "tick_type": tick_type})

    data_client._client.subscribe_ticks = _spy_subscribe_ticks

    cmd = SubscribeTradeTicks(
        instrument_id=_USTEC_ID,
        client_id=data_client.id,
        venue=None,
        command_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )
    await data_client._subscribe_trade_ticks(cmd)

    assert len(subscribe_calls) == 0, (
        "TC-D30: subscribe_ticks must NOT be called — CFDINDEX trade_ticks is UNSUPPORTED "
        "in TICKMILL_DEMO_PROFILE (profile gate should reject before reaching client)"
    )


@pytest.mark.asyncio
@pytest.mark.data_tester
async def test_tc_d30_unsubscribe_trade_ticks_routes_to_all_last(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    TC-D30: _unsubscribe_trade_ticks() calls MT5Client.unsubscribe_ticks()
    with tick_type='AllLast'.
    """
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=_data_config("USTEC"),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await data_client._connect()

    unsub_calls: list = []

    async def _spy_unsubscribe_ticks(instrument_id, tick_type):
        unsub_calls.append({"instrument_id": instrument_id, "tick_type": tick_type})

    data_client._client.unsubscribe_ticks = _spy_unsubscribe_ticks

    cmd = UnsubscribeTradeTicks(
        instrument_id=_USTEC_ID,
        client_id=data_client.id,
        venue=None,
        command_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )
    await data_client._unsubscribe_trade_ticks(cmd)

    assert len(unsub_calls) == 1, (
        "TC-D30: unsubscribe_ticks not called by _unsubscribe_trade_ticks()"
    )
    assert unsub_calls[0]["tick_type"] == "AllLast", (
        "TC-D30: tick_type must be 'AllLast' for TradeTick unsubscription"
    )
    assert unsub_calls[0]["instrument_id"] == _USTEC_ID


@pytest.mark.asyncio
@pytest.mark.data_tester
async def test_tc_d31_request_trade_ticks_forex_profile_rejects(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    TC-D31: _request_trade_ticks() for EURUSD (FOREX / CurrencyPair) is rejected
    by the VenueProfile gate before reaching get_historical_ticks().

    With TICKMILL_DEMO_PROFILE, EURUSD is now parsed as CurrencyPair
    (trade_calc_mode=0, SYMBOL_CALC_MODE_FOREX → nautilus_instrument_type=CurrencyPair).
    The profile declares trade_ticks=UNSUPPORTED for FOREX, so the request is
    short-circuited by the profile check. The dead-code isinstance(CurrencyPair)
    block is replaced by this clean profile-based gate.
    """
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=_data_config("EURUSD"),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await data_client._connect()

    # Verify EURUSD is now parsed as CurrencyPair (not Cfd).
    from nautilus_trader.model.instruments import CurrencyPair
    eurusd_instrument = data_client._cache.instrument(_EURUSD_ID)
    assert eurusd_instrument is not None, "TC-D31: EURUSD not in cache after connect"
    assert isinstance(eurusd_instrument, CurrencyPair), (
        f"TC-D31: EURUSD must be CurrencyPair with TICKMILL_DEMO_PROFILE, got {type(eurusd_instrument).__name__}"
    )

    historical_tick_calls: list = []
    handle_calls: list = []

    async def _stub(*a, **kw):
        historical_tick_calls.append(a)
        return []

    def _spy_handle(instrument_id, ticks, correlation_id):
        handle_calls.append(ticks)

    data_client._client.get_historical_ticks = _stub
    data_client._handle_trade_ticks = _spy_handle

    req = RequestTradeTicks(
        instrument_id=_EURUSD_ID,
        start=None,
        end=None,
        limit=1,
        client_id=data_client.id,
        venue=_VENUE,
        callback=None,
        request_id=UUID4(),
        ts_init=clock.timestamp_ns(),
        params=None,
    )
    await data_client._request_trade_ticks(req)

    # Profile gate rejects before reaching get_historical_ticks.
    assert len(historical_tick_calls) == 0, (
        "TC-D31: get_historical_ticks must NOT be called — FOREX trade_ticks is UNSUPPORTED "
        "in TICKMILL_DEMO_PROFILE (profile gate rejects before the client call)"
    )
    assert len(handle_calls) == 0, (
        "TC-D31: _handle_trade_ticks must NOT be called when profile rejects"
    )


@pytest.mark.asyncio
@pytest.mark.data_tester
async def test_tc_d31_request_trade_ticks_cfd_profile_rejects(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    TC-D31: _request_trade_ticks() for USTEC (CFDINDEX / Cfd) is rejected by the
    VenueProfile gate before reaching get_historical_ticks().

    TICKMILL_DEMO_PROFILE declares trade_ticks=UNSUPPORTED for CFDINDEX.
    Confirmed live 2026-05-02: USTEC on Tickmill-Demo has last=0.0, making
    TradeTick data semantically invalid even if fetched.
    """
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=_data_config("USTEC"),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await data_client._connect()

    historical_tick_calls: list = []
    handle_calls: list = []

    async def _stub(*a, **kw):
        historical_tick_calls.append(a)
        return []

    def _spy_handle(instrument_id, ticks, correlation_id):
        handle_calls.append(ticks)

    data_client._client.get_historical_ticks = _stub
    data_client._handle_trade_ticks = _spy_handle

    req = RequestTradeTicks(
        instrument_id=_USTEC_ID,
        start=None,
        end=None,
        limit=1,
        client_id=data_client.id,
        venue=_VENUE,
        callback=None,
        request_id=UUID4(),
        ts_init=clock.timestamp_ns(),
        params=None,
    )
    await data_client._request_trade_ticks(req)

    # Profile gate rejects before reaching get_historical_ticks.
    assert len(historical_tick_calls) == 0, (
        "TC-D31: get_historical_ticks must NOT be called — CFDINDEX trade_ticks is UNSUPPORTED "
        "in TICKMILL_DEMO_PROFILE"
    )
    assert len(handle_calls) == 0, (
        "TC-D31: _handle_trade_ticks must NOT be called when profile rejects"
    )


# ---------------------------------------------------------------------------
# TC-D40: Request historical bars
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.data_tester
async def test_tc_d40_request_historical_bars_reaches_mt5_client(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    TC-D40: _request_bars() calls MT5Client.get_historical_bars().
    Validates the bars request wiring through the data client.
    """
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=_data_config("USTEC"),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await data_client._connect()

    bar_calls: list = []

    async def _spy_get_bars(*args, **kwargs):
        bar_calls.append({"args": args, "kwargs": kwargs})
        return []  # empty — avoids Bar parse path

    data_client._client.get_historical_bars = _spy_get_bars

    req = RequestBars(
        bar_type=_BAR_TYPE,
        start=None,
        end=None,
        limit=5,
        client_id=data_client.id,
        venue=_VENUE,
        callback=None,
        request_id=UUID4(),
        ts_init=clock.timestamp_ns(),
        params=None,
    )
    await data_client._request_bars(req)

    assert len(bar_calls) >= 1, (
        "TC-D40: get_historical_bars not called by _request_bars()"
    )


# ---------------------------------------------------------------------------
# TC-D41: Subscribe bars
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.data_tester
async def test_tc_d41_subscribe_bars_reaches_mt5_client(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    TC-D41: _subscribe_bars() calls MT5Client.subscribe_historical_bars()
    for non-5s bar types (the historical subscription path).
    """
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=_data_config("USTEC"),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await data_client._connect()

    subscribe_bar_calls: list = []

    async def _spy_sub_bars(*args, **kwargs):
        subscribe_bar_calls.append({"args": args, "kwargs": kwargs})

    data_client._client.subscribe_historical_bars = _spy_sub_bars

    cmd = SubscribeBars(
        bar_type=_BAR_TYPE,
        client_id=data_client.id,
        venue=None,
        command_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )
    await data_client._subscribe_bars(cmd)

    assert len(subscribe_bar_calls) == 1, (
        "TC-D41: subscribe_historical_bars not called by _subscribe_bars()"
    )
    assert subscribe_bar_calls[0]["kwargs"].get("bar_type") == _BAR_TYPE or (
        len(subscribe_bar_calls[0]["args"]) > 0
        and subscribe_bar_calls[0]["args"][0] == _BAR_TYPE
    ), "TC-D41: wrong bar_type passed to subscribe_historical_bars"


# ---------------------------------------------------------------------------
# TC-D10–D15: Order book — Unsupported
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.data_tester
async def test_tc_d10_order_book_unsupported_logs_warning(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    TC-D10–D15: Order book subscription logs a warning and does not raise.
    The adapter explicitly does not support order book.
    """
    from nautilus_trader.data.messages import SubscribeOrderBook
    from nautilus_trader.model.enums import BookType

    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=_data_config("USTEC"),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await data_client._connect()

    from nautilus_trader.model.data import OrderBookDelta
    cmd = SubscribeOrderBook(
        instrument_id=_USTEC_ID,
        book_data_type=OrderBookDelta,
        book_type=BookType.L1_MBP,
        client_id=data_client.id,
        venue=None,
        command_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )
    # Must not raise — logs warning instead
    await data_client._subscribe_order_book_deltas(cmd)
    await data_client._subscribe_order_book_snapshots(cmd)


# ---------------------------------------------------------------------------
# TC-D02: Subscribe all instruments — unsupported, logs warning
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.data_tester
async def test_tc_d02_subscribe_instruments_logs_warning_no_raise(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    TC-D02: _subscribe_instruments() is documented as unsupported.
    Must log a warning and return without raising any exception.
    """
    from nautilus_trader.data.messages import SubscribeInstruments

    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=_data_config("USTEC"),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await data_client._connect()

    cmd = SubscribeInstruments(
        client_id=data_client.id,
        venue=_VENUE,
        command_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )
    # Must not raise
    await data_client._subscribe_instruments(cmd)
    # No assertion other than "no exception" — the log warning is the only side-effect.


# ---------------------------------------------------------------------------
# TC-D40 (end-to-end): Request historical bars → Bar objects reach _handle_bars
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.data_tester
async def test_tc_d40_request_historical_bars_delivers_bar_objects(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    TC-D40 (end-to-end): _request_bars() receives Bar objects from the client
    and forwards them to _handle_bars.  Validates the dispatch path, not only
    that get_historical_bars is called.
    """
    import pandas as pd
    from nautilus_trader.model.data import Bar, BarSpecification, BarType
    from nautilus_trader.model.enums import AggregationSource, BarAggregation, PriceType

    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=_data_config("USTEC"),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await data_client._connect()

    instrument = cache.instrument(_USTEC_ID)
    assert instrument is not None, "USTEC must be in cache after connect"

    # Build a real Bar using the instrument's price/qty precision
    ts_event = 1_700_000_000_000_000_000  # 2023-11-14 UTC in ns
    fake_bar = Bar(
        bar_type=_BAR_TYPE,
        open=instrument.make_price(18490.00),
        high=instrument.make_price(18510.00),
        low=instrument.make_price(18480.00),
        close=instrument.make_price(18500.00),
        volume=instrument.make_qty(100.0),
        ts_event=ts_event,
        ts_init=ts_event,
    )

    handle_bars_calls: list = []

    def _spy_handle_bars(bar_type, bars, partial, correlation_id):
        handle_bars_calls.append({"bar_type": bar_type, "bars": bars})

    data_client._handle_bars = _spy_handle_bars

    async def _stub_get_bars(**kwargs):
        return [fake_bar]

    data_client._client.get_historical_bars = _stub_get_bars

    req = RequestBars(
        bar_type=_BAR_TYPE,
        start=None,
        end=None,
        limit=1,
        client_id=data_client.id,
        venue=_VENUE,
        callback=None,
        request_id=UUID4(),
        ts_init=clock.timestamp_ns(),
        params=None,
    )
    await data_client._request_bars(req)

    assert len(handle_bars_calls) == 1, (
        "TC-D40 (e2e): _handle_bars not called when get_historical_bars returns Bar objects"
    )
    delivered = handle_bars_calls[0]["bars"]
    assert len(delivered) == 1, "TC-D40 (e2e): expected exactly 1 Bar"
    assert isinstance(delivered[0], Bar), "TC-D40 (e2e): delivered item is not a Bar"
    assert delivered[0].bar_type == _BAR_TYPE, "TC-D40 (e2e): wrong bar_type on delivered Bar"


# ---------------------------------------------------------------------------
# TC-D41 (5s path): Subscribe bars → subscribe_realtime_bars for 5s bars
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.data_tester
async def test_tc_d41_subscribe_5s_bars_uses_realtime_path(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    TC-D41 (5s path): When bar_spec.timedelta == 5s, _subscribe_bars() must
    dispatch to MT5Client.subscribe_realtime_bars(), not subscribe_historical_bars.
    """
    from nautilus_trader.model.data import BarSpecification, BarType
    from nautilus_trader.model.enums import AggregationSource, BarAggregation, PriceType

    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=_data_config("USTEC"),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await data_client._connect()

    _5S_BAR_TYPE = BarType(
        instrument_id=_USTEC_ID,
        bar_spec=BarSpecification(5, BarAggregation.SECOND, PriceType.BID),
        aggregation_source=AggregationSource.EXTERNAL,
    )

    realtime_calls: list = []
    historical_calls: list = []

    async def _spy_realtime(**kwargs):
        realtime_calls.append(kwargs)

    async def _spy_historical(**kwargs):
        historical_calls.append(kwargs)

    data_client._client.subscribe_realtime_bars = _spy_realtime
    data_client._client.subscribe_historical_bars = _spy_historical

    cmd = SubscribeBars(
        bar_type=_5S_BAR_TYPE,
        client_id=data_client.id,
        venue=None,
        command_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )
    await data_client._subscribe_bars(cmd)

    assert len(realtime_calls) == 1, (
        "TC-D41 (5s): subscribe_realtime_bars should be called for 5s bar type"
    )
    assert len(historical_calls) == 0, (
        "TC-D41 (5s): subscribe_historical_bars must NOT be called for 5s bar type"
    )


# ===========================================================================
# GROUP B — TC-D21 end-to-end + TC-D70/D71/D72 lifecycle
# ===========================================================================

# ---------------------------------------------------------------------------
# TC-D21 (end-to-end): Historical QuoteTicks → QuoteTick objects reach _handle_quote_ticks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.data_tester
async def test_tc_d21_request_quote_ticks_delivers_quote_tick_objects(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    TC-D21 (end-to-end): _request_quote_ticks() receives QuoteTick objects from
    get_historical_ticks and forwards them to _handle_quote_ticks.
    Validates the full dispatch path: client → data layer → handler.
    """
    from nautilus_trader.model.data import QuoteTick
    from nautilus_trader.model.objects import Price, Quantity

    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=_data_config("USTEC"),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await data_client._connect()

    instrument = cache.instrument(_USTEC_ID)
    assert instrument is not None, "USTEC must be in cache after connect"

    ts = 1_700_000_000_000_000_000  # ns
    fake_tick = QuoteTick(
        instrument_id=_USTEC_ID,
        bid_price=instrument.make_price(18500.00),
        ask_price=instrument.make_price(18500.50),
        bid_size=instrument.make_qty(1.0),
        ask_size=instrument.make_qty(1.0),
        ts_event=ts,
        ts_init=ts,
    )

    handle_calls: list = []

    def _spy_handle_quote_ticks(instrument_id, ticks, correlation_id):
        handle_calls.append({"instrument_id": instrument_id, "ticks": ticks})

    data_client._handle_quote_ticks = _spy_handle_quote_ticks

    # Return the tick on the first call, then [] to break the accumulation loop.
    _call_count = {"n": 0}

    async def _stub_get_historical_ticks(*args, **kwargs):
        _call_count["n"] += 1
        return [fake_tick] if _call_count["n"] == 1 else []

    data_client._client.get_historical_ticks = _stub_get_historical_ticks

    req = RequestQuoteTicks(
        instrument_id=_USTEC_ID,
        start=None,
        end=None,
        limit=1,
        client_id=data_client.id,
        venue=_VENUE,
        callback=None,
        request_id=UUID4(),
        ts_init=clock.timestamp_ns(),
        params=None,
    )
    await data_client._request_quote_ticks(req)

    assert len(handle_calls) == 1, (
        "TC-D21 (e2e): _handle_quote_ticks not called when get_historical_ticks returns QuoteTick objects"
    )
    delivered = handle_calls[0]["ticks"]
    assert len(delivered) == 1, "TC-D21 (e2e): expected exactly 1 QuoteTick"
    assert isinstance(delivered[0], QuoteTick), "TC-D21 (e2e): delivered item is not a QuoteTick"
    assert delivered[0].instrument_id == _USTEC_ID, "TC-D21 (e2e): wrong instrument_id on QuoteTick"


@pytest.mark.asyncio
@pytest.mark.data_tester
async def test_tc_d21_start_none_uses_tick_capacity_not_request_limit(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    TC-D21: When request.start=None, _handle_ticks_request replaces 'limit'
    with self._cache.tick_capacity (typically 10 000) instead of the request's
    'limit' field.

    Observable: with request.limit=1 and start=None, the stub is called TWICE
    (first call → 1 tick, second call → [] → break).  If limit=1 had been
    honoured, the loop would have exited after the first call (len==1 >= 1).
    """
    from nautilus_trader.model.data import QuoteTick
    from nautilus_trader.model.objects import Price, Quantity

    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=_data_config("USTEC"),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await data_client._connect()

    instrument = cache.instrument(_USTEC_ID)
    ts = 1_700_000_000_000_000_000
    fake_tick = QuoteTick(
        instrument_id=_USTEC_ID,
        bid_price=instrument.make_price(18500.00),
        ask_price=instrument.make_price(18500.50),
        bid_size=instrument.make_qty(1.0),
        ask_size=instrument.make_qty(1.0),
        ts_event=ts,
        ts_init=ts,
    )

    call_count = {"n": 0}

    async def _stub(symbol, tick_type, **kwargs):
        call_count["n"] += 1
        return [fake_tick] if call_count["n"] == 1 else []

    data_client._client.get_historical_ticks = _stub

    handle_calls: list = []

    def _spy_handle(instrument_id, ticks, correlation_id):
        handle_calls.append(ticks)

    data_client._handle_quote_ticks = _spy_handle

    req = RequestQuoteTicks(
        instrument_id=_USTEC_ID,
        start=None,
        end=None,
        limit=1,  # should be ignored — tick_capacity takes over
        client_id=data_client.id,
        venue=_VENUE,
        callback=None,
        request_id=UUID4(),
        ts_init=clock.timestamp_ns(),
        params=None,
    )
    await data_client._request_quote_ticks(req)

    assert call_count["n"] == 2, (
        "TC-D21: get_historical_ticks should be called twice when start=None — "
        "once to fetch ticks, once more (returns []) confirming tick_capacity "
        "is used as limit instead of request.limit=1"
    )
    assert len(handle_calls) == 1
    assert len(handle_calls[0]) == 1, (
        "TC-D21: 1 tick should have been delivered (all returned by stub)"
    )


@pytest.mark.asyncio
@pytest.mark.data_tester
async def test_tc_d21_empty_result_does_not_call_handle_quote_ticks(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    TC-D21: When get_historical_ticks returns an empty list, _handle_quote_ticks
    is NOT called and the adapter logs a warning instead.

    This is the 'no data available' path — the adapter must not deliver an empty
    QuoteTick batch to the engine.
    """
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=_data_config("USTEC"),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await data_client._connect()

    async def _stub_empty(*a, **kw):
        return []

    data_client._client.get_historical_ticks = _stub_empty

    handle_calls: list = []

    def _spy_handle(instrument_id, ticks, correlation_id):
        handle_calls.append(ticks)

    data_client._handle_quote_ticks = _spy_handle

    req = RequestQuoteTicks(
        instrument_id=_USTEC_ID,
        start=None,
        end=None,
        limit=10,
        client_id=data_client.id,
        venue=_VENUE,
        callback=None,
        request_id=UUID4(),
        ts_init=clock.timestamp_ns(),
        params=None,
    )
    await data_client._request_quote_ticks(req)

    assert len(handle_calls) == 0, (
        "TC-D21: _handle_quote_ticks must NOT be called when get_historical_ticks "
        "returns no data — adapter should log a warning and return early"
    )


@pytest.mark.asyncio
@pytest.mark.data_tester
async def test_tc_d21_correlation_id_forwarded_to_handle_quote_ticks(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    TC-D21: The correlation_id from the RequestQuoteTicks is forwarded unchanged
    to _handle_quote_ticks.

    This ensures that the DataEngine can match the response to the original
    request (required for the request/response protocol).
    """
    from nautilus_trader.model.data import QuoteTick

    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=_data_config("USTEC"),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await data_client._connect()

    instrument = cache.instrument(_USTEC_ID)
    ts = 1_700_000_000_000_000_000
    fake_tick = QuoteTick(
        instrument_id=_USTEC_ID,
        bid_price=instrument.make_price(18500.00),
        ask_price=instrument.make_price(18500.50),
        bid_size=instrument.make_qty(1.0),
        ask_size=instrument.make_qty(1.0),
        ts_event=ts,
        ts_init=ts,
    )

    call_count = {"n": 0}

    async def _stub(*a, **kw):
        call_count["n"] += 1
        return [fake_tick] if call_count["n"] == 1 else []

    data_client._client.get_historical_ticks = _stub

    handle_calls: list = []

    def _spy_handle(instrument_id, ticks, correlation_id):
        handle_calls.append({"instrument_id": instrument_id, "correlation_id": correlation_id})

    data_client._handle_quote_ticks = _spy_handle

    request_id = UUID4()
    req = RequestQuoteTicks(
        instrument_id=_USTEC_ID,
        start=None,
        end=None,
        limit=1,
        client_id=data_client.id,
        venue=_VENUE,
        callback=None,
        request_id=request_id,
        ts_init=clock.timestamp_ns(),
        params=None,
    )
    await data_client._request_quote_ticks(req)

    assert len(handle_calls) == 1, "TC-D21: _handle_quote_ticks should be called once"
    assert handle_calls[0]["instrument_id"] == _USTEC_ID, (
        "TC-D21: instrument_id forwarded incorrectly"
    )
    # correlation_id must be forwarded unchanged from the request
    # (may be None in test context without a full DataEngine — that is expected)
    assert handle_calls[0]["correlation_id"] == req.correlation_id, (
        "TC-D21: correlation_id must be forwarded from the request to _handle_quote_ticks unchanged"
    )


# ---------------------------------------------------------------------------
# TC-D70: Unsubscribe routes to the correct MT5Client method
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.data_tester
async def test_tc_d70_unsubscribe_quote_ticks_calls_unsubscribe_ticks(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    TC-D70: _unsubscribe_quote_ticks() calls MT5Client.unsubscribe_ticks()
    with tick_type='BidAsk'. Validates that stop/unsubscribe is wired.
    """
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=_data_config("USTEC"),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await data_client._connect()

    unsub_calls: list = []

    async def _spy_unsubscribe_ticks(instrument_id, tick_type):
        unsub_calls.append({"instrument_id": instrument_id, "tick_type": tick_type})

    data_client._client.unsubscribe_ticks = _spy_unsubscribe_ticks

    cmd = UnsubscribeQuoteTicks(
        instrument_id=_USTEC_ID,
        client_id=data_client.id,
        venue=None,
        command_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )
    await data_client._unsubscribe_quote_ticks(cmd)

    assert len(unsub_calls) == 1, "TC-D70: unsubscribe_ticks not called by _unsubscribe_quote_ticks()"
    assert unsub_calls[0]["instrument_id"] == _USTEC_ID
    assert unsub_calls[0]["tick_type"] == "BidAsk"


@pytest.mark.asyncio
@pytest.mark.data_tester
async def test_tc_d70_unsubscribe_bars_historical_path(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    TC-D70: _unsubscribe_bars() calls MT5Client.unsubscribe_historical_bars()
    for non-5s bar types.
    """
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=_data_config("USTEC"),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await data_client._connect()

    hist_unsub_calls: list = []
    realtime_unsub_calls: list = []

    async def _spy_hist(bar_type):
        hist_unsub_calls.append(bar_type)

    async def _spy_rt(bar_type):
        realtime_unsub_calls.append(bar_type)

    data_client._client.unsubscribe_historical_bars = _spy_hist
    data_client._client.unsubscribe_realtime_bars = _spy_rt

    cmd = UnsubscribeBars(
        bar_type=_BAR_TYPE,   # 1-minute — not 5s
        client_id=data_client.id,
        venue=None,
        command_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )
    await data_client._unsubscribe_bars(cmd)

    assert len(hist_unsub_calls) == 1, (
        "TC-D70: unsubscribe_historical_bars not called for 1-minute bar"
    )
    assert hist_unsub_calls[0] == _BAR_TYPE
    assert len(realtime_unsub_calls) == 0, (
        "TC-D70: unsubscribe_realtime_bars must NOT be called for 1-minute bar"
    )


@pytest.mark.asyncio
@pytest.mark.data_tester
async def test_tc_d70_unsubscribe_bars_realtime_path(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    TC-D70: _unsubscribe_bars() calls MT5Client.unsubscribe_realtime_bars()
    for 5s bar types.
    """
    from nautilus_trader.model.data import BarSpecification, BarType
    from nautilus_trader.model.enums import AggregationSource, BarAggregation, PriceType

    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=_data_config("USTEC"),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await data_client._connect()

    _5S_BAR_TYPE = BarType(
        instrument_id=_USTEC_ID,
        bar_spec=BarSpecification(5, BarAggregation.SECOND, PriceType.BID),
        aggregation_source=AggregationSource.EXTERNAL,
    )

    hist_unsub_calls: list = []
    realtime_unsub_calls: list = []

    async def _spy_hist(bar_type):
        hist_unsub_calls.append(bar_type)

    async def _spy_rt(bar_type):
        realtime_unsub_calls.append(bar_type)

    data_client._client.unsubscribe_historical_bars = _spy_hist
    data_client._client.unsubscribe_realtime_bars = _spy_rt

    cmd = UnsubscribeBars(
        bar_type=_5S_BAR_TYPE,
        client_id=data_client.id,
        venue=None,
        command_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )
    await data_client._unsubscribe_bars(cmd)

    assert len(realtime_unsub_calls) == 1, (
        "TC-D70: unsubscribe_realtime_bars should be called for 5s bar type"
    )
    assert realtime_unsub_calls[0] == _5S_BAR_TYPE
    assert len(hist_unsub_calls) == 0, (
        "TC-D70: unsubscribe_historical_bars must NOT be called for 5s bar type"
    )


# ---------------------------------------------------------------------------
# TC-D71: Custom subscribe params — not supported; documented explicitly
# ---------------------------------------------------------------------------

@pytest.mark.data_tester
def test_tc_d71_custom_subscribe_params_not_supported():
    """
    TC-D71: The nt_mt5 adapter does not expose custom subscribe params in its
    public API. SubscribeBars / SubscribeQuoteTicks accept no adapter-specific
    kwargs beyond the standard Nautilus fields.

    This test documents the explicit capability decision rather than testing
    a runtime path.
    """
    CUSTOM_SUBSCRIBE_PARAMS_SUPPORTED = False
    assert not CUSTOM_SUBSCRIBE_PARAMS_SUPPORTED, (
        "If this assertion fails, add explicit custom-params tests and update "
        "docs/data_capability_matrix.md to Supported."
    )


# ---------------------------------------------------------------------------
# TC-D72: Custom request params — not supported; documented explicitly
# ---------------------------------------------------------------------------

@pytest.mark.data_tester
def test_tc_d72_custom_request_params_not_supported():
    """
    TC-D72: The nt_mt5 adapter does not expose custom request params in its
    public API. RequestBars / RequestQuoteTicks accept no adapter-specific
    kwargs beyond the standard Nautilus fields.

    This test documents the explicit capability decision rather than testing
    a runtime path.
    """
    CUSTOM_REQUEST_PARAMS_SUPPORTED = False
    assert not CUSTOM_REQUEST_PARAMS_SUPPORTED, (
        "If this assertion fails, add explicit custom-params tests and update "
        "docs/data_capability_matrix.md to Supported."
    )
