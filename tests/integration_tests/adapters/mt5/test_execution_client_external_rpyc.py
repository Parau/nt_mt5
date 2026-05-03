"""
test_execution_client_external_rpyc.py
Nautilus-level execution client integration tests for EXTERNAL_RPYC mode.

Exercises the path:
    MT5LiveExecClientFactory.create(...)
    → MetaTrader5ExecutionClient._connect()
    → account validation against fake bridge (login=123456)
    → _submit_order()
    → MetaTrader5Client.place_order() → fake bridge.exposed_order_send()
    → generate_order_submitted() called

No real MT5, no live env vars.
"""
import asyncio
from unittest.mock import MagicMock

import pytest

from nautilus_trader.model.currencies import USD
from nautilus_trader.model.enums import OrderSide, OrderType, TimeInForce
from nautilus_trader.model.identifiers import (
    AccountId,
    ClientOrderId,
    InstrumentId,
    StrategyId,
    Symbol,
    TraderId,
    Venue,
)
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.model.orders import MarketOrder
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.execution.messages import SubmitOrder

from nautilus_mt5.client.types import MT5TerminalAccessMode
from nautilus_mt5.config import (
    ExternalRPyCTerminalConfig,
    MetaTrader5DataClientConfig,
    MetaTrader5ExecClientConfig,
    MetaTrader5InstrumentProviderConfig,
)
from nautilus_mt5.data_types import MT5Symbol
from nautilus_mt5.execution import MetaTrader5ExecutionClient
from nautilus_mt5.factories import (
    MT5LiveDataClientFactory,
    MT5LiveExecClientFactory,
)
from nautilus_mt5.venue_profile import TICKMILL_DEMO_PROFILE


_RPYC_CONFIG = ExternalRPyCTerminalConfig(host="127.0.0.1", port=18812)
_VENUE = Venue("METATRADER_5")
_USTEC_ID = InstrumentId(Symbol("USTEC"), _VENUE)


def _data_config(*symbols: str) -> MetaTrader5DataClientConfig:
    load = frozenset(MT5Symbol(symbol=s) for s in symbols) if symbols else None
    return MetaTrader5DataClientConfig(
        client_id=1,
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=_RPYC_CONFIG,
        venue_profile=TICKMILL_DEMO_PROFILE,
        instrument_provider=MetaTrader5InstrumentProviderConfig(load_symbols=load),
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


@pytest.mark.asyncio
async def test_exec_client_connect_validates_account(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    _connect() reads account_info from the fake bridge (login=123456),
    matches it against config.account_id="123456", and calls _set_connected(True).
    """
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    exec_client = MT5LiveExecClientFactory.create(
        loop=loop, name="MT5", config=_exec_config(),
        msgbus=msgbus, cache=cache, clock=clock,
    )

    assert isinstance(exec_client, MetaTrader5ExecutionClient)

    exec_client._set_connected = MagicMock(wraps=exec_client._set_connected)
    await exec_client._connect()

    exec_client._set_connected.assert_called_once_with(True)


@pytest.mark.asyncio
async def test_exec_client_connect_rejects_wrong_account(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    _connect() raises ConnectionError when config.account_id does not match the
    login returned by the fake bridge (123456 vs 999999).
    """
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    wrong_config = MetaTrader5ExecClientConfig(
        client_id=1,
        account_id="999999",
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=_RPYC_CONFIG,
        instrument_provider=MetaTrader5InstrumentProviderConfig(),
    )

    exec_client = MT5LiveExecClientFactory.create(
        loop=loop, name="MT5", config=wrong_config,
        msgbus=msgbus, cache=cache, clock=clock,
    )

    with pytest.raises(ConnectionError, match="account mismatch"):
        await exec_client._connect()


@pytest.mark.asyncio
async def test_exec_client_submit_order_calls_order_send(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    _submit_order() translates a Nautilus MarketOrder into an MT5 request and
    calls order_send() on the fake bridge via the MetaTrader5Client pipeline.
    """
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    # Data client loads USTEC into cache (shared cache with exec client).
    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=_data_config("USTEC"),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await data_client._connect()

    # Exec client gets a handle on the same underlying MT5Client.
    exec_client = MT5LiveExecClientFactory.create(
        loop=loop, name="MT5", config=_exec_config("USTEC"),
        msgbus=msgbus, cache=cache, clock=clock,
    )
    await exec_client._connect()

    fake_conn = nautilus_mt5_harness
    fake_conn.root.reset_calls()

    strategy_id = StrategyId("S-001")
    order = MarketOrder(
        trader_id=msgbus.trader_id,
        strategy_id=strategy_id,
        instrument_id=_USTEC_ID,
        client_order_id=ClientOrderId("O-001"),
        order_side=OrderSide.BUY,
        quantity=Quantity.from_str("1"),
        time_in_force=TimeInForce.GTC,
        init_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )

    command = SubmitOrder(
        trader_id=msgbus.trader_id,
        strategy_id=strategy_id,
        order=order,
        position_id=None,
        client_id=exec_client.id,
        command_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )

    await exec_client._submit_order(command)

    calls = fake_conn.root.calls
    order_send_calls = [c for c in calls if c.method == "order_send"]
    assert len(order_send_calls) == 1, (
        f"Expected 1 order_send call, got {len(order_send_calls)}. "
        f"All calls: {[c.method for c in calls]}"
    )


@pytest.mark.asyncio
async def test_exec_client_submit_order_generates_submitted_event(
    clean_factory_cache, nautilus_components, nautilus_mt5_harness
):
    """
    _submit_order() calls generate_order_submitted() after placing the order.
    Verifies the event is generated via the Nautilus execution pipeline.
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

    strategy_id = StrategyId("S-002")
    order = MarketOrder(
        trader_id=msgbus.trader_id,
        strategy_id=strategy_id,
        instrument_id=_USTEC_ID,
        client_order_id=ClientOrderId("O-002"),
        order_side=OrderSide.BUY,
        quantity=Quantity.from_str("1"),
        time_in_force=TimeInForce.GTC,
        init_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )

    command = SubmitOrder(
        trader_id=msgbus.trader_id,
        strategy_id=strategy_id,
        order=order,
        position_id=None,
        client_id=exec_client.id,
        command_id=UUID4(),
        ts_init=clock.timestamp_ns(),
    )

    await exec_client._submit_order(command)

    assert exec_client.generate_order_submitted.called, (
        "generate_order_submitted was not called after _submit_order"
    )
