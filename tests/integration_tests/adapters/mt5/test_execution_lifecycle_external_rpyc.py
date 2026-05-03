"""
test_execution_lifecycle_external_rpyc.py

Deterministic Nautilus-level execution lifecycle tests for the MT5 adapter in
EXTERNAL_RPYC mode.  No real MT5 terminal, no live env vars.

Lifecycle covered:
    1. Connect execution client → account validated against fake bridge.
    2. Submit USTEC market order → order_send called, OrderSubmitted generated.
    3. Retcode 10009 (DONE) → OrderAccepted generated with venue_order_id.
    4. generate_fill_reports → FillReport built from history_deals_get payload.
    5. generate_position_status_reports → PositionStatusReport for USTEC.
    6. generate_order_status_reports → OrderStatusReport inferred from positions.
    7. Error retcode from fake bridge → OrderRejected generated.
"""
import asyncio
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from nautilus_trader.core.uuid import UUID4
from nautilus_trader.execution.messages import (
    GenerateFillReports,
    GenerateOrderStatusReports,
    GeneratePositionStatusReports,
    SubmitOrder,
)
from nautilus_trader.execution.reports import FillReport, OrderStatusReport, PositionStatusReport
from nautilus_trader.model.enums import LiquiditySide, OrderSide, OrderStatus, OrderType, TimeInForce
from nautilus_trader.model.identifiers import (
    ClientOrderId,
    InstrumentId,
    StrategyId,
    Symbol,
    Venue,
    VenueOrderId,
)
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.model.events import OrderAccepted, OrderSubmitted
from nautilus_trader.model.identifiers import AccountId
from nautilus_trader.model.orders import LimitOrder, MarketOrder, StopMarketOrder, StopLimitOrder
from nautilus_trader.model.enums import TriggerType
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
_BTCUSD_ID = InstrumentId(Symbol("BTCUSD"), _VENUE)


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


def _make_market_order(msgbus, clock, strategy_id: str, client_order_id: str) -> MarketOrder:
    return MarketOrder(
        trader_id=msgbus.trader_id,
        strategy_id=StrategyId(strategy_id),
        instrument_id=_USTEC_ID,
        client_order_id=ClientOrderId(client_order_id),
        order_side=OrderSide.BUY,
        quantity=Quantity.from_str("1"),
        time_in_force=TimeInForce.GTC,
        init_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )


def _make_submit_command(msgbus, clock, exec_client, order: MarketOrder) -> SubmitOrder:
    return SubmitOrder(
        trader_id=msgbus.trader_id,
        strategy_id=order.strategy_id,
        order=order,
        position_id=None,
        client_id=exec_client.id,
        command_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )


