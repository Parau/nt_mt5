"""
test_execution_order_commands_external_rpyc.py

Deterministic Nautilus-level tests for order management commands and
generate_order_status_reports in the MT5 adapter (EXTERNAL_RPYC mode).

Tests:
    TC-EL-08  generate_order_status_reports → infers reports from open positions
    TC-EL-09  generate_order_status_report (singular) → returns None when not in open orders
    TC-EL-10  _cancel_order → calls order_send with action=8 (TRADE_ACTION_REMOVE)
    TC-EL-11  _modify_order → calls place_order with updated volume
    TC-EL-12  _cancel_all_orders → cancels each open order in the Nautilus cache
"""
import asyncio
from unittest.mock import MagicMock, patch

import pytest

from nautilus_trader.core.uuid import UUID4
from nautilus_trader.execution.messages import (
    CancelAllOrders,
    CancelOrder,
    GenerateOrderStatusReport,
    GenerateOrderStatusReports,
    ModifyOrder,
)
from nautilus_trader.execution.reports import OrderStatusReport
from nautilus_trader.model.enums import OrderSide, OrderStatus, OrderType, TimeInForce
from nautilus_trader.model.events import OrderAccepted, OrderInitialized, OrderSubmitted
from nautilus_trader.model.identifiers import (
    AccountId,
    ClientOrderId,
    InstrumentId,
    StrategyId,
    Symbol,
    Venue,
    VenueOrderId,
)
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.model.orders import LimitOrder, MarketOrder

from nautilus_mt5.client.types import MT5TerminalAccessMode
from nautilus_mt5.config import (
    ExternalRPyCTerminalConfig,
    MetaTrader5DataClientConfig,
    MetaTrader5ExecClientConfig,
    MetaTrader5InstrumentProviderConfig,
)
from nautilus_mt5.data_types import MT5Symbol
from nautilus_mt5.factories import MT5LiveDataClientFactory, MT5LiveExecClientFactory
from nautilus_mt5 import TICKMILL_DEMO_PROFILE

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RPYC_CONFIG = ExternalRPyCTerminalConfig(host="127.0.0.1", port=18812)
_VENUE = Venue("METATRADER_5")
_USTEC_ID = InstrumentId(Symbol("USTEC"), _VENUE)


def _data_config(*symbols: str) -> MetaTrader5DataClientConfig:
    load = frozenset(MT5Symbol(symbol=s) for s in symbols) if symbols else None
    return MetaTrader5DataClientConfig(
        client_id=1,
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=_RPYC_CONFIG,
        instrument_provider=MetaTrader5InstrumentProviderConfig(load_symbols=load),
        venue_profile=TICKMILL_DEMO_PROFILE,
    )


def _exec_config(*symbols: str) -> MetaTrader5ExecClientConfig:
    load = frozenset(MT5Symbol(symbol=s) for s in symbols) if symbols else None
    return MetaTrader5ExecClientConfig(
        client_id=1,
        account_id="123456",
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=_RPYC_CONFIG,
        instrument_provider=MetaTrader5InstrumentProviderConfig(load_symbols=load),
    )


def _make_limit_order(msgbus, clock, strategy_id: str, client_order_id: str, price: float = 18000.0) -> LimitOrder:
    return LimitOrder(
        trader_id=msgbus.trader_id,
        strategy_id=StrategyId(strategy_id),
        instrument_id=_USTEC_ID,
        client_order_id=ClientOrderId(client_order_id),
        order_side=OrderSide.BUY,
        quantity=Quantity.from_str("1"),
        price=Price.from_str(str(price)),
        time_in_force=TimeInForce.GTC,
        init_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )


def _accept_order(order, account_id: AccountId, venue_order_id: str, clock, cache=None) -> None:
    """Apply OrderSubmitted + OrderAccepted events so the order has venue_order_id set.

    Pass ``cache`` to also update the cache's open-order index (required for
    ``cache.orders_open()`` to return the order).
    """
    ts = clock.timestamp_ns()
    submitted = OrderSubmitted(
        trader_id=order.trader_id,
        strategy_id=order.strategy_id,
        instrument_id=order.instrument_id,
        client_order_id=order.client_order_id,
        account_id=account_id,
        event_id=UUID4(),
        ts_event=ts,
        ts_init=ts,
    )
    order.apply(submitted)
    if cache is not None:
        cache.update_order(order)
    accepted = OrderAccepted(
        trader_id=order.trader_id,
        strategy_id=order.strategy_id,
        instrument_id=order.instrument_id,
        client_order_id=order.client_order_id,
        venue_order_id=VenueOrderId(venue_order_id),
        account_id=account_id,
        event_id=UUID4(),
        ts_event=ts,
        ts_init=ts,
    )
    order.apply(accepted)
    if cache is not None:
        cache.update_order(order)


# ---------------------------------------------------------------------------
# TC-EL-08  generate_order_status_reports (plural) → reports from positions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_order_status_reports_from_positions(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    generate_order_status_reports builds OrderStatusReports from open positions
    when the USTEC instrument is loaded in the cache.
    """
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=_data_config("USTEC"),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await data_client._connect()

    exec_client = MT5LiveExecClientFactory.create(
        loop=loop, name="MT5", config=_exec_config("USTEC"),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await exec_client._connect()

    command = GenerateOrderStatusReports(
        instrument_id=None,
        start=None,
        end=None,
        open_only=False,
        command_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )

    reports = await exec_client.generate_order_status_reports(command)

    assert len(reports) >= 1, "Expected at least one OrderStatusReport from open USTEC position"
    ustec_reports = [r for r in reports if r.instrument_id == _USTEC_ID]
    assert len(ustec_reports) == 1

    r = ustec_reports[0]
    assert isinstance(r, OrderStatusReport)
    assert r.account_id == exec_client.account_id
    assert r.order_status == OrderStatus.FILLED
    assert float(r.quantity) == pytest.approx(0.1)


# ---------------------------------------------------------------------------
# TC-EL-09  generate_order_status_report (singular) → None when not found
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_order_status_report_singular_not_found(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    generate_order_status_report (singular) returns None when the venue_order_id
    is not found in open orders (exposed_orders_get returns []).
    """
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=_data_config("USTEC"),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await data_client._connect()

    exec_client = MT5LiveExecClientFactory.create(
        loop=loop, name="MT5", config=_exec_config("USTEC"),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await exec_client._connect()

    # Add a limit order to cache so _on_order_status can look it up
    order = _make_limit_order(msgbus, clock, "S-EL-09", "O-EL-09")
    cache.add_order(order)

    command = GenerateOrderStatusReport(
        instrument_id=_USTEC_ID,
        client_order_id=ClientOrderId("O-EL-09"),
        venue_order_id=VenueOrderId("9999"),
        command_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )

    # Silence the internal _on_order_status warning path for this test
    exec_client._on_order_status = MagicMock()

    report = await exec_client.generate_order_status_report(command)

    assert report is None, "Expected None when order is not in open orders"
    exec_client._on_order_status.assert_called_once()


# ---------------------------------------------------------------------------
# TC-EL-10  _cancel_order → order_send called with action=8
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cancel_order_sends_action_8(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    _cancel_order calls order_send with action=8 (TRADE_ACTION_REMOVE) and
    the correct order ticket.
    """
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    exec_client = MT5LiveExecClientFactory.create(
        loop=loop, name="MT5", config=_exec_config(),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await exec_client._connect()

    nautilus_mt5_harness.root.reset_calls()

    command = CancelOrder(
        trader_id=msgbus.trader_id,
        strategy_id=StrategyId("S-EL-10"),
        instrument_id=_USTEC_ID,
        client_order_id=ClientOrderId("O-EL-10"),
        venue_order_id=VenueOrderId("1001"),
        command_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )

    await exec_client._cancel_order(command)

    order_send_calls = [c for c in nautilus_mt5_harness.root.calls if c.method == "order_send"]
    assert len(order_send_calls) == 1, "Expected exactly one order_send call for cancel"
    sent_req = order_send_calls[0].args[0]
    assert sent_req["action"] == 8, "Expected action=8 (TRADE_ACTION_REMOVE)"
    assert sent_req["order"] == 1001, "Expected order ticket 1001"


# ---------------------------------------------------------------------------
# TC-EL-11  _modify_order → place_order called with updated volume
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_modify_order_calls_place_order(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    _modify_order calls place_order (→ order_send) with updated volume after
    a limit order is found in the Nautilus cache.
    """
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=_data_config("USTEC"),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await data_client._connect()

    exec_client = MT5LiveExecClientFactory.create(
        loop=loop, name="MT5", config=_exec_config("USTEC"),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await exec_client._connect()

    # Create a limit order and accept it (venue_order_id=1001)
    order = _make_limit_order(msgbus, clock, "S-EL-11", "O-EL-11", price=18000.0)
    cache.add_order(order)
    _accept_order(order, exec_client.account_id, "1001", clock, cache)

    nautilus_mt5_harness.root.reset_calls()

    command = ModifyOrder(
        trader_id=msgbus.trader_id,
        strategy_id=StrategyId("S-EL-11"),
        instrument_id=_USTEC_ID,
        client_order_id=ClientOrderId("O-EL-11"),
        venue_order_id=VenueOrderId("1001"),
        quantity=Quantity.from_str("2"),   # updated quantity
        price=None,
        trigger_price=None,
        command_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )

    await exec_client._modify_order(command)

    order_send_calls = [c for c in nautilus_mt5_harness.root.calls if c.method == "order_send"]
    assert len(order_send_calls) >= 1, "Expected order_send called during modify"
    sent_req = order_send_calls[0].args[0]
    # Modify uses place_order which sends a full order request
    assert sent_req.get("symbol") == "USTEC"
    assert float(sent_req.get("volume", 0)) == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# TC-EL-12  _cancel_all_orders → cancel_order called for each open order in cache
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cancel_all_orders_cancels_each_open_order(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    _cancel_all_orders iterates open orders from the Nautilus cache and calls
    cancel_order (→ order_send) for each one with action=8.
    """
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=_data_config("USTEC"),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await data_client._connect()

    exec_client = MT5LiveExecClientFactory.create(
        loop=loop, name="MT5", config=_exec_config("USTEC"),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await exec_client._connect()

    # Add two limit orders to the Nautilus cache in ACCEPTED state
    order_a = _make_limit_order(msgbus, clock, "S-EL-12", "O-EL-12A", price=17900.0)
    order_b = _make_limit_order(msgbus, clock, "S-EL-12", "O-EL-12B", price=17800.0)
    cache.add_order(order_a)
    cache.add_order(order_b)
    _accept_order(order_a, exec_client.account_id, "2001", clock, cache)
    _accept_order(order_b, exec_client.account_id, "2002", clock, cache)

    nautilus_mt5_harness.root.reset_calls()

    command = CancelAllOrders(
        trader_id=msgbus.trader_id,
        strategy_id=StrategyId("S-EL-12"),
        instrument_id=_USTEC_ID,
        order_side=OrderSide.NO_ORDER_SIDE,
        command_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )

    await exec_client._cancel_all_orders(command)

    order_send_calls = [c for c in nautilus_mt5_harness.root.calls if c.method == "order_send"]
    assert len(order_send_calls) == 2, (
        f"Expected 2 cancel order_send calls, got {len(order_send_calls)}"
    )
    for call in order_send_calls:
        req = call.args[0]
        assert req["action"] == 8, "All cancel requests must use action=8"
    cancelled_tickets = {call.args[0]["order"] for call in order_send_calls}
    assert cancelled_tickets == {2001, 2002}, f"Expected tickets 2001, 2002; got {cancelled_tickets}"
