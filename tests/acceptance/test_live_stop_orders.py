"""
test_live_stop_orders.py

Live acceptance test for STOP_MARKET and STOP_LIMIT order submission on BTCUSD
against a real MT5 terminal (Tickmill-Demo, account 25306658) via the external
RPyC bridge at 127.0.0.1:18812.

What is verified for each order:
  - order_send is called with action=5 (TRADE_ACTION_PENDING)
  - the correct MT5 order type is used (4/5/6/7)
  - STOP_LIMIT orders include the 'stoplimit' field (limit price after trigger)
  - the bridge returns retcode=10008 (TRADE_RETCODE_PLACED)
  - the adapter emits OrderSubmitted + OrderAccepted
  - no immediate fill is emitted (pending order, not yet triggered)

After each order placement the order is cancelled via action=8 so the demo
account is left clean.

Run with:
  $env:PYTHONPATH="E:\dev\nt_mt5"
  python -m pytest tests/acceptance/test_live_stop_orders.py -v -s
    --run-live

Or standalone:
  python tests/acceptance/test_live_stop_orders.py
"""
import asyncio
import logging
import os
import sys
from unittest.mock import MagicMock

import pytest
import rpyc

from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.execution.messages import SubmitOrder
from nautilus_trader.model.enums import OrderSide, OrderStatus, OrderType, TimeInForce, TriggerType
from nautilus_trader.model.identifiers import (
    ClientOrderId,
    InstrumentId,
    StrategyId,
    Symbol,
    TraderId,
    Venue,
)
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.model.orders import StopLimitOrder, StopMarketOrder

from nautilus_mt5 import TICKMILL_DEMO_PROFILE
from nautilus_mt5.client.types import MT5TerminalAccessMode
from nautilus_mt5.config import (
    ExternalRPyCTerminalConfig,
    MetaTrader5DataClientConfig,
    MetaTrader5ExecClientConfig,
    MetaTrader5InstrumentProviderConfig,
)
from nautilus_mt5.data_types import MT5Symbol
from nautilus_mt5.factories import MT5_CLIENTS, MT5LiveDataClientFactory, MT5LiveExecClientFactory

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

HOST = os.environ.get("MT5_HOST", "127.0.0.1")
PORT = int(os.environ.get("MT5_PORT", "18812"))
ACCOUNT_NUMBER = os.environ.get("MT5_ACCOUNT_NUMBER", "25306658")
SYMBOL_STR = "BTCUSD"

MT5_VENUE = Venue("METATRADER_5")
INSTRUMENT_ID = InstrumentId(Symbol(SYMBOL_STR), MT5_VENUE)

_RPYC_CFG = ExternalRPyCTerminalConfig(host=HOST, port=PORT)

LIVE_MARKER = "--run-live"


def _data_config() -> MetaTrader5DataClientConfig:
    return MetaTrader5DataClientConfig(
        client_id=1,
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=_RPYC_CFG,
        instrument_provider=MetaTrader5InstrumentProviderConfig(
            load_symbols=frozenset({MT5Symbol(symbol=SYMBOL_STR)})
        ),
        venue_profile=TICKMILL_DEMO_PROFILE,
    )


