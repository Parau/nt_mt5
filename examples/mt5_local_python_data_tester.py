"""
mt5_local_python_data_tester.py
================================
DataTester example for the MT5 adapter via LOCAL_PYTHON mode.

Identical coverage to ``mt5_external_rpyc_data_tester.py``, but connects through
the local MetaTrader5 Python module instead of an EXTERNAL_RPYC gateway.

Covers (Tier 0):
  TC-D01  Load specific instrument (USTEC) via InstrumentProvider
  TC-D03  Request instrument via MetaTrader5DataClient._request_instrument()
  TC-D20  Subscribe QuoteTicks (subscription registered; ticks flow in live session)
  TC-D40  Request historical bars via MetaTrader5DataClient._request_bars()
  TC-D41  Subscribe bars (historical path)

Trade ticks (TC-D30/TC-D31): Partial/Undecided — see docs/data_capability_matrix.md.
Order book (TC-D10–TC-D15): Unsupported.

Requirements:
  - Windows
  - MetaTrader5 terminal running and logged in
  - pip install MetaTrader5

Usage:
    $env:MT5_TEST_SYMBOL="USTEC"
    python examples/mt5_local_python_data_tester.py
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
    LocalPythonTerminalConfig,
    MetaTrader5DataClientConfig,
    MetaTrader5InstrumentProviderConfig,
)
from nautilus_mt5.data_types import MT5Symbol
from nautilus_mt5.factories import MT5LiveDataClientFactory, MT5_CLIENTS

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SYMBOL_NAME = os.environ.get("MT5_TEST_SYMBOL", "USTEC")
MT5_LOCAL_PATH = os.environ.get("MT5_LOCAL_PATH", None)
MT5_LOCAL_TIMEOUT = int(os.environ.get("MT5_LOCAL_TIMEOUT", "60000"))

VENUE = Venue("METATRADER_5")
INSTRUMENT_ID = InstrumentId(Symbol(SYMBOL_NAME), VENUE)

BAR_TYPE = BarType(
    instrument_id=INSTRUMENT_ID,
    bar_spec=BarSpecification(1, BarAggregation.MINUTE, PriceType.BID),
    aggregation_source=AggregationSource.EXTERNAL,
)


def _build_config() -> MetaTrader5DataClientConfig:
    local_cfg_kwargs: dict = {}
    if MT5_LOCAL_PATH:
        local_cfg_kwargs["path"] = MT5_LOCAL_PATH
    local_cfg_kwargs["timeout"] = MT5_LOCAL_TIMEOUT

    return MetaTrader5DataClientConfig(
        client_id=1,
        terminal_access=MT5TerminalAccessMode.LOCAL_PYTHON,
        local_python=LocalPythonTerminalConfig(**local_cfg_kwargs),
        instrument_provider=MetaTrader5InstrumentProviderConfig(
            load_symbols=frozenset([MT5Symbol(symbol=SYMBOL_NAME)]),
        ),
    )


# ---------------------------------------------------------------------------
# DataTester flow
# ---------------------------------------------------------------------------
async def run_data_tester() -> None:
    print(f"=== MT5 DataTester (LOCAL_PYTHON) | symbol={SYMBOL_NAME} ===\n")
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

    # --- Connect (TC-D01) ---
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
        print(f"  [~] TC-D03: Instrument not in cache after request")

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
        "Ticks flow in a live session (Partial)."
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
        print(f"  [~] TC-D40: _request_bars completed (check logs for bar count).")
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
        print(f"  [~] TC-D41: Subscription registered (Partial — no live feed).")
    except Exception as exc:
        print(f"  [✗] TC-D41: _subscribe_bars raised: {exc}")

    # --- TradeTick decision ---
    print("\n[TC-D30/D31] TradeTick decision:")
    print(
        "  [-] TC-D30: Skipped — MT5 copy_ticks_* returns bid/ask (QuoteTick semantics).\n"
        "              'last' unreliable for CFD indexes. Status: Partial/Undecided."
    )
    print("  [-] TC-D31: Same as TC-D30.")

    # --- Order book ---
    print("\n[TC-D10–D15] Order book: Unsupported.")

    # --- Disconnect ---
    print("\n[Lifecycle] Disconnecting ...")
    await data_client._disconnect()
    print("  [✓] Disconnected cleanly.\n")

    print("=" * 60)
    print(" TC-D01  Instrument load       ✓ Supported")
    print(" TC-D03  Request instrument    ✓ Supported")
    print(" TC-D20  Subscribe QuoteTicks  ~ Partial")
    print(" TC-D30  Live TradeTicks       - Undecided")
    print(" TC-D31  Hist TradeTicks       - Undecided")
    print(" TC-D40  Request hist bars     ~ Partial")
    print(" TC-D41  Subscribe bars        ~ Partial")
    print(" TC-D10–D15  Order book        ✗ Unsupported")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_data_tester())
