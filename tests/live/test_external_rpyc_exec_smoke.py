"""
test_external_rpyc_exec_smoke.py
Live execution smoke test for the EXTERNAL_RPYC gateway.

Validates the minimal execution path against a real demo MT5 account:
    RPyC gateway → pre-order validations (account type, symbol_info, tick)
                 → order_send (minimum volume, market BUY)
                 → positions_get / history_orders_get / history_deals_get
                 → close position (market SELL) or document manual procedure

No automated strategy, no position sizing, no optimisation.

Markers: @pytest.mark.live  @pytest.mark.external_rpyc  @pytest.mark.demo_execution

Safety locks (ALL must be satisfied for any order to be sent):
  1. MT5_ENABLE_LIVE_EXECUTION=1  — explicit opt-in
  2. MT5_HOST and MT5_PORT        — gateway location
  3. MT5_ACCOUNT_NUMBER           — login to validate against account_info()
  4. MT5_TEST_ORDER_QTY           — volume must be stated explicitly; no default
  5. account_info().trade_mode == ACCOUNT_TRADE_MODE_DEMO (0)  — demo only

Run command:
  MT5_ENABLE_LIVE_EXECUTION=1 \\
    MT5_HOST=127.0.0.1 MT5_PORT=18812 \\
    MT5_ACCOUNT_NUMBER=<login> \\
    MT5_TEST_ORDER_QTY=0.1 \\
    pytest -m "live and external_rpyc and demo_execution" \\
      tests/live/test_external_rpyc_exec_smoke.py -v
"""

import os
import time
import datetime

import pytest

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
MT5_HOST = os.environ.get("MT5_HOST", "")
MT5_PORT_STR = os.environ.get("MT5_PORT", "")
MT5_ACCOUNT_NUMBER = os.environ.get("MT5_ACCOUNT_NUMBER", "")
MT5_TEST_SYMBOL = os.environ.get("MT5_TEST_SYMBOL", "USTEC")
MT5_TEST_ORDER_QTY_STR = os.environ.get("MT5_TEST_ORDER_QTY", "")
MT5_ENABLE_LIVE_EXECUTION = os.environ.get("MT5_ENABLE_LIVE_EXECUTION", "")

_MISSING_CONN = not (MT5_HOST and MT5_PORT_STR)
_SKIP_NO_CONN = (
    "Live EXTERNAL_RPYC tests require MT5_HOST and MT5_PORT. "
    "Set them to point at a running MT5 RPyC gateway."
)

# ---------------------------------------------------------------------------
# MT5 constants (numeric values, no import of MetaTrader5 package needed)
# ---------------------------------------------------------------------------
ACCOUNT_TRADE_MODE_DEMO = 0
TRADE_ACTION_DEAL = 1          # immediate order
ORDER_TYPE_BUY = 0
ORDER_TYPE_SELL = 1

# Order filling type constants
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
    """
    Return the best supported ORDER_FILLING_* constant given a symbol's
    filling_mode bitmask from symbol_info().
    Defaults to ORDER_FILLING_RETURN if nothing matches (should not happen).
    """
    for bit, mode in _FILLING_PRIORITY:
        if filling_mode_bitmask & bit:
            return mode
    return ORDER_FILLING_RETURN


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def mt5_rpyc_conn():
    """
    Module-scoped RPyC connection.
    Skips if MT5_HOST/MT5_PORT are absent or connection fails.
    """
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
        pass  # not all gateways expose initialize()

    yield mt5

    conn.close()


# ---------------------------------------------------------------------------
# Helper: obtain dict from RPyC-proxied result
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
    # numpy structured array row or similar
    try:
        return {k: local[k] for k in local.dtype.names}
    except Exception:
        return {}


def _as_list(obj) -> list:
    """Coerce an RPyC-proxied sequence to a plain Python list of dicts."""
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


# ---------------------------------------------------------------------------
# Pre-execution validation tests (no orders sent)
# ---------------------------------------------------------------------------

