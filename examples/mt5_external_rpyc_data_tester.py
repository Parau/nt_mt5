"""
mt5_external_rpyc_data_tester.py
=================================
DataTester example for the MT5 adapter via EXTERNAL_RPYC mode.

Covers (Tier 0):
  TC-D01  Load specific instrument (USTEC) via InstrumentProvider
  TC-D03  Request instrument via MetaTrader5DataClient._request_instrument()
  TC-D20  Subscribe QuoteTicks (subscription is registered; ticks flow in live session)
  TC-D40  Request historical bars via MetaTrader5DataClient._request_bars()
  TC-D41  Subscribe bars (historical path via MetaTrader5DataClient._subscribe_bars())

Trade ticks (TC-D30/TC-D31): copy_ticks_* in MT5 returns bid/ask (QuoteTick
semantics).  For CFD indexes like USTEC, 'last' may be unreliable or zero.
TradeTick support is marked Partial/Undecided — see docs/data_capability_matrix.md.

Order book (TC-D10–TC-D15): Not implemented. Marked Unsupported.

Usage:
    Set environment variables then run:
        $env:MT5_HOST="127.0.0.1"
        $env:MT5_PORT="18812"
        $env:MT5_TEST_SYMBOL="USTEC"
        python examples/mt5_external_rpyc_data_tester.py
"""
import asyncio
import os

from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.data.messages import RequestBars, RequestInstrument, SubscribeBars, SubscribeQuoteTicks
from nautilus_trader.model.data import BarSpecification, BarType
from nautilus_trader.model.enums import AggregationSource, BarAggregation, PriceType
from nautilus_trader.model.identifiers import InstrumentId, Symbol, TraderId, Venue

from nautilus_mt5.client.types import MT5TerminalAccessMode
from nautilus_mt5.config import (
    ExternalRPyCTerminalConfig,
    MetaTrader5DataClientConfig,
    MetaTrader5InstrumentProviderConfig,
)
from nautilus_mt5.data_types import MT5Symbol
from nautilus_mt5.factories import MT5LiveDataClientFactory, MT5_CLIENTS

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MT5_HOST = os.environ.get("MT5_HOST", "127.0.0.1")
MT5_PORT = int(os.environ.get("MT5_PORT", "18812"))
SYMBOL_NAME = os.environ.get("MT5_TEST_SYMBOL", "USTEC")
VENUE = Venue("METATRADER_5")
INSTRUMENT_ID = InstrumentId(Symbol(SYMBOL_NAME), VENUE)

BAR_TYPE = BarType(
    instrument_id=INSTRUMENT_ID,
    bar_spec=BarSpecification(1, BarAggregation.MINUTE, PriceType.BID),
    aggregation_source=AggregationSource.EXTERNAL,
)


def _build_config() -> MetaTrader5DataClientConfig:
    return MetaTrader5DataClientConfig(
        client_id=1,
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=ExternalRPyCTerminalConfig(host=MT5_HOST, port=MT5_PORT),
        instrument_provider=MetaTrader5InstrumentProviderConfig(
            load_symbols=frozenset([MT5Symbol(symbol=SYMBOL_NAME)]),
        ),
    )


