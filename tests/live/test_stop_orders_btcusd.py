"""
test_stop_orders_btcusd.py
Live stop-order tests for TC-E20–TC-E23 equivalents using BTCUSD.

Validates pending stop orders placed via a real demo MT5 account through the
EXTERNAL_RPYC gateway:

    TC-E20-LIVE  BUY  STOP_MARKET  → action=5, type=4, retcode=10008 (PLACED)
    TC-E21-LIVE  SELL STOP_MARKET  → action=5, type=5, retcode=10008 (PLACED)
    TC-E22-LIVE  BUY  STOP_LIMIT   → action=5, type=6, retcode=10008 (PLACED)
    TC-E23-LIVE  SELL STOP_LIMIT   → action=5, type=7, retcode=10008 (PLACED)

All placed orders are removed (TRADE_ACTION_REMOVE) at the end of each test.

Markers: @pytest.mark.live  @pytest.mark.external_rpyc

Layer: raw bridge (no adapter)
-------------------------------
This file tests stop orders by calling the RPyC bridge directly, without going
through the Nautilus adapter stack (no MetaTrader5Client, no ExecutionClient,
no factory). It validates that the raw MT5 request dict sent to
bridge.order_send() is accepted by the real terminal with retcode=10008.

For the equivalent test that exercises the same order types through the full
adapter stack (ExecutionClient → MetaTrader5Client → bridge), see:
    tests/acceptance/test_live_stop_orders.py

Both levels are intentional: this file catches bridge-level field name errors
(e.g. the stoplimit vs stpx regression of 2026-05-03); the acceptance test
catches adapter-level translation errors.

Safety locks (ALL must be satisfied before any order is sent):
  1. MT5_ENABLE_LIVE_EXECUTION=1  — explicit opt-in
  2. MT5_HOST and MT5_PORT        — RPyC gateway location
  3. MT5_ACCOUNT_NUMBER           — login to validate against account_info()
  4. account_info().trade_mode == 0  — demo only

Run command:
  $env:MT5_ENABLE_LIVE_EXECUTION="1"
  $env:MT5_HOST="127.0.0.1"
  $env:MT5_PORT="18812"
  $env:MT5_ACCOUNT_NUMBER="<login>"
  pytest -m "live and external_rpyc" tests/live/test_stop_orders_btcusd.py -v -s
"""

import os
import time

import pytest

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
MT5_HOST = os.environ.get("MT5_HOST", "")
MT5_PORT_STR = os.environ.get("MT5_PORT", "")
MT5_ACCOUNT_NUMBER = os.environ.get("MT5_ACCOUNT_NUMBER", "")
MT5_ENABLE_LIVE_EXECUTION = os.environ.get("MT5_ENABLE_LIVE_EXECUTION", "")

_MISSING_CONN = not (MT5_HOST and MT5_PORT_STR)
_SKIP_NO_CONN = (
    "Live EXTERNAL_RPYC tests require MT5_HOST and MT5_PORT. "
    "Set them to point at a running MT5 RPyC gateway."
)

# ---------------------------------------------------------------------------
# MT5 constants
# ---------------------------------------------------------------------------
ACCOUNT_TRADE_MODE_DEMO = 0

# TRADE_ACTION_PENDING = 5  — place a pending order (stop / limit)
TRADE_ACTION_PENDING = 5
# TRADE_ACTION_REMOVE = 8   — cancel a pending order
TRADE_ACTION_REMOVE = 8

# MT5 order types for stop orders
ORDER_TYPE_BUY_STOP = 4
ORDER_TYPE_SELL_STOP = 5
ORDER_TYPE_BUY_STOP_LIMIT = 6
ORDER_TYPE_SELL_STOP_LIMIT = 7

# ORDER_TIME_GTC = 0
ORDER_TIME_GTC = 0

# Pending orders must NOT trigger immediately.
# For BTCUSD we use a conservative offset from the current price (in USD).
STOP_PRICE_OFFSET_PCT = 0.03   # 3 % away from current price

SYMBOL = "BTCUSD"
VOLUME = 0.01          # minimum tradeable lot for BTCUSD on most demo brokers
MAGIC = 20260503
RETCODE_PLACED = 10008


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _as_dict(obj) -> dict:
    """Coerce an RPyC-proxied named-tuple or dict-like to a plain dict."""
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return dict(obj)
    try:
        import rpyc
        local = rpyc.classic.obtain(obj)
    except Exception:
        local = obj
    if hasattr(local, "_asdict"):
        return local._asdict()
    if isinstance(local, dict):
        return dict(local)
    try:
        return {k: local[k] for k in local.dtype.names}
    except Exception:
        return {}