@pytest.mark.live
@pytest.mark.external_rpyc
def test_exec_smoke_gateway_reachable(mt5_rpyc_conn):
    """Gateway is reachable and returns account_info or terminal_info."""
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
def test_exec_smoke_account_is_demo(mt5_rpyc_conn):
    """
    account_info().trade_mode must be ACCOUNT_TRADE_MODE_DEMO (0).
    This guard runs before any order is attempted.
    """
    mt5 = mt5_rpyc_conn
    try:
        acc_raw = mt5.account_info()
    except Exception as exc:
        pytest.skip(f"account_info() raised: {exc}")

    acc = _as_dict(acc_raw)
    assert acc, "account_info() returned empty result"

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
@pytest.mark.external_rpyc
def test_exec_smoke_symbol_tradeable(mt5_rpyc_conn):
    """
    symbol_info() for MT5_TEST_SYMBOL (default USTEC) must be available,
    visible, and have a non-zero volume_min.
    """
    mt5 = mt5_rpyc_conn
    symbol = MT5_TEST_SYMBOL

    # Ensure symbol is selected in Market Watch
    try:
        mt5.symbol_select(symbol, True)
    except Exception as exc:
        pytest.skip(f"symbol_select({symbol}) raised: {exc}")

    try:
        info_raw = mt5.symbol_info(symbol)
    except Exception as exc:
        pytest.skip(f"symbol_info({symbol}) raised: {exc}")

    info = _as_dict(info_raw)
    assert info, f"symbol_info({symbol}) returned empty result"

    volume_min = float(info.get("volume_min", 0.0))
    volume_step = float(info.get("volume_step", 0.0))
    volume_max = float(info.get("volume_max", 0.0))

    assert volume_min > 0, f"{symbol}: volume_min={volume_min} must be > 0"
    assert volume_step > 0, f"{symbol}: volume_step={volume_step} must be > 0"
    assert volume_max >= volume_min, f"{symbol}: volume_max={volume_max} < volume_min={volume_min}"

    # Ensure a current tick is available
    try:
        tick_raw = mt5.symbol_info_tick(symbol)
    except Exception as exc:
        pytest.skip(f"symbol_info_tick({symbol}) raised: {exc}")

    tick = _as_dict(tick_raw)
    assert float(tick.get("ask", 0.0)) > 0, f"{symbol}: ask price is 0 — market may be closed"

    filling_mode_bitmask = int(info.get("filling_mode", 0))
    chosen = _pick_filling_mode(filling_mode_bitmask)
    print(
        f"\n[symbol-check] {symbol} filling_mode bitmask={filling_mode_bitmask} "
        f"→ will use type_filling={chosen}"
    )


# ---------------------------------------------------------------------------
# Execution smoke (opt-in required)
# ---------------------------------------------------------------------------