# ---------------------------------------------------------------------------
# DataTester flow
# ---------------------------------------------------------------------------
async def run_data_tester() -> None:
    print(f"=== MT5 DataTester (EXTERNAL_RPYC) | symbol={SYMBOL_NAME} | {MT5_HOST}:{MT5_PORT} ===\n")
    MT5_CLIENTS.clear()

    loop = asyncio.get_running_loop()
    clock = LiveClock()
    msgbus = MessageBus(TraderId("DATATESTER-001"), clock)
    cache = Cache()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop,
        name="MT5",
        config=_build_config(),
        msgbus=msgbus,
        cache=cache,
        clock=clock,
    )

    # --- Connect (TC-D01: loads instrument via provider) ---
    print("[TC-D01] Connecting and loading instrument provider ...")
    await data_client._connect()
    instruments = data_client.instrument_provider.list_all()
    ustec = next((i for i in instruments if i.id == INSTRUMENT_ID), None)
    if ustec:
        print(f"  [✓] TC-D01: Instrument loaded — {ustec.id}  digits={ustec.info.get('digits', '?')}")
    else:
        print(f"  [✗] TC-D01: {SYMBOL_NAME} not found in provider after connect")

    # --- Request instrument (TC-D03) ---
    print("\n[TC-D03] Requesting instrument via data client ...")
    req_instrument = RequestInstrument(
        instrument_id=INSTRUMENT_ID,
        start=None,
        end=None,
        client_id=data_client.id,
        venue=VENUE,
        callback=None,
        request_id=UUID4(),
        ts_init=clock.timestamp_ns(),
        params=None,
    )
    await data_client._request_instrument(req_instrument)
    cached = cache.instrument(INSTRUMENT_ID)
    if cached:
        print(f"  [✓] TC-D03: Instrument in cache — {cached.id}")
    else:
        print(f"  [~] TC-D03: Instrument not in cache after request (may need provider load first)")

    # --- Subscribe QuoteTicks (TC-D20) ---
    print("\n[TC-D20] Subscribing QuoteTicks ...")
    sub_qt = SubscribeQuoteTicks(
        instrument_id=INSTRUMENT_ID,
        client_id=data_client.id,
        venue=None,
        command_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )
    await data_client._subscribe_quote_ticks(sub_qt)
    print(
        f"  [~] TC-D20: Subscription registered for {SYMBOL_NAME}. "
        "Ticks flow in a live session — not validated here (Partial)."
    )

    # --- Request historical bars (TC-D40) ---
    print("\n[TC-D40] Requesting historical bars (M1, last 5) ...")
    req_bars = RequestBars(
        bar_type=BAR_TYPE,
        start=None,
        end=None,
        limit=5,
        client_id=data_client.id,
        venue=VENUE,
        callback=None,
        request_id=UUID4(),
        ts_init=clock.timestamp_ns(),
        params=None,
    )
    try:
        await data_client._request_bars(req_bars)
        print(f"  [~] TC-D40: _request_bars completed for {BAR_TYPE} (check logs for bar count).")
    except Exception as exc:
        print(f"  [✗] TC-D40: _request_bars raised: {exc}")

    # --- Subscribe bars (TC-D41) ---
    print("\n[TC-D41] Subscribing bars (M1 historical path) ...")
    sub_bars = SubscribeBars(
        bar_type=BAR_TYPE,
        client_id=data_client.id,
        venue=None,
        command_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )
    try:
        await data_client._subscribe_bars(sub_bars)
        print(f"  [~] TC-D41: Subscription registered for {BAR_TYPE} (Partial — no live feed).")
    except Exception as exc:
        print(f"  [✗] TC-D41: _subscribe_bars raised: {exc}")

    # --- Trade ticks: explicit decision ---
    print("\n[TC-D30/D31] TradeTick decision:")
    print(
        "  [-] TC-D30: Skipped — MT5 copy_ticks_* returns bid/ask (QuoteTick semantics).\n"
        "              'last' field is unreliable for CFD indexes. Status: Partial/Undecided."
    )
    print("  [-] TC-D31: Same as TC-D30.")

    # --- Order book: explicit Unsupported ---
    print("\n[TC-D10–D15] Order book: Unsupported — not implemented in this adapter.")

    # --- Disconnect ---
    print("\n[Lifecycle] Disconnecting ...")
    await data_client._disconnect()
    print("  [✓] Disconnected cleanly.\n")

    print("=" * 60)
    print(" TC-D01  Instrument load       ✓ Supported (via provider)")
    print(" TC-D03  Request instrument    ✓ Supported")
    print(" TC-D20  Subscribe QuoteTicks  ~ Partial (subscription wired, no live stream here)")
    print(" TC-D30  Live TradeTicks       - Undecided (bid/ask≠trade; see data_capability_matrix)")
    print(" TC-D31  Hist TradeTicks       - Undecided (same as TC-D30)")
    print(" TC-D40  Request hist bars     ~ Partial (request wired; bar delivery needs live MT5)")
    print(" TC-D41  Subscribe bars        ~ Partial (subscription wired)")
    print(" TC-D10–D15  Order book        ✗ Unsupported")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_data_tester())