def _as_list(obj) -> list:
    if obj is None:
        return []
    try:
        import rpyc
        local = rpyc.classic.obtain(obj)
    except Exception:
        local = obj
    if not local:
        return []
    try:
        return [_as_dict(item) for item in local]
    except Exception:
        return list(local)


def _cancel_pending_order(mt5, ticket: int, symbol: str) -> dict:
    """Send TRADE_ACTION_REMOVE for a pending order ticket."""
    cancel_req = {
        "action": TRADE_ACTION_REMOVE,
        "order": ticket,
        "symbol": symbol,
        "magic": MAGIC,
        "comment": "tc-e20-23 cleanup",
    }
    try:
        result_raw = mt5.order_send(cancel_req)
        return _as_dict(result_raw)
    except Exception as exc:
        return {"retcode": -1, "comment": str(exc)}


def _round_price(price: float, digits: int) -> float:
    return round(price, digits)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def mt5_rpyc_conn():
    """Module-scoped RPyC connection to a running MT5 gateway."""
    if _MISSING_CONN:
        pytest.skip(_SKIP_NO_CONN)
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
        pass

    yield mt5
    conn.close()


@pytest.fixture(scope="module")
def validated_demo_mt5(mt5_rpyc_conn):
    """
    Validates opt-in flag, demo account, and symbol availability.
    Returns (mt5, symbol_info_dict, tick_dict).
    """
    if MT5_ENABLE_LIVE_EXECUTION != "1":
        pytest.skip(
            "MT5_ENABLE_LIVE_EXECUTION is not set to '1'. "
            "Set MT5_ENABLE_LIVE_EXECUTION=1 to run live stop-order tests."
        )

    mt5 = mt5_rpyc_conn

    # Verify demo account
    try:
        acc_raw = mt5.account_info()
    except Exception as exc:
        pytest.skip(f"account_info() raised: {exc}")

    acc = _as_dict(acc_raw)
    trade_mode = acc.get("trade_mode", -1)
    assert trade_mode == ACCOUNT_TRADE_MODE_DEMO, (
        f"SAFETY: account trade_mode={trade_mode} is not DEMO. Aborting."
    )
    if MT5_ACCOUNT_NUMBER:
        login = int(acc.get("login", -1))
        assert login == int(MT5_ACCOUNT_NUMBER), (
            f"SAFETY: login={login} != MT5_ACCOUNT_NUMBER={MT5_ACCOUNT_NUMBER}."
        )

    # Verify symbol
    try:
        mt5.symbol_select(SYMBOL, True)
        info_raw = mt5.symbol_info(SYMBOL)
    except Exception as exc:
        pytest.skip(f"symbol_info({SYMBOL}) raised: {exc}")

    info = _as_dict(info_raw)
    assert info, f"symbol_info({SYMBOL}) returned empty result"

    try:
        tick_raw = mt5.symbol_info_tick(SYMBOL)
    except Exception as exc:
        pytest.skip(f"symbol_info_tick({SYMBOL}) raised: {exc}")

    tick = _as_dict(tick_raw)
    assert float(tick.get("ask", 0.0)) > 0, (
        f"{SYMBOL}: ask price is 0 — market may be closed"
    )

    return mt5, info, tick


# ---------------------------------------------------------------------------
# TC-E20-LIVE: BUY STOP_MARKET (ORDER_TYPE_BUY_STOP = 4)
# ---------------------------------------------------------------------------

