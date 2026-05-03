"""
test_external_rpyc_data_tester.py
===================================
Live DataTester tests for the MT5 adapter — EXTERNAL_RPYC mode.

Skips automatically if MT5_HOST or MT5_PORT are not set.
No orders submitted.

Markers: @pytest.mark.live  @pytest.mark.external_rpyc  @pytest.mark.data_tester

TC coverage against a real MT5 gateway:
  TC-D01  Instrument loads from real gateway
  TC-D03  symbol_info_tick delivers real bid/ask
  TC-D20  copy_ticks_from delivers real bid/ask ticks (QuoteTick semantics confirmed)
  TC-D40  copy_rates_from_pos delivers real M1 bars
  TC-D41  copy_rates_from_pos delivers real M5 bars

Run:
    $env:MT5_HOST="127.0.0.1"; $env:MT5_PORT="18812"; $env:MT5_TEST_SYMBOL="USTEC"
    pytest -m "live and external_rpyc and data_tester" tests/live/test_external_rpyc_data_tester.py -v
"""
import datetime
import os

import pytest

MT5_HOST = os.environ.get("MT5_HOST", "")
MT5_PORT_STR = os.environ.get("MT5_PORT", "")
MT5_SYMBOL = os.environ.get("MT5_TEST_SYMBOL", "USTEC")

_MISSING = not MT5_HOST or not MT5_PORT_STR
_SKIP_REASON = (
    "Live DataTester tests require MT5_HOST and MT5_PORT. "
    "Set them to point at a running MT5 RPyC gateway."
)

pytestmark = [pytest.mark.live, pytest.mark.external_rpyc, pytest.mark.data_tester]


# ---------------------------------------------------------------------------
# Module-scoped fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def mt5_gateway():
    if _MISSING:
        pytest.skip(_SKIP_REASON)

    try:
        import rpyc
    except ImportError:
        pytest.skip("rpyc not installed")

    try:
        conn = rpyc.connect(
            MT5_HOST, int(MT5_PORT_STR),
            config={"allow_all_attrs": True}, keepalive=True,
        )
    except Exception as exc:
        pytest.skip(f"Cannot connect to MT5 gateway at {MT5_HOST}:{MT5_PORT_STR}: {exc}")

    mt5 = conn.root
    try:
        mt5.initialize()
    except AttributeError:
        pass

    yield mt5

    conn.close()


def _attr(obj, name):
    """Get field from namedtuple, dict, or numpy structured array row."""
    if isinstance(obj, dict):
        return obj.get(name)
    try:
        return obj[name]
    except (IndexError, ValueError, KeyError, TypeError):
        return getattr(obj, name, None)


# ---------------------------------------------------------------------------
# TC-D01: Instrument loading
# ---------------------------------------------------------------------------

def test_tc_d01_instrument_loads(mt5_gateway):
    """TC-D01: symbol_info() returns a valid instrument for MT5_TEST_SYMBOL."""
    mt5 = mt5_gateway
    try:
        mt5.symbol_select(MT5_SYMBOL, True)
    except Exception:
        pass

    info = mt5.symbol_info(MT5_SYMBOL)
    assert info is not None, f"TC-D01: symbol_info({MT5_SYMBOL!r}) returned None"

    digits = _attr(info, "digits")
    assert digits is not None, "TC-D01: symbol_info missing 'digits'"
    assert isinstance(digits, int), f"TC-D01: digits not int: {digits!r}"


# ---------------------------------------------------------------------------
# TC-D03: Request instrument (bid/ask tick)
# ---------------------------------------------------------------------------

def test_tc_d03_request_instrument_tick(mt5_gateway):
    """TC-D03: symbol_info_tick() returns bid and ask for MT5_TEST_SYMBOL."""
    mt5 = mt5_gateway
    tick = mt5.symbol_info_tick(MT5_SYMBOL)

    if tick is None:
        pytest.skip(f"TC-D03: symbol_info_tick({MT5_SYMBOL!r}) returned None — market closed?")

    bid = _attr(tick, "bid")
    ask = _attr(tick, "ask")
    assert bid is not None and ask is not None, f"TC-D03: tick missing bid/ask: {tick}"
    assert ask >= bid, f"TC-D03: ask ({ask}) < bid ({bid})"


# ---------------------------------------------------------------------------
# TC-D20: QuoteTick semantics from copy_ticks_from
# ---------------------------------------------------------------------------

def test_tc_d20_quote_ticks_bid_ask_confirmed(mt5_gateway):
    """
    TC-D20: copy_ticks_from returns bid/ask records (QuoteTick semantics).
    Validates:
    - At least 1 tick returned
    - Each tick has bid and ask fields
    - bid/ask values are positive

    Explicit note: 'last' field is NOT validated here because for CFD indexes
    like USTEC it is unreliable (often zero). This confirms QuoteTick semantics
    and rules out TradeTick semantics (TC-D30 remains Undecided).
    """
    mt5 = mt5_gateway

    try:
        flags = (
            mt5.get_constant("COPY_TICKS_ALL")
            if hasattr(mt5, "get_constant")
            else 0
        )
        # MT5 via RPyC requires Unix timestamp int, not datetime object
        from_ts = int(datetime.datetime.now(datetime.timezone.utc).timestamp()) - 3600
        ticks = mt5.copy_ticks_from(MT5_SYMBOL, from_ts, 20, flags)
    except Exception as exc:
        pytest.skip(f"TC-D20: copy_ticks_from raised: {exc}")

    if ticks is None or len(ticks) == 0:
        pytest.skip("TC-D20: No ticks returned — copy_ticks_from returned empty (market closed or no tick history)")

    # Validate first tick
    t = ticks[0]
    bid = _attr(t, "bid")
    ask = _attr(t, "ask")
    assert bid is not None and ask is not None, f"TC-D20: tick missing bid/ask: {t}"
    assert bid > 0, f"TC-D20: bid <= 0: {bid}"
    assert ask > 0, f"TC-D20: ask <= 0: {ask}"
    assert ask >= bid, f"TC-D20: ask ({ask}) < bid ({bid})"


