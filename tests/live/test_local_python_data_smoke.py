"""
test_local_python_data_smoke.py
Live data smoke test for LOCAL_PYTHON mode (direct MetaTrader5 module access).

Validates the path:
    MetaTrader5 module (local Windows install)
    → initialize() → symbol_select / symbol_info / symbol_info_tick
    → copy_rates_from_pos (>= 1 M1 bar)
    → copy_ticks_from (>= 1 tick)
    → shutdown()

No orders are submitted.

Markers: @pytest.mark.live  @pytest.mark.local_python

Skip conditions:
  - MetaTrader5 package not installed
  - MT5 terminal not running / not logged in
  - MT5_TEST_SYMBOL defaults to USTEC

Run command:
  pytest -m "live and local_python" tests/live/test_local_python_data_smoke.py -v
"""

import datetime
import os

import pytest

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
MT5_SYMBOL = os.environ.get("MT5_TEST_SYMBOL", "USTEC")
MT5_ACCOUNT_NUMBER = os.environ.get("MT5_ACCOUNT_NUMBER", "")
MT5_LOCAL_PATH = os.environ.get("MT5_LOCAL_PATH", None)
MT5_LOCAL_TIMEOUT = int(os.environ.get("MT5_LOCAL_TIMEOUT", "60000"))

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def mt5_local():
    """
    Module-scoped MetaTrader5 module handle.
    Skipped if:
      - MetaTrader5 package not installed
      - initialize() fails (terminal not running or not logged in)
    """
    try:
        import MetaTrader5 as mt5
    except ImportError:
        pytest.skip(
            "MetaTrader5 package not installed. "
            "Run on Windows with: pip install MetaTrader5"
        )

    kwargs: dict = {}
    if MT5_LOCAL_PATH:
        kwargs["path"] = MT5_LOCAL_PATH
    if MT5_LOCAL_TIMEOUT:
        kwargs["timeout"] = MT5_LOCAL_TIMEOUT

    if not mt5.initialize(**kwargs):
        err = mt5.last_error()
        pytest.skip(
            f"MetaTrader5.initialize() failed: {err}. "
            "Ensure the MT5 terminal is running and logged in."
        )

    yield mt5

    mt5.shutdown()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.live
@pytest.mark.local_python
def test_local_python_terminal_info(mt5_local):
    """terminal_info() returns a connected terminal object."""
    mt5 = mt5_local
    info = mt5.terminal_info()
    assert info is not None, "terminal_info() returned None"
    assert info.connected, "MT5 terminal reports not connected to broker"


@pytest.mark.live
@pytest.mark.local_python
def test_local_python_account_info(mt5_local):
    """
    account_info() returns a valid demo account.
    If MT5_ACCOUNT_NUMBER is set, validates the login matches.
    """
    mt5 = mt5_local
    acc = mt5.account_info()

    if acc is None:
        pytest.skip("account_info() returned None — terminal may not be logged in.")

    assert acc.login is not None
    assert acc.login > 0, f"Unexpected login value: {acc.login}"

    if MT5_ACCOUNT_NUMBER:
        assert str(acc.login) == str(MT5_ACCOUNT_NUMBER), (
            f"Account mismatch: actual login={acc.login}, "
            f"MT5_ACCOUNT_NUMBER={MT5_ACCOUNT_NUMBER}"
        )


@pytest.mark.live
@pytest.mark.local_python
def test_local_python_symbol_available(mt5_local):
    """MT5_TEST_SYMBOL is available and selectable in the local terminal."""
    mt5 = mt5_local

    ok = mt5.symbol_select(MT5_SYMBOL, True)
    assert ok, (
        f"symbol_select({MT5_SYMBOL!r}, True) returned False — "
        f"symbol may not exist in this broker account."
    )

    info = mt5.symbol_info(MT5_SYMBOL)
    assert info is not None, f"symbol_info({MT5_SYMBOL!r}) returned None after symbol_select"
    assert info.digits is not None


@pytest.mark.live
@pytest.mark.local_python
def test_local_python_symbol_info_tick(mt5_local):
    """symbol_info_tick returns bid and ask."""
    mt5 = mt5_local

    tick = mt5.symbol_info_tick(MT5_SYMBOL)
    if tick is None:
        pytest.skip(
            f"symbol_info_tick({MT5_SYMBOL!r}) returned None — market may be closed."
        )

    assert tick.bid is not None and tick.ask is not None
    assert tick.ask >= tick.bid, f"ask ({tick.ask}) < bid ({tick.bid})"


@pytest.mark.live
@pytest.mark.local_python
def test_local_python_copy_rates_m1(mt5_local):
    """copy_rates_from_pos returns at least 1 M1 bar."""
    mt5 = mt5_local

    bars = mt5.copy_rates_from_pos(MT5_SYMBOL, mt5.TIMEFRAME_M1, 0, 5)
    assert bars is not None and len(bars) >= 1, (
        f"copy_rates_from_pos returned no bars for {MT5_SYMBOL}. "
        "Market may be closed or history unavailable."
    )


@pytest.mark.live
@pytest.mark.local_python
def test_local_python_copy_ticks_from(mt5_local):
    """copy_ticks_from returns at least 1 tick in the last 30 minutes."""
    mt5 = mt5_local

    now = datetime.datetime.now()
    from_dt = now - datetime.timedelta(minutes=30)
    ticks = mt5.copy_ticks_from(MT5_SYMBOL, from_dt, 10, mt5.COPY_TICKS_ALL)

    assert ticks is not None and len(ticks) >= 1, (
        f"copy_ticks_from returned no ticks for {MT5_SYMBOL} in the last 30 min. "
        "Market may be closed."
    )