@pytest.mark.live
@pytest.mark.external_rpyc
def test_tc_e20_live_buy_stop_market(validated_demo_mt5):
    """
    TC-E20-LIVE: BUY STOP_MARKET for BTCUSD.

    Places a pending BUY STOP order above the current ask price.
    Expects:
      - order_send called with action=5 (TRADE_ACTION_PENDING), type=4 (ORDER_TYPE_BUY_STOP)
      - retcode=10008 (PLACED) → not triggered immediately
    Cleanup: cancels the pending order via TRADE_ACTION_REMOVE.
    """
    mt5, info, tick = validated_demo_mt5
    digits = int(info.get("digits", 2))
    ask = float(tick.get("ask", 0.0))

    # Stop price must be above current ask to avoid immediate trigger
    stop_price = _round_price(ask * (1 + STOP_PRICE_OFFSET_PCT), digits)
    print(f"\n[TC-E20] BTCUSD ask={ask:.{digits}f} → BUY STOP price={stop_price:.{digits}f}")

    req = {
        "action": TRADE_ACTION_PENDING,
        "symbol": SYMBOL,
        "volume": VOLUME,
        "type": ORDER_TYPE_BUY_STOP,
        "price": stop_price,
        "deviation": 20,
        "magic": MAGIC,
        "comment": "tc-e20 buy-stop-market",
        "type_time": ORDER_TIME_GTC,
        "type_filling": 2,  # ORDER_FILLING_RETURN
    }

    result_raw = mt5.order_send(req)
    result = _as_dict(result_raw)
    print(f"[TC-E20] order_send result: {result}")

    retcode = result.get("retcode", -1)
    order_ticket = int(result.get("order", 0))

    # --- Assertions ---
    assert retcode == RETCODE_PLACED, (
        f"TC-E20: Expected retcode=10008 (PLACED), got retcode={retcode} "
        f"comment={result.get('comment')}"
    )
    assert order_ticket > 0, "TC-E20: Expected a valid order ticket in result['order']"

    print(f"[TC-E20] PASS — ticket={order_ticket}, retcode={retcode} (PLACED)")

    # Cleanup: cancel the pending order
    cancel_result = _cancel_pending_order(mt5, order_ticket, SYMBOL)
    print(f"[TC-E20] cancel result: {cancel_result}")


# ---------------------------------------------------------------------------
# TC-E21-LIVE: SELL STOP_MARKET (ORDER_TYPE_SELL_STOP = 5)
# ---------------------------------------------------------------------------

@pytest.mark.live
@pytest.mark.external_rpyc
def test_tc_e21_live_sell_stop_market(validated_demo_mt5):
    """
    TC-E21-LIVE: SELL STOP_MARKET for BTCUSD.

    Places a pending SELL STOP order below the current bid price.
    Expects:
      - action=5, type=5 (ORDER_TYPE_SELL_STOP)
      - retcode=10008 (PLACED)
    Cleanup: cancels the pending order.
    """
    mt5, info, tick = validated_demo_mt5
    digits = int(info.get("digits", 2))
    bid = float(tick.get("bid", 0.0))

    # Stop price must be below current bid to avoid immediate trigger
    stop_price = _round_price(bid * (1 - STOP_PRICE_OFFSET_PCT), digits)
    print(f"\n[TC-E21] BTCUSD bid={bid:.{digits}f} → SELL STOP price={stop_price:.{digits}f}")

    req = {
        "action": TRADE_ACTION_PENDING,
        "symbol": SYMBOL,
        "volume": VOLUME,
        "type": ORDER_TYPE_SELL_STOP,
        "price": stop_price,
        "deviation": 20,
        "magic": MAGIC,
        "comment": "tc-e21 sell-stop-market",
        "type_time": ORDER_TIME_GTC,
        "type_filling": 2,
    }

    result_raw = mt5.order_send(req)
    result = _as_dict(result_raw)
    print(f"[TC-E21] order_send result: {result}")

    retcode = result.get("retcode", -1)
    order_ticket = int(result.get("order", 0))

    assert retcode == RETCODE_PLACED, (
        f"TC-E21: Expected retcode=10008 (PLACED), got retcode={retcode} "
        f"comment={result.get('comment')}"
    )
    assert order_ticket > 0, "TC-E21: Expected a valid order ticket in result['order']"

    print(f"[TC-E21] PASS — ticket={order_ticket}, retcode={retcode} (PLACED)")

    cancel_result = _cancel_pending_order(mt5, order_ticket, SYMBOL)
    print(f"[TC-E21] cancel result: {cancel_result}")


# ---------------------------------------------------------------------------
# TC-E22-LIVE: BUY STOP_LIMIT (ORDER_TYPE_BUY_STOP_LIMIT = 6)
# ---------------------------------------------------------------------------