# ---------------------------------------------------------------------------
# TC-EL-01  Connect exec client → account validated
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_lifecycle_connect_validates_account(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    _connect() validates config.account_id against fake bridge login (123456).
    """
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    exec_client = MT5LiveExecClientFactory.create(
        loop=loop, name="MT5", config=_exec_config(),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    exec_client._set_connected = MagicMock(wraps=exec_client._set_connected)
    await exec_client._connect()

    exec_client._set_connected.assert_called_once_with(True)


# ---------------------------------------------------------------------------
# TC-EL-02  Submit USTEC market order → order_send called
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_lifecycle_submit_order_calls_order_send(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    _submit_order() places a USTEC market order and calls order_send on the bridge.
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

    nautilus_mt5_harness.root.reset_calls()

    order = _make_market_order(msgbus, clock, "S-EL-02", "O-EL-02")
    command = _make_submit_command(msgbus, clock, exec_client, order)

    await exec_client._submit_order(command)

    order_send_calls = [c for c in nautilus_mt5_harness.root.calls if c.method == "order_send"]
    assert len(order_send_calls) == 1
    sent_req = order_send_calls[0].args[0]
    assert sent_req["symbol"] == "USTEC"
    assert sent_req["action"] == 1   # TRADE_ACTION_DEAL


# ---------------------------------------------------------------------------
# TC-EL-03  Submit USTEC market order → OrderSubmitted + OrderAccepted events
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_lifecycle_submit_order_generates_submitted_and_accepted(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    _submit_order() generates OrderSubmitted then OrderAccepted when retcode=10009.
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

    exec_client.generate_order_submitted = MagicMock()
    exec_client.generate_order_accepted = MagicMock()

    order = _make_market_order(msgbus, clock, "S-EL-03", "O-EL-03")
    command = _make_submit_command(msgbus, clock, exec_client, order)

    await exec_client._submit_order(command)

    assert exec_client.generate_order_submitted.called, "OrderSubmitted not generated"
    assert exec_client.generate_order_accepted.called, (
        "OrderAccepted not generated — retcode 10009 should trigger ACCEPTED"
    )
    # VenueOrderId should be 1001 (from USTEC fake bridge response)
    call_kwargs = exec_client.generate_order_accepted.call_args.kwargs
    assert call_kwargs.get("venue_order_id") == VenueOrderId("1001")


# ---------------------------------------------------------------------------
# TC-EL-04  generate_fill_reports → FillReport from USTEC deal
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_lifecycle_generate_fill_reports_ustec(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    generate_fill_reports returns a FillReport for the USTEC deal from history_deals_get.
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

    command = GenerateFillReports(
        instrument_id=_USTEC_ID,
        venue_order_id=None,
        start=None,
        end=None,
        command_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )

    reports = await exec_client.generate_fill_reports(command)

    assert len(reports) >= 1, "Expected at least one FillReport for USTEC"
    ustec_reports = [r for r in reports if r.instrument_id == _USTEC_ID]
    assert len(ustec_reports) == 1

    r = ustec_reports[0]
    assert isinstance(r, FillReport)
    assert r.account_id == exec_client.account_id
    assert r.instrument_id == _USTEC_ID
    assert r.venue_order_id == VenueOrderId("1001")
    assert r.trade_id.value == "101"
    assert r.order_side == OrderSide.BUY
    assert float(r.last_qty) == pytest.approx(0.1)
    assert float(r.last_px) == pytest.approx(18500.50)
    assert r.commission.as_double() == pytest.approx(0.50)   # absolute value
    assert r.liquidity_side == LiquiditySide.TAKER


# ---------------------------------------------------------------------------
# TC-EL-05  generate_fill_reports without instrument_id filter → all deals
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_lifecycle_generate_fill_reports_all_symbols(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    generate_fill_reports without instrument_id filter returns FillReports
    for all symbols whose instruments are loaded in the cache.
    """
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    # Load both USTEC and EURUSD
    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=_data_config("USTEC", "EURUSD"),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await data_client._connect()

    exec_client = MT5LiveExecClientFactory.create(
        loop=loop, name="MT5", config=_exec_config("USTEC", "EURUSD"),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await exec_client._connect()

    command = GenerateFillReports(
        instrument_id=None,
        venue_order_id=None,
        start=None,
        end=None,
        command_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )

    reports = await exec_client.generate_fill_reports(command)

    assert len(reports) == 2, f"Expected 2 FillReports, got {len(reports)}"
    instrument_ids = {r.instrument_id for r in reports}
    assert _USTEC_ID in instrument_ids


# ---------------------------------------------------------------------------
# TC-EL-06  generate_position_status_reports → PositionStatusReport for USTEC
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_lifecycle_generate_position_status_reports(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    generate_position_status_reports returns a PositionStatusReport for USTEC.
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

    command = GeneratePositionStatusReports(
        instrument_id=_USTEC_ID,
        start=None,
        end=None,
        command_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )

    reports = await exec_client.generate_position_status_reports(command)

    assert len(reports) >= 1, "Expected at least one PositionStatusReport for USTEC"
    ustec_reports = [r for r in reports if r.instrument_id == _USTEC_ID]
    assert len(ustec_reports) == 1

    r = ustec_reports[0]
    assert isinstance(r, PositionStatusReport)
    assert r.account_id == exec_client.account_id
    assert float(r.quantity) == pytest.approx(0.1)


# ---------------------------------------------------------------------------
# TC-EL-07  Error retcode → OrderRejected
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_lifecycle_submit_order_rejected_on_error_retcode(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    When order_send returns an error retcode, _submit_order generates OrderRejected.
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

    # Patch order_send on the bridge to return an error retcode
    original_order_send = nautilus_mt5_harness.root.exposed_order_send
    def error_order_send(request):
        return {"retcode": 10014, "comment": "Invalid volume", "order": 0, "deal": 0}
    nautilus_mt5_harness.root.exposed_order_send = error_order_send

    exec_client.generate_order_submitted = MagicMock()
    exec_client.generate_order_rejected = MagicMock()

    try:
        order = _make_market_order(msgbus, clock, "S-EL-07", "O-EL-07")
        command = _make_submit_command(msgbus, clock, exec_client, order)
        await exec_client._submit_order(command)
    finally:
        nautilus_mt5_harness.root.exposed_order_send = original_order_send

    assert exec_client.generate_order_submitted.called, "OrderSubmitted not generated"
    assert exec_client.generate_order_rejected.called, (
        "OrderRejected not generated for error retcode 10014"
    )
    reject_kwargs = exec_client.generate_order_rejected.call_args.kwargs
    assert "Invalid volume" in reject_kwargs.get("reason", "")


# ---------------------------------------------------------------------------
# TC-EL-13  Unsupported OrderType → pre-venue OrderRejected, no bridge call
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("unsupported_type", [
    OrderType.MARKET_TO_LIMIT,
    OrderType.MARKET_IF_TOUCHED,
    OrderType.LIMIT_IF_TOUCHED,
    OrderType.TRAILING_STOP_MARKET,
    OrderType.TRAILING_STOP_LIMIT,
])
async def test_lifecycle_submit_order_rejected_for_unsupported_order_type(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness, unsupported_type
):
    """
    TC-EL-13: _submit_order() emits OrderRejected for any OrderType that is
    not in the adapter's supported set, without calling order_send on the bridge.
    This is the pre-venue guard required by TC-E72.
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

    # Build a real market order but override its order_type via a mock wrapper.
    real_order = _make_market_order(msgbus, clock, "S-EL-13", f"O-EL-13-{unsupported_type.name}")
    mock_order = MagicMock(wraps=real_order)
    mock_order.order_type = unsupported_type  # override to unsupported type
    mock_order.time_in_force = TimeInForce.GTC
    mock_order.status = real_order.status

    command = MagicMock(spec=SubmitOrder)
    command.order = mock_order

    exec_client.generate_order_submitted = MagicMock()
    exec_client.generate_order_rejected = MagicMock()

    with patch.object(exec_client._client, "place_order") as mock_place_order:
        await exec_client._submit_order(command)
        mock_place_order.assert_not_called()

    assert not exec_client.generate_order_submitted.called, (
        f"OrderSubmitted must not fire for unsupported type {unsupported_type.name}"
    )
    assert exec_client.generate_order_rejected.called, (
        f"OrderRejected not emitted for unsupported OrderType.{unsupported_type.name}"
    )
    reason = exec_client.generate_order_rejected.call_args.kwargs.get("reason", "")
    assert "MT5 adapter does not support OrderType" in reason
    assert unsupported_type.name in reason


# ---------------------------------------------------------------------------
# TC-EL-14  Unsupported TimeInForce → pre-venue OrderRejected, no bridge call
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("unsupported_tif", [
    TimeInForce.GTD,
    TimeInForce.AT_THE_OPEN,
    TimeInForce.AT_THE_CLOSE,
])
async def test_lifecycle_submit_order_rejected_for_unsupported_tif(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness, unsupported_tif
):
    """
    TC-EL-14: _submit_order() emits OrderRejected for any TimeInForce that is
    not in the adapter's supported set, without calling order_send on the bridge.
    This is the pre-venue guard required by TC-E73.
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

    real_order = _make_market_order(msgbus, clock, "S-EL-14", f"O-EL-14-{unsupported_tif.name}")
    mock_order = MagicMock(wraps=real_order)
    mock_order.order_type = OrderType.MARKET  # supported type
    mock_order.time_in_force = unsupported_tif  # override to unsupported TIF
    mock_order.status = real_order.status

    command = MagicMock(spec=SubmitOrder)
    command.order = mock_order

    exec_client.generate_order_submitted = MagicMock()
    exec_client.generate_order_rejected = MagicMock()

    with patch.object(exec_client._client, "place_order") as mock_place_order:
        await exec_client._submit_order(command)
        mock_place_order.assert_not_called()

    assert not exec_client.generate_order_submitted.called, (
        f"OrderSubmitted must not fire for unsupported TIF {unsupported_tif.name}"
    )
    assert exec_client.generate_order_rejected.called, (
        f"OrderRejected not emitted for unsupported TimeInForce.{unsupported_tif.name}"
    )
    reason = exec_client.generate_order_rejected.call_args.kwargs.get("reason", "")
    assert "MT5 adapter does not support TimeInForce" in reason
    assert unsupported_tif.name in reason


# ---------------------------------------------------------------------------
# Helpers shared by TC-EL-15 / TC-EL-16 / TC-EL-17
# ---------------------------------------------------------------------------

def _make_limit_order(msgbus, clock, strategy_id: str, client_order_id: str) -> LimitOrder:
    return LimitOrder(
        trader_id=msgbus.trader_id,
        strategy_id=StrategyId(strategy_id),
        instrument_id=_USTEC_ID,
        client_order_id=ClientOrderId(client_order_id),
        order_side=OrderSide.BUY,
        quantity=Quantity.from_str("1"),
        price=Price.from_str("18000.00"),
        time_in_force=TimeInForce.GTC,
        init_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )


def _accept_order(order, account_id: AccountId, venue_order_id: str, clock, cache=None) -> None:
    """Apply Submitted + Accepted events so the order is open with a venue_order_id."""
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
# TC-EL-15  cancel_on_stop=True → cancel_order called for each open order
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_disconnect_cancel_on_stop_cancels_open_orders(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    TC-EL-15: When cancel_on_stop=True (default), _disconnect() calls cancel_order
    (→ order_send with action=8) for every open order that has a venue_order_id in
    the Nautilus cache.
    """
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    from nautilus_mt5.config import MetaTrader5ExecClientConfig, MetaTrader5InstrumentProviderConfig
    exec_cfg = MetaTrader5ExecClientConfig(
        client_id=1,
        account_id="123456",
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=_RPYC_CONFIG,
        instrument_provider=MetaTrader5InstrumentProviderConfig(),
        cancel_on_stop=True,
        close_on_stop=False,
    )

    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=_data_config("USTEC"),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await data_client._connect()

    exec_client = MT5LiveExecClientFactory.create(
        loop=loop, name="MT5", config=exec_cfg,
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await exec_client._connect()

    # Inject two open limit orders with venue_order_ids into the Nautilus cache.
    for i, vid in enumerate(("2001", "2002"), start=1):
        order = _make_limit_order(msgbus, clock, "S-EL-15", f"O-EL-15-{i}")
        cache.add_order(order)
        _accept_order(order, exec_client.account_id, vid, clock, cache)

    nautilus_mt5_harness.root.reset_calls()

    await exec_client._disconnect()

    cancel_calls = [
        c for c in nautilus_mt5_harness.root.calls
        if c.method == "order_send" and isinstance(c.args[0], dict) and c.args[0].get("action") == 8
    ]
    assert len(cancel_calls) == 2, (
        f"Expected 2 cancel (action=8) calls, got {len(cancel_calls)}: {cancel_calls}"
    )
    cancelled_tickets = {c.args[0]["order"] for c in cancel_calls}
    assert cancelled_tickets == {2001, 2002}


# ---------------------------------------------------------------------------
# TC-EL-16  close_on_stop=True → order_send with position ticket for each position
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_disconnect_close_on_stop_closes_open_positions(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    TC-EL-16: When close_on_stop=True, _disconnect() sends a market SELL order
    (action=1, position=ticket) for each open position returned by positions_get.
    The fake bridge returns 2 positions: USTEC (ticket=1001) and EURUSD (ticket=1).
    """
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    from nautilus_mt5.config import MetaTrader5ExecClientConfig, MetaTrader5InstrumentProviderConfig
    exec_cfg = MetaTrader5ExecClientConfig(
        client_id=1,
        account_id="123456",
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=_RPYC_CONFIG,
        instrument_provider=MetaTrader5InstrumentProviderConfig(),
        cancel_on_stop=False,
        close_on_stop=True,
    )

    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=_data_config("USTEC"),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await data_client._connect()

    exec_client = MT5LiveExecClientFactory.create(
        loop=loop, name="MT5", config=exec_cfg,
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await exec_client._connect()

    nautilus_mt5_harness.root.reset_calls()

    await exec_client._disconnect()

    close_calls = [
        c for c in nautilus_mt5_harness.root.calls
        if c.method == "order_send"
        and isinstance(c.args[0], dict)
        and c.args[0].get("action") == 1  # TRADE_ACTION_DEAL
        and c.args[0].get("position", 0) != 0  # close-position semantics
    ]
    # Fake bridge returns 2 BUY positions (type=0) → 2 SELL close orders (type=1)
    assert len(close_calls) == 2, (
        f"Expected 2 close-position order_send calls, got {len(close_calls)}"
    )
    for call in close_calls:
        req = call.args[0]
        assert req.get("type") == 1, "Expected ORDER_TYPE_SELL (1) to close a BUY position"
        assert req.get("position") in (1001, 1), f"Unexpected position ticket: {req.get('position')}"


# ---------------------------------------------------------------------------
# TC-EL-17  cancel_on_stop=False, close_on_stop=False → no cancel/close calls
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_disconnect_no_cancel_no_close_when_flags_false(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    TC-EL-17: When both cancel_on_stop=False and close_on_stop=False, _disconnect()
    does NOT call order_send for cancel or close — even if open orders exist in cache.
    """
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    from nautilus_mt5.config import MetaTrader5ExecClientConfig, MetaTrader5InstrumentProviderConfig
    exec_cfg = MetaTrader5ExecClientConfig(
        client_id=1,
        account_id="123456",
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=_RPYC_CONFIG,
        instrument_provider=MetaTrader5InstrumentProviderConfig(),
        cancel_on_stop=False,
        close_on_stop=False,
    )

    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=_data_config("USTEC"),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await data_client._connect()

    exec_client = MT5LiveExecClientFactory.create(
        loop=loop, name="MT5", config=exec_cfg,
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await exec_client._connect()

    # Inject an open order — it should NOT be cancelled on disconnect.
    order = _make_limit_order(msgbus, clock, "S-EL-17", "O-EL-17-1")
    cache.add_order(order)
    _accept_order(order, exec_client.account_id, "3001", clock, cache)

    nautilus_mt5_harness.root.reset_calls()

    await exec_client._disconnect()

    # No order_send call should have been made for cancel or close
    order_send_calls = [c for c in nautilus_mt5_harness.root.calls if c.method == "order_send"]
    assert len(order_send_calls) == 0, (
        f"Expected no order_send calls with flags disabled, got: {order_send_calls}"
    )


# ---------------------------------------------------------------------------
# TC-EL-18  GTC BUY LIMIT → order_send with correct MT5 fields + OrderAccepted
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("side,expected_mt5_type", [
    (OrderSide.BUY,  2),  # ORDER_TYPE_BUY_LIMIT
    (OrderSide.SELL, 3),  # ORDER_TYPE_SELL_LIMIT
])
async def test_lifecycle_submit_gtc_limit_order(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness, side, expected_mt5_type
):
    """
    TC-EL-18/19: Submitting a GTC LIMIT order (BUY or SELL) must:
    - call order_send with action=5 (TRADE_ACTION_PENDING), the correct MT5 order type
      (2=BUY_LIMIT or 3=SELL_LIMIT), type_time=0 (GTC), and the requested price;
    - emit OrderSubmitted followed by OrderAccepted (retcode 10008 PLACED);
    - NOT emit an immediate fill (no deal returned for pending orders).
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

    limit_price = 18000.00
    order = LimitOrder(
        trader_id=msgbus.trader_id,
        strategy_id=StrategyId(f"S-EL-18-{side.name}"),
        instrument_id=_USTEC_ID,
        client_order_id=ClientOrderId(f"O-EL-18-{side.name}"),
        order_side=side,
        quantity=Quantity.from_str("1"),
        price=Price.from_str(str(limit_price)),
        time_in_force=TimeInForce.GTC,
        init_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )
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

    exec_client.generate_order_submitted = MagicMock(side_effect=lambda *a, **kw: submitted_events.append(kw))
    exec_client.generate_order_accepted = MagicMock(side_effect=lambda *a, **kw: accepted_events.append(kw))
    exec_client.generate_order_rejected = MagicMock(side_effect=lambda *a, **kw: rejected_events.append(kw))

    nautilus_mt5_harness.root.reset_calls()
    await exec_client._submit_order(command)

    # --- Bridge call assertions ---
    order_send_calls = [c for c in nautilus_mt5_harness.root.calls if c.method == "order_send"]
    assert len(order_send_calls) == 1, f"Expected 1 order_send call, got {len(order_send_calls)}"
    req = order_send_calls[0].args[0]
    assert req["action"] == 5, f"Expected action=5 (TRADE_ACTION_PENDING), got {req['action']}"
    assert req["type"] == expected_mt5_type, (
        f"Expected MT5 order type {expected_mt5_type}, got {req['type']}"
    )
    assert req["type_time"] == 0, f"Expected type_time=0 (GTC), got {req['type_time']}"
    assert abs(req["price"] - limit_price) < 0.01, (
        f"Expected price ~{limit_price}, got {req['price']}"
    )
    assert req["symbol"] == "USTEC"

    # --- Nautilus event assertions ---
    assert len(rejected_events) == 0, f"Unexpected OrderRejected: {rejected_events}"
    assert len(submitted_events) == 1, "Expected exactly one OrderSubmitted event"
    assert len(accepted_events) == 1, "Expected exactly one OrderAccepted event"

    # venue_order_id must be set from the bridge response (order=1001 from fake)
    kwargs = exec_client.generate_order_accepted.call_args.kwargs
    assert str(kwargs.get("venue_order_id", "")) == "1001", (
        f"Expected venue_order_id='1001', got {kwargs.get('venue_order_id')}"
    )


# ---------------------------------------------------------------------------
# TC-EL-20  Market order fill end-to-end (stub bridge)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("side,expected_fill_side", [
    (OrderSide.BUY,  OrderSide.BUY),
    (OrderSide.SELL, OrderSide.SELL),
])
async def test_lifecycle_market_order_fill_end_to_end(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness, side, expected_fill_side
):
    """
    TC-EL-20: Submitting a market order (BUY or SELL) against the stub bridge
    produces the full event chain:
      OrderSubmitted → OrderAccepted → OrderFilled

    Validates that generate_order_filled is called with:
    - correct side, order_type=MARKET
    - trade_id matching the bridge deal ticket (101)
    - venue_order_id matching the bridge order ticket (1001)
    - last_qty and last_px from bridge response (0.1, 18500.50)
    - liquidity_side=TAKER

    For SELL orders the adapter calls positions_get first (hedge-close path);
    the stub bridge returns one open BUY position so the SELL is routed as a
    close-position order — this is correct MT5 hedging semantics.
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

    submitted_calls: list = []
    accepted_calls: list = []
    filled_calls: list = []
    rejected_calls: list = []

    exec_client.generate_order_submitted = MagicMock(side_effect=lambda *a, **kw: submitted_calls.append(kw))
    exec_client.generate_order_accepted  = MagicMock(side_effect=lambda *a, **kw: accepted_calls.append(kw))
    exec_client.generate_order_filled    = MagicMock(side_effect=lambda *a, **kw: filled_calls.append(kw))
    exec_client.generate_order_rejected  = MagicMock(side_effect=lambda *a, **kw: rejected_calls.append(kw))

    order = MarketOrder(
        trader_id=msgbus.trader_id,
        strategy_id=StrategyId(f"S-EL-20-{side.name}"),
        instrument_id=_USTEC_ID,
        client_order_id=ClientOrderId(f"O-EL-20-{side.name}"),
        order_side=side,
        quantity=Quantity.from_str("0.1"),
        time_in_force=TimeInForce.GTC,
        init_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )
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

    nautilus_mt5_harness.root.reset_calls()
    await exec_client._submit_order(command)

    # --- Event chain ---
    assert len(rejected_calls) == 0, f"Unexpected OrderRejected: {rejected_calls}"
    assert len(submitted_calls) == 1, "Expected exactly one OrderSubmitted"
    assert len(accepted_calls) == 1, "Expected exactly one OrderAccepted"
    assert len(filled_calls) == 1, (
        "Expected exactly one OrderFilled — market order with retcode=10009 and deal should emit fill"
    )

    # --- Fill field validation ---
    fill = filled_calls[0]
    assert fill["order_side"] == expected_fill_side
    assert fill["order_type"] == OrderType.MARKET
    assert str(fill["trade_id"]) == "101", f"Expected trade_id='101' (deal ticket), got {fill['trade_id']}"
    assert str(fill["venue_order_id"]) == "1001", f"Expected venue_order_id='1001', got {fill['venue_order_id']}"
    assert float(fill["last_qty"]) == pytest.approx(0.1)
    assert float(fill["last_px"]) == pytest.approx(18500.50)
    from nautilus_trader.model.enums import LiquiditySide as LS
    assert fill["liquidity_side"] == LS.TAKER, f"Expected TAKER, got {fill['liquidity_side']}"

    # --- Accepted venue_order_id ---
    assert str(accepted_calls[0].get("venue_order_id", "")) == "1001"


# ---------------------------------------------------------------------------
# TC-EL-21  GTC BUY/SELL STOP_MARKET → order_send action=5, correct type + OrderAccepted
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("side,expected_mt5_type", [
    (OrderSide.BUY,  4),  # ORDER_TYPE_BUY_STOP
    (OrderSide.SELL, 5),  # ORDER_TYPE_SELL_STOP
])
async def test_lifecycle_submit_gtc_stop_market_order(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness, side, expected_mt5_type
):
    """
    TC-EL-21/22: Submitting a GTC STOP_MARKET order (BUY or SELL) must:
    - call order_send with action=5 (TRADE_ACTION_PENDING), the correct MT5 order
      type (4=BUY_STOP or 5=SELL_STOP), and the trigger price in the 'price' field;
    - emit OrderSubmitted followed by OrderAccepted (retcode 10008 PLACED);
    - NOT emit an immediate fill (no deal for pending orders).

    BUY STOP trigger placed above market (80000 > 78000 ask).
    SELL STOP trigger placed below market (76000 < 78000 bid).
    """
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=_data_config("BTCUSD"),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await data_client._connect()

    exec_client = MT5LiveExecClientFactory.create(
        loop=loop, name="MT5", config=_exec_config("BTCUSD"),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await exec_client._connect()

    trigger_price = 80000.00 if side == OrderSide.BUY else 76000.00
    order = StopMarketOrder(
        trader_id=msgbus.trader_id,
        strategy_id=StrategyId(f"S-EL-21-{side.name}"),
        instrument_id=_BTCUSD_ID,
        client_order_id=ClientOrderId(f"O-EL-21-{side.name}"),
        order_side=side,
        quantity=Quantity.from_str("0.01"),
        trigger_price=Price.from_str(f"{trigger_price:.2f}"),
        trigger_type=TriggerType.DEFAULT,
        time_in_force=TimeInForce.GTC,
        init_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )
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

    exec_client.generate_order_submitted = MagicMock(side_effect=lambda *a, **kw: submitted_events.append(kw))
    exec_client.generate_order_accepted  = MagicMock(side_effect=lambda *a, **kw: accepted_events.append(kw))
    exec_client.generate_order_rejected  = MagicMock(side_effect=lambda *a, **kw: rejected_events.append(kw))
    exec_client.generate_order_filled    = MagicMock(side_effect=lambda *a, **kw: filled_events.append(kw))

    nautilus_mt5_harness.root.reset_calls()
    await exec_client._submit_order(command)

    # --- Bridge call assertions ---
    order_send_calls = [c for c in nautilus_mt5_harness.root.calls if c.method == "order_send"]
    assert len(order_send_calls) == 1, f"Expected 1 order_send call, got {len(order_send_calls)}"
    req = order_send_calls[0].args[0]
    assert req["action"] == 5, f"Expected action=5 (TRADE_ACTION_PENDING), got {req['action']}"
    assert req["type"] == expected_mt5_type, (
        f"Expected MT5 type {expected_mt5_type}, got {req['type']}"
    )
    assert abs(req["price"] - trigger_price) < 0.01, (
        f"Expected price (trigger) ~{trigger_price}, got {req['price']}"
    )
    assert req["symbol"] == "BTCUSD"
    assert "stoplimit" not in req, "STOP_MARKET must not include stoplimit field"

    # --- Nautilus event assertions ---
    assert len(rejected_events) == 0, f"Unexpected OrderRejected: {rejected_events}"
    assert len(submitted_events) == 1, "Expected exactly one OrderSubmitted"
    assert len(accepted_events) == 1, "Expected exactly one OrderAccepted"
    assert len(filled_events) == 0, "Pending stop order must not emit an immediate fill"

    # venue_order_id from bridge response (order=2001)
    kwargs = exec_client.generate_order_accepted.call_args.kwargs
    assert str(kwargs.get("venue_order_id", "")) == "2001", (
        f"Expected venue_order_id='2001', got {kwargs.get('venue_order_id')}"
    )


# ---------------------------------------------------------------------------
# TC-EL-23  GTC BUY/SELL STOP_LIMIT → action=5, type 6/7, price + stpx fields
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("side,expected_mt5_type,trigger,limit_p", [
    # BUY_STOP_LIMIT: stpx (NT price) must be BELOW trigger for MT5 validation.
    # When triggered at 80000, a limit buy at 79900 is created.
    (OrderSide.BUY,  6, 80000.00, 79900.00),  # ORDER_TYPE_BUY_STOP_LIMIT
    # SELL_STOP_LIMIT: stpx (NT price) must be ABOVE trigger for MT5 validation.
    # When triggered at 76000, a limit sell at 76100 is created.
    (OrderSide.SELL, 7, 76000.00, 76100.00),  # ORDER_TYPE_SELL_STOP_LIMIT
])
async def test_lifecycle_submit_gtc_stop_limit_order(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness,
    side, expected_mt5_type, trigger, limit_p
):
    """
    TC-EL-23/24: Submitting a GTC STOP_LIMIT order (BUY or SELL) must:
    - call order_send with action=5 (TRADE_ACTION_PENDING), the correct MT5 order
      type (6=BUY_STOP_LIMIT or 7=SELL_STOP_LIMIT);
    - set 'price' = trigger_price (the stop activation level);
    - set 'stpx' = limit price (the limit price activated once trigger fires);
    - emit OrderSubmitted followed by OrderAccepted (retcode 10008 PLACED);
    - NOT emit an immediate fill.

    BUY: trigger=80000 (above market 78000), limit=80100 (pay at most 80100).
    SELL: trigger=76000 (below market 78000), limit=75900 (accept at least 75900).
    """
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=_data_config("BTCUSD"),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await data_client._connect()

    exec_client = MT5LiveExecClientFactory.create(
        loop=loop, name="MT5", config=_exec_config("BTCUSD"),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await exec_client._connect()

    order = StopLimitOrder(
        trader_id=msgbus.trader_id,
        strategy_id=StrategyId(f"S-EL-23-{side.name}"),
        instrument_id=_BTCUSD_ID,
        client_order_id=ClientOrderId(f"O-EL-23-{side.name}"),
        order_side=side,
        quantity=Quantity.from_str("0.01"),
        price=Price.from_str(f"{limit_p:.2f}"),           # limit price (activated after trigger)
        trigger_price=Price.from_str(f"{trigger:.2f}"),   # stop activation price
        trigger_type=TriggerType.DEFAULT,
        time_in_force=TimeInForce.GTC,
        init_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )
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

    exec_client.generate_order_submitted = MagicMock(side_effect=lambda *a, **kw: submitted_events.append(kw))
    exec_client.generate_order_accepted  = MagicMock(side_effect=lambda *a, **kw: accepted_events.append(kw))
    exec_client.generate_order_rejected  = MagicMock(side_effect=lambda *a, **kw: rejected_events.append(kw))
    exec_client.generate_order_filled    = MagicMock(side_effect=lambda *a, **kw: filled_events.append(kw))

    nautilus_mt5_harness.root.reset_calls()
    await exec_client._submit_order(command)

    # --- Bridge call assertions ---
    order_send_calls = [c for c in nautilus_mt5_harness.root.calls if c.method == "order_send"]
    assert len(order_send_calls) == 1, f"Expected 1 order_send call, got {len(order_send_calls)}"
    req = order_send_calls[0].args[0]
    assert req["action"] == 5, f"Expected action=5 (TRADE_ACTION_PENDING), got {req['action']}"
    assert req["type"] == expected_mt5_type, (
        f"Expected MT5 type {expected_mt5_type}, got {req['type']}"
    )
    assert abs(req["price"] - trigger) < 0.01, (
        f"Expected price (trigger) ~{trigger}, got {req['price']}"
    )
    assert "stoplimit" in req, "STOP_LIMIT must include stoplimit (limit price after trigger)"
    assert abs(req["stoplimit"] - limit_p) < 0.01, (
        f"Expected stoplimit (limit) ~{limit_p}, got {req['stoplimit']}"
    )
    assert req["symbol"] == "BTCUSD"

    # --- Nautilus event assertions ---
    assert len(rejected_events) == 0, f"Unexpected OrderRejected: {rejected_events}"
    assert len(submitted_events) == 1, "Expected exactly one OrderSubmitted"
    assert len(accepted_events) == 1, "Expected exactly one OrderAccepted"
    assert len(filled_events) == 0, "Pending stop-limit order must not emit an immediate fill"

    # venue_order_id from bridge response (order=2001)
    kwargs = exec_client.generate_order_accepted.call_args.kwargs
    assert str(kwargs.get("venue_order_id", "")) == "2001", (
        f"Expected venue_order_id='2001', got {kwargs.get('venue_order_id')}"
    )
