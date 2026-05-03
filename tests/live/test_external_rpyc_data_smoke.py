"""
test_external_rpyc_data_smoke.py
Live data smoke test for the EXTERNAL_RPYC gateway.

Validates the path:
    RPyC gateway → symbol_select / symbol_info / symbol_info_tick
                 → copy_rates_from_pos (>= 1 M1 bar)
                 → copy_ticks_from (>= 1 tick)

No orders are submitted.

Markers: @pytest.mark.live  @pytest.mark.external_rpyc

Skip conditions (all required):
  MT5_HOST, MT5_PORT must be set (or defaults 127.0.0.1 / 18812 are used and
  the test skips if the connection fails at collection time).
  MT5_TEST_SYMBOL defaults to USTEC.

Run command:
  pytest -m "live and external_rpyc" tests/live/test_external_rpyc_data_smoke.py -v
"""

import datetime
import os

import pytest

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
MT5_HOST = os.environ.get("MT5_HOST", "")
MT5_PORT_STR = os.environ.get("MT5_PORT", "")
MT5_SYMBOL = os.environ.get("MT5_TEST_SYMBOL", "USTEC")
MT5_ACCOUNT_NUMBER = os.environ.get("MT5_ACCOUNT_NUMBER", "")

_MISSING_HOST = not MT5_HOST
_MISSING_PORT = not MT5_PORT_STR
_SKIP_REASON = (
    "Live EXTERNAL_RPYC tests require MT5_HOST and MT5_PORT environment variables. "
    "Set them to point at a running MT5 RPyC gateway."
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def mt5_rpyc_conn():
    """
    Module-scoped RPyC connection to the MT5 gateway.
    Skipped automatically if MT5_HOST / MT5_PORT are not set.
    """
    if _MISSING_HOST or _MISSING_PORT:
        pytest.skip(_SKIP_REASON)

    try:
        import rpyc
    except ImportError:
        pytest.skip("rpyc not installed — pip install rpyc")

    host = MT5_HOST
    port = int(MT5_PORT_STR)
    try:
        conn = rpyc.connect(host, port, config={"allow_all_attrs": True}, keepalive=True)
    except Exception as exc:
        pytest.skip(f"Could not connect to MT5 gateway at {host}:{port}: {exc}")

    mt5 = conn.root
    try:
        mt5.initialize()
    except AttributeError:
        pass  # not all gateways expose initialize()

    yield mt5

    conn.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.live
@pytest.mark.external_rpyc
def test_gateway_reachable(mt5_rpyc_conn):
    """Gateway is reachable and responds to terminal_info or account_info."""
    mt5 = mt5_rpyc_conn

    info = None
    try:
        info = mt5.terminal_info()
    except Exception:
        pass

    acc = None
    try:
        acc = mt5.account_info()
    except Exception:
        pass

    assert info is not None or acc is not None, (
        "Both terminal_info() and account_info() returned None — "
        "gateway may not be connected to a MT5 terminal."
    )


@pytest.mark.live
@pytest.mark.external_rpyc
def test_account_info_demo(mt5_rpyc_conn):
    """
    account_info() returns a valid account object.
    If MT5_ACCOUNT_NUMBER is set, validates the login matches.
    """
    mt5 = mt5_rpyc_conn

    try:
        acc = mt5.account_info()
    except Exception as exc:
        pytest.skip(f"account_info() raised: {exc}")

    if acc is None:
        pytest.skip("account_info() returned None — terminal may not be logged in.")

    login = getattr(acc, "login", None)
    assert login is not None, "account_info() returned object without 'login' field"

    if MT5_ACCOUNT_NUMBER:
        assert str(login) == str(MT5_ACCOUNT_NUMBER), (
            f"Account mismatch: gateway login={login}, "
            f"MT5_ACCOUNT_NUMBER={MT5_ACCOUNT_NUMBER}"
        )


@pytest.mark.live
@pytest.mark.external_rpyc
def test_symbol_available(mt5_rpyc_conn):
    """MT5_TEST_SYMBOL is available in the gateway."""
    mt5 = mt5_rpyc_conn

    try:
        mt5.symbol_select(MT5_SYMBOL, True)
    except Exception:
        pass  # not fatal if gateway does not expose symbol_select

    try:
        info = mt5.symbol_info(MT5_SYMBOL)
    except Exception as exc:
        pytest.fail(f"symbol_info({MT5_SYMBOL!r}) raised: {exc}")

    assert info is not None, (
        f"symbol_info({MT5_SYMBOL!r}) returned None — "
        f"symbol may not be available in this broker's account."
    )

    digits = getattr(info, "digits", None)
    assert digits is not None, "symbol_info missing 'digits' field"


@pytest.mark.live
@pytest.mark.external_rpyc
def test_symbol_info_tick(mt5_rpyc_conn):
    """symbol_info_tick returns bid and ask for MT5_TEST_SYMBOL."""
    mt5 = mt5_rpyc_conn

    try:
        tick = mt5.symbol_info_tick(MT5_SYMBOL)
    except Exception as exc:
        pytest.skip(f"symbol_info_tick raised: {exc}")

    if tick is None:
        pytest.skip(
            f"symbol_info_tick({MT5_SYMBOL!r}) returned None — market may be closed."
        )

    bid = getattr(tick, "bid", None)
    ask = getattr(tick, "ask", None)
    assert bid is not None and ask is not None, (
        f"Tick missing bid/ask: {tick}"
    )
    assert ask >= bid, f"ask ({ask}) < bid ({bid}) — unexpected spread"


@pytest.mark.live
@pytest.mark.external_rpyc
def test_copy_rates_from_pos_m1(mt5_rpyc_conn):
    """copy_rates_from_pos returns at least 1 M1 bar for MT5_TEST_SYMBOL."""
    mt5 = mt5_rpyc_conn

    try:
        tf_m1 = (
            mt5.get_constant("TIMEFRAME_M1")
            if hasattr(mt5, "get_constant")
            else 1
        )
        bars = mt5.copy_rates_from_pos(MT5_SYMBOL, tf_m1, 0, 5)
    except Exception as exc:
        pytest.skip(f"copy_rates_from_pos raised: {exc}")

    assert bars is not None and len(bars) >= 1, (
        f"copy_rates_from_pos returned no bars for {MT5_SYMBOL}. "
        "Market may be closed or symbol history unavailable."
    )


@pytest.mark.live
@pytest.mark.external_rpyc
def test_copy_ticks_from(mt5_rpyc_conn):
    """copy_ticks_from returns at least 1 tick for MT5_TEST_SYMBOL (last 30 min)."""
    mt5 = mt5_rpyc_conn

    try:
        tf_all = (
            mt5.get_constant("COPY_TICKS_ALL")
            if hasattr(mt5, "get_constant")
            else 0
        )
        now = datetime.datetime.now(datetime.timezone.utc)
        from_dt = now - datetime.timedelta(minutes=30)
        ticks = mt5.copy_ticks_from(MT5_SYMBOL, from_dt, 10, tf_all)
    except Exception as exc:
        pytest.skip(f"copy_ticks_from raised: {exc}")

    assert ticks is not None and len(ticks) >= 1, (
        f"copy_ticks_from returned no ticks for {MT5_SYMBOL} in the last 30 min. "
        "Market may be closed."
    )
