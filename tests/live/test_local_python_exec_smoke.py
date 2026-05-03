"""
test_local_python_exec_smoke.py
Live execution smoke test using the LOCAL_PYTHON access mode.

Validates the minimal execution path using the official MetaTrader5 Python package
installed directly on the local Windows machine (no RPyC gateway needed):
    MetaTrader5 package → pre-order validations (account type, symbol_info, tick)
                        → order_send (minimum volume, market BUY)
                        → positions_get / history_orders_get / history_deals_get
                        → close position (market SELL) or document manual procedure

No automated strategy, no position sizing, no optimisation.

Markers: @pytest.mark.live  @pytest.mark.local_python  @pytest.mark.demo_execution

Safety locks (ALL must be satisfied for any order to be sent):
  1. MT5_ENABLE_LIVE_EXECUTION=1  — explicit opt-in
  2. MT5_ACCOUNT_NUMBER           — login to validate against account_info()
  3. MT5_TEST_ORDER_QTY           — volume must be stated explicitly; no default
  4. account_info().trade_mode == ACCOUNT_TRADE_MODE_DEMO (0)  — demo only

Optional env vars:
  MT5_TEST_SYMBOL      — symbol to trade (default: USTEC)
  MT5_TERMINAL_PATH    — path to terminal executable; if unset, MT5 finds it automatically
  MT5_LOGIN            — MT5 account login for initialize() auto-login
  MT5_PASSWORD         — MT5 account password for initialize() auto-login
  MT5_SERVER           — MT5 server name for initialize() auto-login

Run command:
  $env:MT5_ENABLE_LIVE_EXECUTION="1"
  $env:MT5_ACCOUNT_NUMBER="<login>"
  $env:MT5_TEST_ORDER_QTY="0.1"
  pytest -m "live and local_python and demo_execution" \\
    tests/live/test_local_python_exec_smoke.py -v
"""

import os
import time
import datetime

import pytest

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
MT5_ACCOUNT_NUMBER = os.environ.get("MT5_ACCOUNT_NUMBER", "")
MT5_TEST_SYMBOL = os.environ.get("MT5_TEST_SYMBOL", "USTEC")
MT5_TEST_ORDER_QTY_STR = os.environ.get("MT5_TEST_ORDER_QTY", "")
MT5_ENABLE_LIVE_EXECUTION = os.environ.get("MT5_ENABLE_LIVE_EXECUTION", "")
MT5_TERMINAL_PATH = os.environ.get("MT5_TERMINAL_PATH", None)
MT5_LOGIN = os.environ.get("MT5_LOGIN", "")
MT5_PASSWORD = os.environ.get("MT5_PASSWORD", "")
MT5_SERVER = os.environ.get("MT5_SERVER", "")

# ---------------------------------------------------------------------------
# MT5 constants (numeric values, no import of MetaTrader5 package needed here)
# ---------------------------------------------------------------------------
ACCOUNT_TRADE_MODE_DEMO = 0
TRADE_ACTION_DEAL = 1
ORDER_TYPE_BUY = 0
ORDER_TYPE_SELL = 1

ORDER_FILLING_FOK = 0
ORDER_FILLING_IOC = 1
ORDER_FILLING_RETURN = 2

# symbol_info().filling_mode bitmask:
#   bit 0 (1) → ORDER_FILLING_FOK is allowed
#   bit 1 (2) → ORDER_FILLING_IOC is allowed
#   bit 2 (4) → ORDER_FILLING_RETURN is allowed
_FILLING_PRIORITY = [
    (2, ORDER_FILLING_IOC),     # prefer IOC for CFDs/forex
    (1, ORDER_FILLING_FOK),
    (4, ORDER_FILLING_RETURN),
]


