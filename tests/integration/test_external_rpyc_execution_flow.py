import asyncio
import pytest
from datetime import datetime

from nautilus_mt5.client.types import MT5TerminalAccessMode
from nautilus_mt5.config import (
    ExternalRPyCTerminalConfig,
    MetaTrader5ExecClientConfig,
    MetaTrader5InstrumentProviderConfig
)
from nautilus_mt5.factories import get_resolved_mt5_client, MT5_CLIENTS
from nautilus_mt5.metatrader5.models import Order as MT5Order
from tests.support.nautilus_components import nautilus_components
from tests.support.external_rpyc_harness import fake_external_rpyc_environment


@pytest.fixture
def clean_factory_cache():
    """
    Ensure MT5_CLIENTS factory cache is clean before and after each test.
    """
    MT5_CLIENTS.clear()
    yield
    MT5_CLIENTS.clear()


@pytest.mark.asyncio
async def test_external_rpyc_execution_flow(
    clean_factory_cache,
    nautilus_components,
    fake_external_rpyc_environment
):
    """
    Test the execution and operational history flow in EXTERNAL_RPYC mode.
    """
    fake_root = fake_external_rpyc_environment
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    # Setup configuration for EXTERNAL_RPYC
    external_rpyc_config = ExternalRPyCTerminalConfig(
        host="127.0.0.1",
        port=18812
    )

    # We need a valid account_id for ExecClient
    config = MetaTrader5ExecClientConfig(
        client_id=1,
        account_id="123456",
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=external_rpyc_config,
        instrument_provider=MetaTrader5InstrumentProviderConfig()
    )

    # Use factory to get and start the client
    mt5_client = get_resolved_mt5_client(
        loop=loop,
        msgbus=msgbus,
        cache=cache,
        clock=clock,
        config=config
    )

    try:
        await mt5_client.wait_until_ready(timeout=5)
        fake_root.reset_calls()

        # CASE 1: order_send
        # Use direct internal call to validate return value from fake bridge
        request = {
            "action": 1,
            "symbol": "EURUSD",
            "volume": 1.0,
        }
        result = mt5_client._mt5_client['mt5'].order_send(request)

        # Validate order_send call
        calls = fake_root.calls
        order_send_calls = [c for c in calls if c.method == "order_send"]
        assert len(order_send_calls) == 1
        assert order_send_calls[0].args[0] == request

        # Validate return from fake bridge
        assert result["retcode"] == 10009
        assert result["comment"] == "Request completed"
        assert result["order"] == 1
        assert result["deal"] == 1

        # Also test via place_order (the higher level mixin method)
        fake_root.reset_calls()
        order = MT5Order(
            action=1,
            symbol="EURUSD",
            volume=1.0,
            type=0,
            price=1.1000,
            comment="mixin call"
        )
        mt5_client.place_order(order)
        assert any(c.method == "order_send" for c in fake_root.calls)

        # CASE 2: positions_get
        fake_root.reset_calls()
        # Requirement: Execute: positions = mt5_client.positions_get(symbol="EURUSD") or equivalent.
        positions = mt5_client._mt5_client['mt5'].positions_get(symbol="EURUSD")
        assert positions is not None
        assert len(positions) == 1
        assert positions[0]['symbol'] == "EURUSD"
        assert positions[0]['ticket'] == 1

        pos_get_calls = [c for c in fake_root.calls if c.method == "positions_get"]
        assert len(pos_get_calls) == 1
        assert pos_get_calls[0].kwargs == {"symbol": "EURUSD"}

        # CASE 3: Operational History (history_orders_get)
        fake_root.reset_calls()
        from_date = datetime(2023, 1, 1)
        to_date = datetime(2023, 1, 2)

        history_orders = mt5_client._mt5_client['mt5'].history_orders_get(from_date, to_date, group="*")
        assert history_orders is not None
        assert len(history_orders) == 1
        assert history_orders[0]['ticket'] == 1

        history_calls = [c for c in fake_root.calls if c.method == "history_orders_get"]
        assert len(history_calls) == 1
        assert history_calls[0].args == (from_date, to_date)
        assert history_calls[0].kwargs == {"group": "*"}

        # CASE 4: Operational History (history_deals_total)
        fake_root.reset_calls()
        total_deals = mt5_client._mt5_client['mt5'].history_deals_total(from_date, to_date)
        assert total_deals == 1

        total_calls = [c for c in fake_root.calls if c.method == "history_deals_total"]
        assert len(total_calls) == 1
        assert total_calls[0].args == (from_date, to_date)

        # CASE 5: Operational History (history_deals_get)
        fake_root.reset_calls()
        history_deals = mt5_client._mt5_client['mt5'].history_deals_get(from_date, to_date)
        assert history_deals is not None
        assert len(history_deals) == 1
        assert history_deals[0]['ticket'] == 1

        deals_get_calls = [c for c in fake_root.calls if c.method == "history_deals_get"]
        assert len(deals_get_calls) == 1
        assert deals_get_calls[0].args == (from_date, to_date)

    finally:
        mt5_client.stop()
        await asyncio.sleep(0.1)