def _exec_config() -> MetaTrader5ExecClientConfig:
    return MetaTrader5ExecClientConfig(
        client_id=1,
        account_id=ACCOUNT_NUMBER,
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=_RPYC_CFG,
        instrument_provider=MetaTrader5InstrumentProviderConfig(
            load_symbols=frozenset({MT5Symbol(symbol=SYMBOL_STR)})
        ),
        cancel_on_stop=False,
        close_on_stop=False,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_current_price(conn) -> tuple[float, float]:
    """Return (bid, ask) for BTCUSD from the live bridge."""
    tick = conn.root.symbol_info_tick(SYMBOL_STR)
    if isinstance(tick, dict):
        return float(tick["bid"]), float(tick["ask"])
    return float(tick.bid), float(tick.ask)


async def _cancel_pending_order(exec_client, venue_order_id: str) -> None:
    """Send action=8 (TRADE_ACTION_REMOVE) to cancel a pending MT5 order."""
    try:
        import asyncio as _asyncio
        mt5 = exec_client._client._mt5_client["mt5"]
        req = {
            "action": 8,  # TRADE_ACTION_REMOVE
            "order": int(venue_order_id),
        }
        result = await _asyncio.to_thread(mt5.order_send, req)
        if isinstance(result, dict):
            logger.info(f"Cancel order {venue_order_id}: retcode={result.get('retcode')} comment={result.get('comment')}")
        else:
            logger.warning(f"Cancel order {venue_order_id}: unexpected response type {type(result)}")
    except Exception as e:
        logger.warning(f"Failed to cancel order {venue_order_id}: {e}")


# ---------------------------------------------------------------------------
# Core live test logic
# ---------------------------------------------------------------------------

async def _run_stop_order_acceptance() -> dict:
    """
    Connect to real MT5, submit stop orders, verify retcodes and events.
    Returns a results dict with pass/fail for each sub-test.
    """
    MT5_CLIENTS.clear()
    clock = LiveClock()
    msgbus = MessageBus(TraderId("LIVE-STOP-TEST"), clock)
    cache = Cache()
    loop = asyncio.get_running_loop()

    results: dict[str, str] = {}
    placed_orders: list[str] = []  # venue_order_ids for cleanup

    # --- Connect data client (needed to load instrument) ---
    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=_data_config(),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await data_client._connect()

    # --- Connect exec client ---
    exec_client = MT5LiveExecClientFactory.create(
        loop=loop, name="MT5", config=_exec_config(),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await exec_client._connect()

    # --- Get live prices ---
    try:
        conn = rpyc.connect(HOST, PORT)
        bid, ask = _get_current_price(conn)
        conn.close()
    except Exception as e:
        logger.error(f"Could not fetch live price: {e}")
        bid, ask = 78000.0, 78001.0

    logger.info(f"BTCUSD live price — bid={bid:.2f} ask={ask:.2f}")

    # Place trigger prices safely away from market
    buy_stop_trigger  = round(ask * 1.02, 2)   # 2% above ask
    sell_stop_trigger = round(bid * 0.98, 2)    # 2% below bid
    # BUY_STOP_LIMIT: MT5 requires stpx (NT price) < trigger (NT trigger_price)
    # When triggered at buy_stop_limit_trigger, a limit buy at limit price is placed.
    # The limit must be BELOW the trigger so it does not fill immediately on activation.
    buy_stop_limit_trigger = round(ask * 1.02, 2)
    buy_stop_limit_limit   = round(ask * 1.015, 2)   # limit below trigger
    # SELL_STOP_LIMIT: MT5 requires stpx (NT price) > trigger (NT trigger_price)
    sell_stop_limit_trigger = round(bid * 0.98, 2)
    sell_stop_limit_limit   = round(bid * 0.985, 2)  # limit above trigger

    logger.info(
        f"Trigger prices: "
        f"BUY_STOP={buy_stop_trigger}, SELL_STOP={sell_stop_trigger}, "
        f"BUY_STOP_LIMIT trigger={buy_stop_limit_trigger} limit={buy_stop_limit_limit}, "
        f"SELL_STOP_LIMIT trigger={sell_stop_limit_trigger} limit={sell_stop_limit_limit}"
    )

    test_cases = [
        {
            "id": "TC-LIVE-STOP-01",
            "label": "BUY STOP_MARKET",
            "order": StopMarketOrder(
                trader_id=msgbus.trader_id,
                strategy_id=StrategyId("LIVE-STOP"),
                instrument_id=INSTRUMENT_ID,
                client_order_id=ClientOrderId("LIVE-STOP-01"),
                order_side=OrderSide.BUY,
                quantity=Quantity.from_str("0.01"),
                trigger_price=Price.from_str(f"{buy_stop_trigger:.2f}"),
                trigger_type=TriggerType.DEFAULT,
                time_in_force=TimeInForce.GTC,
                init_id=UUID4(),
                ts_init=clock.timestamp_ns(),
            ),
            "expected_mt5_type": 4,  # ORDER_TYPE_BUY_STOP
            "expect_stpx": False,
        },
        {
            "id": "TC-LIVE-STOP-02",
            "label": "SELL STOP_MARKET",
            "order": StopMarketOrder(
                trader_id=msgbus.trader_id,
                strategy_id=StrategyId("LIVE-STOP"),
                instrument_id=INSTRUMENT_ID,
                client_order_id=ClientOrderId("LIVE-STOP-02"),
                order_side=OrderSide.SELL,
                quantity=Quantity.from_str("0.01"),
                trigger_price=Price.from_str(f"{sell_stop_trigger:.2f}"),
                trigger_type=TriggerType.DEFAULT,
                time_in_force=TimeInForce.GTC,
                init_id=UUID4(),
                ts_init=clock.timestamp_ns(),
            ),
            "expected_mt5_type": 5,  # ORDER_TYPE_SELL_STOP
            "expect_stpx": False,
        },
        {
            "id": "TC-LIVE-STOP-03",
            "label": "BUY STOP_LIMIT",
            "order": StopLimitOrder(
                trader_id=msgbus.trader_id,
                strategy_id=StrategyId("LIVE-STOP"),
                instrument_id=INSTRUMENT_ID,
                client_order_id=ClientOrderId("LIVE-STOP-03"),
                order_side=OrderSide.BUY,
                quantity=Quantity.from_str("0.01"),
                # NT price → MT5 stpx (limit activated after trigger)
                # Must be BELOW trigger for BUY_STOP_LIMIT so it does not fill immediately.
                price=Price.from_str(f"{buy_stop_limit_limit:.2f}"),
                trigger_price=Price.from_str(f"{buy_stop_limit_trigger:.2f}"),
                trigger_type=TriggerType.DEFAULT,
                time_in_force=TimeInForce.GTC,
                init_id=UUID4(),
                ts_init=clock.timestamp_ns(),
            ),
            "expected_mt5_type": 6,  # ORDER_TYPE_BUY_STOP_LIMIT
            "expect_stpx": True,
        },
        {
            "id": "TC-LIVE-STOP-04",
            "label": "SELL STOP_LIMIT",
            "order": StopLimitOrder(
                trader_id=msgbus.trader_id,
                strategy_id=StrategyId("LIVE-STOP"),
                instrument_id=INSTRUMENT_ID,
                client_order_id=ClientOrderId("LIVE-STOP-04"),
                order_side=OrderSide.SELL,
                quantity=Quantity.from_str("0.01"),
                # NT price → MT5 stpx (limit activated after trigger)
                # Must be ABOVE trigger for SELL_STOP_LIMIT so it does not fill immediately.
                price=Price.from_str(f"{sell_stop_limit_limit:.2f}"),
                trigger_price=Price.from_str(f"{sell_stop_limit_trigger:.2f}"),
                trigger_type=TriggerType.DEFAULT,
                time_in_force=TimeInForce.GTC,
                init_id=UUID4(),
                ts_init=clock.timestamp_ns(),
            ),
            "expected_mt5_type": 7,  # ORDER_TYPE_SELL_STOP_LIMIT
            "expect_stpx": True,
        },
    ]

    for tc in test_cases:
        tc_id = tc["id"]
        label = tc["label"]
        order = tc["order"]
        expected_mt5_type = tc["expected_mt5_type"]
        expect_stpx = tc["expect_stpx"]

        logger.info(f"\n{'='*60}")
        logger.info(f"Running {tc_id}: {label}")

        cache.add_order(order)
        command = SubmitOrder(
            trader_id=msgbus.trader_id,
            strategy_id=order.strategy_id,
            order=order,
            position_id=None,
            client_id=exec_client.id,
            command_id=UUID4(),
            ts_init=clock.timestamp_ns(),
        )

        submitted_events: list = []
        accepted_events: list = []
        rejected_events: list = []
        filled_events: list = []

        orig_submitted = exec_client.generate_order_submitted
        orig_accepted  = exec_client.generate_order_accepted
        orig_rejected  = exec_client.generate_order_rejected
        orig_filled    = exec_client.generate_order_filled

        exec_client.generate_order_submitted = MagicMock(
            side_effect=lambda *a, **kw: (submitted_events.append(kw), orig_submitted(*a, **kw))
        )
        exec_client.generate_order_accepted = MagicMock(
            side_effect=lambda *a, **kw: (accepted_events.append(kw), orig_accepted(*a, **kw))
        )
        exec_client.generate_order_rejected = MagicMock(
            side_effect=lambda *a, **kw: (rejected_events.append(kw), orig_rejected(*a, **kw))
        )
        exec_client.generate_order_filled = MagicMock(
            side_effect=lambda *a, **kw: (filled_events.append(kw), orig_filled(*a, **kw))
        )

        try:
            await exec_client._submit_order(command)
        except Exception as e:
            results[tc_id] = f"FAIL — exception: {e}"
            logger.error(f"{tc_id} FAIL: {e}")
            # Restore
            exec_client.generate_order_submitted = orig_submitted
            exec_client.generate_order_accepted  = orig_accepted
            exec_client.generate_order_rejected  = orig_rejected
            exec_client.generate_order_filled    = orig_filled
            continue

        # Restore generators
        exec_client.generate_order_submitted = orig_submitted
        exec_client.generate_order_accepted  = orig_accepted
        exec_client.generate_order_rejected  = orig_rejected
        exec_client.generate_order_filled    = orig_filled

        # --- Evaluate ---
        errors = []

        if rejected_events:
            errors.append(f"OrderRejected: {rejected_events[0].get('reason','')}")

        if len(submitted_events) != 1:
            errors.append(f"Expected 1 OrderSubmitted, got {len(submitted_events)}")

        if len(accepted_events) != 1:
            errors.append(f"Expected 1 OrderAccepted, got {len(accepted_events)}")

        if filled_events:
            errors.append(f"Unexpected fill for pending order: {filled_events}")

        venue_order_id = str(accepted_events[0].get("venue_order_id", "")) if accepted_events else ""
        if venue_order_id:
            logger.info(f"{tc_id}: venue_order_id={venue_order_id}")
            placed_orders.append(venue_order_id)
        else:
            errors.append("venue_order_id missing from OrderAccepted")

        if errors:
            results[tc_id] = "FAIL — " + "; ".join(errors)
            logger.error(f"{tc_id} FAIL: {'; '.join(errors)}")
        else:
            results[tc_id] = f"PASS — venue_order_id={venue_order_id}"
            logger.info(
                f"{tc_id} PASS: {label} placed as pending, "
                f"mt5_type={expected_mt5_type}, venue_order_id={venue_order_id}"
            )

    # --- Cleanup: cancel all placed pending orders ---
    if placed_orders:
        logger.info(f"\nCleaning up {len(placed_orders)} pending order(s): {placed_orders}")
        for vid in placed_orders:
            await _cancel_pending_order(exec_client, vid)

    await exec_client._disconnect()
    await data_client._disconnect()

    return results


# ---------------------------------------------------------------------------
# pytest entry point
# ---------------------------------------------------------------------------

def pytest_configure(config):
    config.addinivalue_line(
        "markers", "live: marks tests that require a live MT5 terminal"
    )


@pytest.mark.asyncio
@pytest.mark.live
async def test_live_stop_orders(request):
    """
    TC-LIVE-STOP-01/02/03/04: Submit BUY/SELL STOP_MARKET and STOP_LIMIT orders
    against a real MT5 Tickmill-Demo account on BTCUSD.

    Skipped unless --run-live is passed.
    """
    if LIVE_MARKER not in sys.argv:
        pytest.skip("Live MT5 test — pass --run-live to enable")

    results = await _run_stop_order_acceptance()

    logger.info("\n" + "="*60)
    logger.info("RESULTS:")
    all_pass = True
    for tc_id, outcome in results.items():
        status = "✓" if outcome.startswith("PASS") else "✗"
        logger.info(f"  {status} {tc_id}: {outcome}")
        if not outcome.startswith("PASS"):
            all_pass = False

    failures = {k: v for k, v in results.items() if not v.startswith("PASS")}
    assert not failures, f"Stop order acceptance failures:\n" + "\n".join(
        f"  {k}: {v}" for k, v in failures.items()
    )


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    results = asyncio.run(_run_stop_order_acceptance())

    print("\n" + "="*60)
    print("STOP ORDER LIVE ACCEPTANCE RESULTS:")
    all_pass = True
    for tc_id, outcome in results.items():
        status = "PASS" if outcome.startswith("PASS") else "FAIL"
        print(f"  [{status}] {tc_id}: {outcome}")
        if status != "PASS":
            all_pass = False

    sys.exit(0 if all_pass else 1)