def _pick_filling_mode(filling_mode_bitmask: int) -> int:
    """Return the best supported ORDER_FILLING_* constant for this symbol."""
    for bit, mode in _FILLING_PRIORITY:
        if filling_mode_bitmask & bit:
            return mode
    return ORDER_FILLING_RETURN


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _as_dict(obj) -> dict:
    """Coerce a MetaTrader5 named-tuple result to a plain dict."""
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return dict(obj)
    if hasattr(obj, "_asdict"):
        return dict(obj._asdict())
    return {}


def _as_list(obj) -> list:
    """Coerce a MetaTrader5 sequence result to a plain Python list of dicts."""
    if obj is None:
        return []
    try:
        return [_as_dict(item) for item in obj]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def mt5_local():
    """
    Module-scoped MetaTrader5 connection via the official Python package.
    Skips if the package is not installed or initialize() fails.
    """
    try:
        import MetaTrader5 as mt5
    except ImportError:
        pytest.skip(
            "MetaTrader5 package not installed. "
            "Install it with: pip install MetaTrader5  (Windows only)"
        )

    init_kwargs = {}
    if MT5_TERMINAL_PATH:
        init_kwargs["path"] = MT5_TERMINAL_PATH
    if MT5_LOGIN:
        init_kwargs["login"] = int(MT5_LOGIN)
    if MT5_PASSWORD:
        init_kwargs["password"] = MT5_PASSWORD
    if MT5_SERVER:
        init_kwargs["server"] = MT5_SERVER

    ok = mt5.initialize(**init_kwargs)
    if not ok:
        err = mt5.last_error()
        pytest.skip(f"MetaTrader5.initialize() failed: {err}")

    yield mt5

    mt5.shutdown()


# ---------------------------------------------------------------------------
# Pre-execution validation tests (no orders sent)
# ---------------------------------------------------------------------------

@pytest.mark.live
@pytest.mark.local_python
def test_local_python_smoke_gateway_reachable(mt5_local):
    """MetaTrader5 package can initialize and return terminal_info or account_info."""
    mt5 = mt5_local
    info = mt5.terminal_info()
    acc = mt5.account_info()
    assert info is not None or acc is not None, (
        "Both terminal_info() and account_info() returned None — "
        "MT5 terminal may not be running or not connected to a broker."
    )
    if info:
        d = _as_dict(info)
        print(f"\n[local-python] terminal: {d.get('name')} build={d.get('build')} "
              f"connected={d.get('connected')}")


@pytest.mark.live
@pytest.mark.local_python
def test_local_python_smoke_account_is_demo(mt5_local):
    """account_info().trade_mode must be ACCOUNT_TRADE_MODE_DEMO (0)."""
    mt5 = mt5_local
    acc_raw = mt5.account_info()
    assert acc_raw is not None, "account_info() returned None"

    acc = _as_dict(acc_raw)
    trade_mode = acc.get("trade_mode", -1)
    assert trade_mode == ACCOUNT_TRADE_MODE_DEMO, (
        f"account trade_mode={trade_mode} is NOT demo (expected 0). "
        "Execution smoke tests must only run on demo accounts."
    )

    if MT5_ACCOUNT_NUMBER:
        login = int(acc.get("login", -1))
        assert login == int(MT5_ACCOUNT_NUMBER), (
            f"Account login {login} does not match MT5_ACCOUNT_NUMBER={MT5_ACCOUNT_NUMBER}."
        )