@pytest.mark.live
@pytest.mark.external_rpyc
@pytest.mark.demo_execution
def test_exec_smoke_submit_and_close_ustec(mt5_rpyc_conn):
    """
    Full execution smoke for USTEC (or MT5_TEST_SYMBOL):
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

    mt5 = mt5_rpyc_conn
    symbol = MT5_TEST_SYMBOL

    # ------------------------------------------------------------------
    # Lock 3: demo account
    # ------------------------------------------------------------------
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
            f"SAFETY: login={login} does not match MT5_ACCOUNT_NUMBER={MT5_ACCOUNT_NUMBER}. Aborting."
        )

    # Detect account margin mode: 0=netting, 2=hedging
    # In hedging mode, close orders must include position=<ticket>.
    account_margin_mode = int(acc.get("margin_mode", 0))
    is_hedging = (account_margin_mode == 2)
    print(f"[exec-smoke] margin_mode={account_margin_mode} ({'hedging' if is_hedging else 'netting'})")

    # ------------------------------------------------------------------
    # Lock 4: symbol validation and volume check
    # ------------------------------------------------------------------
    try:
        mt5.symbol_select(symbol, True)
        info_raw = mt5.symbol_info(symbol)
    except Exception as exc:
        pytest.skip(f"Symbol validation failed for {symbol}: {exc}")

    info = _as_dict(info_raw)
    assert info, f"symbol_info({symbol}) returned empty result"

    volume_min = float(info.get("volume_min", 0.0))
    volume_step = float(info.get("volume_step", 0.0))
    assert requested_qty >= volume_min, (
        f"Requested qty {requested_qty} < volume_min {volume_min} for {symbol}. "
        "Increase MT5_TEST_ORDER_QTY."
    )

    # Detect which filling mode the broker supports for this symbol
    filling_mode_bitmask = int(info.get("filling_mode", 0))
    chosen_filling = _pick_filling_mode(filling_mode_bitmask)
    print(
        f"[exec-smoke] {symbol} filling_mode bitmask={filling_mode_bitmask} "
        f"→ using type_filling={chosen_filling} "
        f"({'FOK' if chosen_filling == ORDER_FILLING_FOK else 'IOC' if chosen_filling == ORDER_FILLING_IOC else 'RETURN'})"
    )

    # Round to nearest valid step
    if volume_step > 0:
        steps = round(requested_qty / volume_step)
        volume = round(steps * volume_step, 8)
    else:
        volume = requested_qty

    # Get current ask price for BUY
    try:
        tick_raw = mt5.symbol_info_tick(symbol)
    except Exception as exc:
        pytest.skip(f"symbol_info_tick({symbol}) raised: {exc}")

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
        "comment": "nt_mt5 exec smoke BUY",
        "type_time": 0,              # ORDER_TIME_GTC
        "type_filling": chosen_filling,
    }

    try:
        buy_result_raw = mt5.order_send(buy_request)
    except Exception as exc:
        pytest.fail(f"order_send(BUY) raised an exception: {exc}")

    buy_result = _as_dict(buy_result_raw)
    print(f"\n[exec-smoke] order_send BUY result: {buy_result}")

    buy_retcode = buy_result.get("retcode", -1)
    assert buy_retcode in (10008, 10009, 10010), (
        f"order_send BUY failed: retcode={buy_retcode}, comment={buy_result.get('comment')}"
    )

    buy_order_ticket = buy_result.get("order", 0)
    buy_deal_ticket = buy_result.get("deal", 0)
    print(f"[exec-smoke] BUY accepted: order_ticket={buy_order_ticket}, deal_ticket={buy_deal_ticket}")

    # Brief pause for MT5 to settle the position
    time.sleep(1)

    # ------------------------------------------------------------------
    # Step 4: Query positions / history
    # ------------------------------------------------------------------
    try:
        positions_raw = mt5.positions_get(symbol=symbol)
    except Exception as exc:
        print(f"[exec-smoke] positions_get raised: {exc}")
        positions_raw = None

    positions = _as_list(positions_raw)
    print(f"[exec-smoke] positions_get({symbol}): {len(positions)} position(s)")
    for pos in positions:
        print(f"  ticket={pos.get('ticket')} type={pos.get('type')} "
              f"volume={pos.get('volume')} price_open={pos.get('price_open')}")

    _from = datetime.datetime.utcnow() - datetime.timedelta(hours=2)
    _to = datetime.datetime.utcnow() + datetime.timedelta(minutes=5)

    try:
        history_orders_raw = mt5.history_orders_get(_from, _to, group=f"*{symbol}*")
    except Exception as exc:
        print(f"[exec-smoke] history_orders_get raised: {exc}")
        history_orders_raw = None

    history_orders = _as_list(history_orders_raw)
    print(f"[exec-smoke] history_orders_get: {len(history_orders)} order(s)")

    try:
        history_deals_raw = mt5.history_deals_get(_from, _to, group=f"*{symbol}*")
    except Exception as exc:
        print(f"[exec-smoke] history_deals_get raised: {exc}")
        history_deals_raw = None

    history_deals = _as_list(history_deals_raw)
    print(f"[exec-smoke] history_deals_get: {len(history_deals)} deal(s)")
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
        # Get current bid price for SELL
        try:
            tick_close_raw = mt5.symbol_info_tick(symbol)
            tick_close = _as_dict(tick_close_raw)
            bid_price = float(tick_close.get("bid", 0.0))
        except Exception:
            bid_price = 0.0

        if bid_price <= 0:
            print(
                "[exec-smoke] WARNING: bid price is 0 — cannot safely close position automatically. "
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
                "comment": "nt_mt5 exec smoke CLOSE",
                "type_time": 0,
                "type_filling": chosen_filling,
            }
            # In hedging mode, specifying the position ticket is required to
            # close the specific position rather than opening a new short.
            if is_hedging and pos_ticket:
                close_request["position"] = pos_ticket
                print(f"[exec-smoke] Hedging mode: closing position ticket={pos_ticket}")

            try:
                close_result_raw = mt5.order_send(close_request)
                close_result = _as_dict(close_result_raw)
                print(f"[exec-smoke] order_send CLOSE result: {close_result}")
                close_retcode = close_result.get("retcode", -1)
                close_attempted = True
                if close_retcode not in (10008, 10009, 10010):
                    print(
                        f"[exec-smoke] WARNING: CLOSE order retcode={close_retcode} "
                        f"({close_result.get('comment')}). "
                        "MANUAL ACTION REQUIRED: verify and close position in MT5 terminal."
                    )
            except Exception as exc:
                print(
                    f"[exec-smoke] WARNING: close order_send raised: {exc}. "
                    "MANUAL ACTION REQUIRED: close the open position in the MT5 terminal."
                )
    else:
        print(
            "[exec-smoke] No open position found after BUY. "
            "Position may have been closed automatically (e.g. stop-out or netting account)."
        )

    # ------------------------------------------------------------------
    # Step 6: Final position state
    # ------------------------------------------------------------------
    time.sleep(1)
    try:
        final_positions_raw = mt5.positions_get(symbol=symbol)
        final_positions = _as_list(final_positions_raw)
    except Exception:
        final_positions = []

    print(f"[exec-smoke] Final open positions for {symbol}: {len(final_positions)}")
    if final_positions:
        for pos in final_positions:
            print(
                f"  ticket={pos.get('ticket')} volume={pos.get('volume')} "
                f"price_open={pos.get('price_open')} profit={pos.get('profit')}"
            )
        if not close_attempted:
            print(
                "[exec-smoke] MANUAL ACTION REQUIRED: "
                f"There are still {len(final_positions)} open position(s) for {symbol}. "
                "Close them in the MT5 terminal to avoid unintended exposure."
            )

    # ------------------------------------------------------------------
    # Assertions on the smoke result
    # ------------------------------------------------------------------
    assert buy_retcode in (10008, 10009, 10010), (
        f"BUY order was not accepted. retcode={buy_retcode}"
    )
    # History (orders/deals) may not be immediately visible on all brokers
    # (eventual consistency). Log a diagnostic but do not fail the smoke.
    if len(history_deals) == 0 and len(history_orders) == 0:
        print(
            "[exec-smoke] NOTE: history_deals and history_orders returned 0 results. "
            "This is expected on some brokers immediately after a fill. "
            "Re-run the data smoke or wait a few seconds and query manually."
        )