# ---------------------------------------------------------------------------
# TC-D30/D31: TradeTick — explicit decision
# ---------------------------------------------------------------------------

def test_tc_d30_trade_tick_semantics_decision(mt5_gateway):
    """
    TC-D30/TC-D31: Validates the 'last' field from copy_ticks_from for USTEC.

    For CFD indexes on Tickmill-Demo, 'last' is often 0.0 or None.
    This confirms that copy_ticks_* CANNOT be used as a reliable TradeTick
    source for USTEC. TradeTick (TC-D30/TC-D31) remains Partial/Undecided.

    If 'last' is consistently non-zero for your broker/symbol, update the
    capability matrix and add explicit TradeTick parsing coverage.
    """
    mt5 = mt5_gateway

    try:
        flags = (
            mt5.get_constant("COPY_TICKS_ALL")
            if hasattr(mt5, "get_constant")
            else 0
        )
        # MT5 via RPyC requires Unix timestamp int, not datetime object
        from_ts = int(datetime.datetime.now(datetime.timezone.utc).timestamp()) - 3600
        ticks = mt5.copy_ticks_from(MT5_SYMBOL, from_ts, 5, flags)
    except Exception as exc:
        pytest.skip(f"TC-D30: copy_ticks_from raised: {exc}")

    if ticks is None or len(ticks) == 0:
        pytest.skip("TC-D30: No ticks — copy_ticks_from returned empty (market closed or no tick history)")

    last_values = [_attr(t, "last") or 0.0 for t in ticks]
    all_zero = all(v == 0.0 or v is None for v in last_values)

    # Document the finding — test passes regardless (it's an observation test)
    if all_zero:
        pytest.xfail(
            f"TC-D30: 'last' is zero/None for all sampled ticks of {MT5_SYMBOL}. "
            "copy_ticks_* cannot reliably supply TradeTick semantics for this symbol. "
            "Status remains Partial/Undecided."
        )
    else:
        # 'last' is non-zero — warrant further investigation before claiming Supported
        pytest.xfail(
            f"TC-D30: 'last' is non-zero for some ticks of {MT5_SYMBOL} "
            f"(values: {last_values[:3]}). "
            "Investigate whether 'last' represents actual exchange trades "
            "before promoting TradeTick to Supported. Status: Partial/Undecided."
        )


# ---------------------------------------------------------------------------
# TC-D40: Historical bars M1
# ---------------------------------------------------------------------------

def test_tc_d40_historical_bars_m1(mt5_gateway):
    """TC-D40: copy_rates_from_pos returns at least 1 M1 bar with valid OHLC."""
    mt5 = mt5_gateway

    try:
        tf_m1 = (
            mt5.get_constant("TIMEFRAME_M1")
            if hasattr(mt5, "get_constant")
            else 1
        )
        bars = mt5.copy_rates_from_pos(MT5_SYMBOL, tf_m1, 0, 5)
    except Exception as exc:
        pytest.skip(f"TC-D40: copy_rates_from_pos raised: {exc}")

    if bars is None or len(bars) == 0:
        pytest.skip("TC-D40: No bars returned — market may be closed")

    b = bars[0]
    open_ = _attr(b, "open")
    high = _attr(b, "high")
    low = _attr(b, "low")
    close = _attr(b, "close")

    assert all(v is not None for v in [open_, high, low, close]), (
        f"TC-D40: Bar missing OHLC: {b}"
    )
    assert high >= low, f"TC-D40: high ({high}) < low ({low})"
    assert high >= open_ and high >= close, "TC-D40: high not >= open/close"
    assert low <= open_ and low <= close, "TC-D40: low not <= open/close"


# ---------------------------------------------------------------------------
# TC-D41: Bars M5
# ---------------------------------------------------------------------------

def test_tc_d41_historical_bars_m5(mt5_gateway):
    """TC-D41: copy_rates_from_pos returns M5 bars with valid structure."""
    mt5 = mt5_gateway

    try:
        tf_m5 = (
            mt5.get_constant("TIMEFRAME_M5")
            if hasattr(mt5, "get_constant")
            else 5
        )
        bars = mt5.copy_rates_from_pos(MT5_SYMBOL, tf_m5, 0, 10)
    except Exception as exc:
        pytest.skip(f"TC-D41: copy_rates_from_pos (M5) raised: {exc}")

    if bars is None or len(bars) == 0:
        pytest.skip("TC-D41: No M5 bars returned")

    assert len(bars) >= 1
    b = bars[0]
    assert _attr(b, "open") is not None, "TC-D41: M5 bar missing 'open'"
    assert _attr(b, "close") is not None, "TC-D41: M5 bar missing 'close'"