@pytest.mark.live
@pytest.mark.local_python
def test_local_python_smoke_symbol_tradeable(mt5_local):
    """symbol_info() for MT5_TEST_SYMBOL must be available and have valid volume limits."""
    mt5 = mt5_local
    symbol = MT5_TEST_SYMBOL

    ok = mt5.symbol_select(symbol, True)
    assert ok, f"symbol_select({symbol}, True) returned False"

    info_raw = mt5.symbol_info(symbol)
    assert info_raw is not None, f"symbol_info({symbol}) returned None"

    info = _as_dict(info_raw)
    volume_min = float(info.get("volume_min", 0.0))
    volume_step = float(info.get("volume_step", 0.0))
    volume_max = float(info.get("volume_max", 0.0))

    assert volume_min > 0, f"{symbol}: volume_min={volume_min} must be > 0"
    assert volume_step > 0, f"{symbol}: volume_step={volume_step} must be > 0"
    assert volume_max >= volume_min, f"{symbol}: volume_max < volume_min"

    tick_raw = mt5.symbol_info_tick(symbol)
    assert tick_raw is not None, f"symbol_info_tick({symbol}) returned None"
    tick = _as_dict(tick_raw)
    assert float(tick.get("ask", 0.0)) > 0, f"{symbol}: ask price is 0 — market may be closed"

    filling_bitmask = int(info.get("filling_mode", 0))
    chosen = _pick_filling_mode(filling_bitmask)
    print(
        f"\n[local-python] {symbol} filling_mode bitmask={filling_bitmask} "
        f"→ will use type_filling={chosen}"
    )


# ---------------------------------------------------------------------------
# Execution smoke (opt-in required)
# ---------------------------------------------------------------------------

