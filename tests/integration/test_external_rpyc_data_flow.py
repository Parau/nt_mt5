import asyncio
import pytest
from nautilus_trader.model.identifiers import TraderId

from nautilus_mt5.client.types import MT5TerminalAccessMode
from nautilus_mt5.config import (
    ExternalRPyCTerminalConfig,
    MetaTrader5DataClientConfig,
    MetaTrader5InstrumentProviderConfig
)
from nautilus_mt5.factories import get_resolved_mt5_client, MT5_CLIENTS
from nautilus_mt5.data_types import MT5Symbol
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
async def test_external_rpyc_symbol_flow(
    clean_factory_cache,
    nautilus_components,
    fake_external_rpyc_environment
):
    """
    Test the symbol info flow in EXTERNAL_RPYC mode.
    """
    fake_root = fake_external_rpyc_environment
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    # Setup configuration for EXTERNAL_RPYC
    external_rpyc_config = ExternalRPyCTerminalConfig(
        host="127.0.0.1",
        port=18812
    )

    config = MetaTrader5DataClientConfig(
        client_id=1,
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

        # Execute symbol info flow
        symbol = MT5Symbol(symbol="EURUSD", broker="FakeBroker")
        # Clear connect calls
        fake_root.reset_calls()

        # This calls mt5_client.get_symbol_details(symbol)
        result = await mt5_client.get_symbol_details(symbol)

        # Validate symbol_info
        assert result is not None
        assert len(result) == 1
        assert result[0].name == "EURUSD"

        calls = fake_root.calls
        symbol_info_calls = [c for c in calls if c.method == "symbol_info"]
        assert len(symbol_info_calls) == 1
        assert symbol_info_calls[0].args[0] == "EURUSD"

        # Execute symbols_get flow
        fake_root.reset_calls()
        symbols = mt5_client._mt5_client['mt5'].symbols_get()
        assert symbols == ["EURUSD"]
        assert any(c.method == "symbols_get" for c in fake_root.calls)

        # Execute symbol_select flow
        fake_root.reset_calls()
        success = mt5_client._mt5_client['mt5'].symbol_select("EURUSD", True)
        assert success is True
        select_calls = [c for c in fake_root.calls if c.method == "symbol_select"]
        assert len(select_calls) == 1
        assert select_calls[0].args == ("EURUSD",)
        assert select_calls[0].kwargs == {"enable": True}

    finally:
        mt5_client.stop()
        await asyncio.sleep(0.1)


@pytest.mark.asyncio
async def test_external_rpyc_market_data_flow(
    clean_factory_cache,
    nautilus_components,
    fake_external_rpyc_environment
):
    """
    Test the market data flow (tick/candle) in EXTERNAL_RPYC mode.
    """
    fake_root = fake_external_rpyc_environment
    msgbus, cache, clock = nautilus_components
    loop = asyncio.get_running_loop()

    # Setup configuration for EXTERNAL_RPYC
    external_rpyc_config = ExternalRPyCTerminalConfig(
        host="127.0.0.1",
        port=18812
    )

    config = MetaTrader5DataClientConfig(
        client_id=1,
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=external_rpyc_config
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

        # Execute candle flow (copy_rates_from_pos)
        symbol_name = "EURUSD"
        timeframe = 1 # mt5.TIMEFRAME_M1
        start_pos = 0
        count = 10

        rates = mt5_client._mt5_client['mt5'].copy_rates_from_pos(symbol_name, timeframe, start_pos, count)

        # Validate copy_rates_from_pos
        assert rates is not None
        assert len(rates) == count
        assert rates[0]['close'] == 1.10050

        copy_rates_calls = [c for c in fake_root.calls if c.method == "copy_rates_from_pos"]
        assert len(copy_rates_calls) == 1
        assert copy_rates_calls[0].args == (symbol_name, timeframe, start_pos, count)

        # Execute tick flow (symbol_info_tick)
        fake_root.reset_calls()
        tick = mt5_client._mt5_client['mt5'].symbol_info_tick(symbol_name)

        assert tick is not None
        assert tick['bid'] == 1.10000

        tick_calls = [c for c in fake_root.calls if c.method == "symbol_info_tick"]
        assert len(tick_calls) == 1
        assert tick_calls[0].args[0] == symbol_name

        # Execute copy_ticks_range flow
        fake_root.reset_calls()
        ticks_range = mt5_client._mt5_client['mt5'].copy_ticks_range(symbol_name, 1700000000, 1700000060, 0)
        assert len(ticks_range) == 1
        assert ticks_range[0]['bid'] == 1.10000

        range_calls = [c for c in fake_root.calls if c.method == "copy_ticks_range"]
        assert len(range_calls) == 1
        assert range_calls[0].args == (symbol_name, 1700000000, 1700000060, 0)

        # Execute copy_ticks_from flow
        fake_root.reset_calls()
        ticks_from = mt5_client._mt5_client['mt5'].copy_ticks_from(symbol_name, 1700000000, 5, 0)
        assert len(ticks_from) == 5
        assert ticks_from[0]['ask'] == 1.10020

        from_calls = [c for c in fake_root.calls if c.method == "copy_ticks_from"]
        assert len(from_calls) == 1
        assert from_calls[0].args == (symbol_name, 1700000000, 5, 0)

    finally:
        mt5_client.stop()
        await asyncio.sleep(0.1)