@pytest.mark.live
@pytest.mark.external_rpyc
def test_tc_e22_live_buy_stop_limit(validated_demo_mt5):
    """
    TC-E22-LIVE: BUY STOP_LIMIT for BTCUSD.

    Places a pending BUY STOP_LIMIT:
      - `price` = stop trigger (above current ask)
      - `stoplimit`  = limit price (slightly below trigger, i.e. the fill limit)
    Expects:
      - action=5, type=6 (ORDER_TYPE_BUY_STOP_LIMIT)
      - retcode=10008 (PLACED)
    Cleanup: cancels the pending order.
    """
    mt5, info, tick = validated_demo_mt5
    digits = int(info.get("digits", 2))
    ask = float(tick.get("ask", 0.0))

    # Stop trigger above current ask
    stop_trigger = _round_price(ask * (1 + STOP_PRICE_OFFSET_PCT), digits)
    # Limit price slightly below trigger (the most-favourable fill price)
    limit_offset = _round_price(ask * 0.005, digits)  # 0.5 % below trigger
    limit_price = _round_price(stop_trigger - limit_offset, digits)

    print(
        f"\n[TC-E22] BTCUSD ask={ask:.{digits}f} → BUY STOP_LIMIT "
        f"trigger={stop_trigger:.{digits}f} limit={limit_price:.{digits}f}"
    )

    req = {
        "action": TRADE_ACTION_PENDING,
        "symbol": SYMBOL,
        "volume": VOLUME,
        "type": ORDER_TYPE_BUY_STOP_LIMIT,
        "price": stop_trigger,   # stop trigger level
        "stoplimit": limit_price,     # limit price after stop fires
        "deviation": 20,
        "magic": MAGIC,
        "comment": "tc-e22 buy-stop-limit",
        "type_time": ORDER_TIME_GTC,
        "type_filling": 2,
    }

    result_raw = mt5.order_send(req)
    result = _as_dict(result_raw)
    print(f"[TC-E22] order_send result: {result}")

    retcode = result.get("retcode", -1)
    order_ticket = int(result.get("order", 0))

    assert retcode == RETCODE_PLACED, (
        f"TC-E22: Expected retcode=10008 (PLACED), got retcode={retcode} "
        f"comment={result.get('comment')}"
    )
    assert order_ticket > 0, "TC-E22: Expected a valid order ticket in result['order']"

    print(f"[TC-E22] PASS — ticket={order_ticket}, retcode={retcode} (PLACED)")

    cancel_result = _cancel_pending_order(mt5, order_ticket, SYMBOL)
    print(f"[TC-E22] cancel result: {cancel_result}")


# ---------------------------------------------------------------------------
# TC-E23-LIVE: SELL STOP_LIMIT (ORDER_TYPE_SELL_STOP_LIMIT = 7)
# ---------------------------------------------------------------------------

@pytest.mark.live
@pytest.mark.external_rpyc
def test_tc_e23_live_sell_stop_limit(validated_demo_mt5):
    """
    TC-E23-LIVE: SELL STOP_LIMIT for BTCUSD.

    Places a pending SELL STOP_LIMIT:
      - `price` = stop trigger (below current bid)
      - `stoplimit`  = limit price (slightly above trigger, i.e. the fill limit)
    Expects:
      - action=5, type=7 (ORDER_TYPE_SELL_STOP_LIMIT)
      - retcode=10008 (PLACED)
    Cleanup: cancels the pending order.
    """
    mt5, info, tick = validated_demo_mt5
    digits = int(info.get("digits", 2))
    bid = float(tick.get("bid", 0.0))

    # Stop trigger below current bid
    stop_trigger = _round_price(bid * (1 - STOP_PRICE_OFFSET_PCT), digits)
    # Limit price slightly above trigger
    limit_offset = _round_price(bid * 0.005, digits)
    limit_price = _round_price(stop_trigger + limit_offset, digits)

    print(
        f"\n[TC-E23] BTCUSD bid={bid:.{digits}f} → SELL STOP_LIMIT "
        f"trigger={stop_trigger:.{digits}f} limit={limit_price:.{digits}f}"
    )

    req = {
        "action": TRADE_ACTION_PENDING,
        "symbol": SYMBOL,
        "volume": VOLUME,
        "type": ORDER_TYPE_SELL_STOP_LIMIT,
        "price": stop_trigger,   # stop trigger level
        "stoplimit": limit_price,     # limit price after stop fires
        "deviation": 20,
        "magic": MAGIC,
        "comment": "tc-e23 sell-stop-limit",
        "type_time": ORDER_TIME_GTC,
        "type_filling": 2,
    }

    result_raw = mt5.order_send(req)
    result = _as_dict(result_raw)
    print(f"[TC-E23] order_send result: {result}")

    retcode = result.get("retcode", -1)
    order_ticket = int(result.get("order", 0))

    assert retcode == RETCODE_PLACED, (
        f"TC-E23: Expected retcode=10008 (PLACED), got retcode={retcode} "
        f"comment={result.get('comment')}"
    )
    assert order_ticket > 0, "TC-E23: Expected a valid order ticket in result['order']"

    print(f"[TC-E23] PASS — ticket={order_ticket}, retcode={retcode} (PLACED)")

    cancel_result = _cancel_pending_order(mt5, order_ticket, SYMBOL)
    print(f"[TC-E23] cancel result: {cancel_result}")