@pytest.mark.live
@pytest.mark.local_python
@pytest.mark.demo_execution
def test_local_python_smoke_submit_and_close_ustec(mt5_local):
    """
    Full execution smoke for USTEC (or MT5_TEST_SYMBOL) via LOCAL_PYTHON:
      1. Validate opt-in and env vars.
      2. Validate demo account and symbol.
      3. Send minimum market BUY order.
      4. Query positions / history_orders / history_deals.
      5. Attempt to close the opened position with a market SELL.
      6. Report final position state.

    Safety locks that must ALL be satisfied before any order is sent:
      - MT5_ENABLE_LIVE_EXECUTION == "1"
      - MT5_TEST_ORDER_QTY is set explicitly
      - account trade_mode == 0 (demo)
      - symbol volume_min <= requested quantity
    """
    # ------------------------------------------------------------------
    # Lock 1: explicit opt-in
    # ------------------------------------------------------------------
    if MT5_ENABLE_LIVE_EXECUTION != "1":
        pytest.skip(
            "MT5_ENABLE_LIVE_EXECUTION is not set to '1'. "
            "Set MT5_ENABLE_LIVE_EXECUTION=1 to run execution smoke tests."
        )

    # ------------------------------------------------------------------
    # Lock 2: explicit volume
    # ------------------------------------------------------------------
    if not MT5_TEST_ORDER_QTY_STR:
        pytest.skip(
            "MT5_TEST_ORDER_QTY is not set. "
            "Provide an explicit volume, e.g. MT5_TEST_ORDER_QTY=0.1"
        )
    try:
        requested_qty = float(MT5_TEST_ORDER_QTY_STR)
    except ValueError:
        pytest.fail(
            f"MT5_TEST_ORDER_QTY={MT5_TEST_ORDER_QTY_STR!r} is not a valid float."
        )

    mt5 = mt5_local
    symbol = MT5_TEST_SYMBOL

    # ------------------------------------------------------------------
    # Lock 3: demo account
    # ------------------------------------------------------------------
    acc_raw = mt5.account_info()
    assert acc_raw is not None, "account_info() returned None — cannot validate demo account"

    acc = _as_dict(acc_raw)
    trade_mode = acc.get("trade_mode", -1)
    assert trade_mode == ACCOUNT_TRADE_MODE_DEMO, (
        f"SAFETY: account trade_mode={trade_mode} is not DEMO. Aborting."
    )

    if MT5_ACCOUNT_NUMBER:
        login = int(acc.get("login", -1))
        assert login == int(MT5_ACCOUNT_NUMBER), (
            f"SAFETY: login={login} does not match MT5_ACCOUNT_NUMBER={MT5_ACCOUNT_NUMBER}. Aborting."
        )

    # Detect account margin mode: 0=netting, 2=hedging
    account_margin_mode = int(acc.get("margin_mode", 0))
    is_hedging = (account_margin_mode == 2)
    print(f"\n[local-python] margin_mode={account_margin_mode} ({'hedging' if is_hedging else 'netting'})")

    # ------------------------------------------------------------------
    # Lock 4: symbol validation and volume check
    # ------------------------------------------------------------------
    mt5.symbol_select(symbol, True)
    info_raw = mt5.symbol_info(symbol)
    assert info_raw is not None, f"symbol_info({symbol}) returned None"

    info = _as_dict(info_raw)
    volume_min = float(info.get("volume_min", 0.0))
    volume_step = float(info.get("volume_step", 0.0))
    assert requested_qty >= volume_min, (
        f"Requested qty {requested_qty} < volume_min {volume_min} for {symbol}. "
        "Increase MT5_TEST_ORDER_QTY."
    )

    filling_bitmask = int(info.get("filling_mode", 0))
    chosen_filling = _pick_filling_mode(filling_bitmask)
    print(
        f"[local-python] {symbol} filling_mode bitmask={filling_bitmask} "
        f"→ using type_filling={chosen_filling} "
        f"({'FOK' if chosen_filling == ORDER_FILLING_FOK else 'IOC' if chosen_filling == ORDER_FILLING_IOC else 'RETURN'})"
    )

    if volume_step > 0:
        volume = round(round(requested_qty / volume_step) * volume_step, 8)
    else:
        volume = requested_qty

    tick_raw = mt5.symbol_info_tick(symbol)
    assert tick_raw is not None, f"symbol_info_tick({symbol}) returned None"
    tick = _as_dict(tick_raw)
    ask_price = float(tick.get("ask", 0.0))
    assert ask_price > 0, f"{symbol}: ask price is 0 — market may be closed"

    # ------------------------------------------------------------------
    # Step 3: Send market BUY order
    # ------------------------------------------------------------------
    buy_request = {
        "action": TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": ORDER_TYPE_BUY,
        "price": ask_price,
        "deviation": 20,
        "magic": 20260501,
        "comment": "nt_mt5 lpython smoke BUY",
        "type_time": 0,
        "type_filling": chosen_filling,
    }

    buy_result_raw = mt5.order_send(buy_request)
    assert buy_result_raw is not None, (
        f"order_send(BUY) returned None. MT5 last_error: {mt5.last_error()}"
    )

    buy_result = _as_dict(buy_result_raw)
    print(f"[local-python] order_send BUY result: {buy_result}")

    buy_retcode = buy_result.get("retcode", -1)
    assert buy_retcode in (10008, 10009, 10010), (
        f"order_send BUY failed: retcode={buy_retcode}, comment={buy_result.get('comment')}"
    )

    buy_order_ticket = buy_result.get("order", 0)
    buy_deal_ticket = buy_result.get("deal", 0)
    print(f"[local-python] BUY accepted: order_ticket={buy_order_ticket}, deal_ticket={buy_deal_ticket}")

    time.sleep(1)

    # ------------------------------------------------------------------
    # Step 4: Query positions / history
    # ------------------------------------------------------------------
    positions = _as_list(mt5.positions_get(symbol=symbol))
    print(f"[local-python] positions_get({symbol}): {len(positions)} position(s)")
    for pos in positions:
        print(f"  ticket={pos.get('ticket')} type={pos.get('type')} "
              f"volume={pos.get('volume')} price_open={pos.get('price_open')}")

    _from = datetime.datetime.utcnow() - datetime.timedelta(hours=2)
    _to = datetime.datetime.utcnow() + datetime.timedelta(minutes=5)

    history_orders = _as_list(mt5.history_orders_get(_from, _to, group=f"*{symbol}*"))
    print(f"[local-python] history_orders_get: {len(history_orders)} order(s)")

    history_deals = _as_list(mt5.history_deals_get(_from, _to, group=f"*{symbol}*"))
    print(f"[local-python] history_deals_get: {len(history_deals)} deal(s)")
    for deal in history_deals:
        print(f"  ticket={deal.get('ticket')} order={deal.get('order')} "
              f"type={deal.get('type')} volume={deal.get('volume')} "
              f"price={deal.get('price')} commission={deal.get('commission')}")

    # ------------------------------------------------------------------
    # Step 5: Attempt to close the opened position
    # ------------------------------------------------------------------
    position_to_close = next(
        (p for p in positions if p.get("ticket") or p.get("volume", 0) > 0),
        None,
    )

    close_attempted = False
    if position_to_close:
        tick_close_raw = mt5.symbol_info_tick(symbol)
        bid_price = float(_as_dict(tick_close_raw).get("bid", 0.0)) if tick_close_raw else 0.0

        if bid_price <= 0:
            print(
                "[local-python] WARNING: bid price is 0 — cannot safely close automatically. "
                "MANUAL ACTION REQUIRED: close the open position in the MT5 terminal."
            )
        else:
            close_volume = float(position_to_close.get("volume", volume))
            pos_ticket = int(position_to_close.get("ticket", 0))

            close_request = {
                "action": TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": close_volume,
                "type": ORDER_TYPE_SELL,
                "price": bid_price,
                "deviation": 20,
                "magic": 20260501,
                "comment": "nt_mt5 lpython smoke CLOSE",
                "type_time": 0,
                "type_filling": chosen_filling,
            }
            # In hedging mode, position ticket is required to close the specific
            # position instead of opening a new short.
            if is_hedging and pos_ticket:
                close_request["position"] = pos_ticket
                print(f"[local-python] Hedging mode: closing position ticket={pos_ticket}")

            close_result_raw = mt5.order_send(close_request)
            if close_result_raw is None:
                print(
                    f"[local-python] WARNING: order_send(CLOSE) returned None. "
                    f"MT5 last_error: {mt5.last_error()}. "
                    "MANUAL ACTION REQUIRED: close the open position in the MT5 terminal."
                )
            else:
                close_result = _as_dict(close_result_raw)
                print(f"[local-python] order_send CLOSE result: {close_result}")
                close_retcode = close_result.get("retcode", -1)
                close_attempted = True
                if close_retcode not in (10008, 10009, 10010):
                    print(
                        f"[local-python] WARNING: CLOSE order retcode={close_retcode} "
                        f"({close_result.get('comment')}). "
                        "MANUAL ACTION REQUIRED: verify and close position in MT5 terminal."
                    )
    else:
        print(
            "[local-python] No open position found after BUY. "
            "Position may have been closed automatically (netting account or stop-out)."
        )

    # ------------------------------------------------------------------
    # Step 6: Final position state
    # ------------------------------------------------------------------
    time.sleep(1)
    final_positions = _as_list(mt5.positions_get(symbol=symbol))
    print(f"[local-python] Final open positions for {symbol}: {len(final_positions)}")
    if final_positions:
        for pos in final_positions:
            print(
                f"  ticket={pos.get('ticket')} volume={pos.get('volume')} "
                f"price_open={pos.get('price_open')} profit={pos.get('profit')}"
            )
        if not close_attempted:
            print(
                "[local-python] MANUAL ACTION REQUIRED: "
                f"There are still {len(final_positions)} open position(s) for {symbol}. "
                "Close them in the MT5 terminal to avoid unintended exposure."
            )

    # ------------------------------------------------------------------
    # Assertions
    # ------------------------------------------------------------------
    assert buy_retcode in (10008, 10009, 10010), (
        f"BUY order was not accepted. retcode={buy_retcode}"
    )
    # History may not be immediately visible on some brokers (eventual consistency).
    if len(history_deals) == 0 and len(history_orders) == 0:
        print(
            "[local-python] NOTE: history_deals and history_orders returned 0 results. "
            "This is expected on some brokers immediately after a fill (eventual consistency). "
            "Re-run the data smoke or wait a few seconds and query manually."
        )
