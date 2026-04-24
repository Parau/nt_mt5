import pytest
from unittest.mock import MagicMock, patch
from nautilus_mt5.metatrader5.MetaTrader5 import MetaTrader5

@pytest.fixture
def mock_rpyc_connect():
    """
    Fixture to mock rpyc.connect and return a fake connection with independent mocks
    for the exposed endpoints for market data.
    """
    with patch("rpyc.connect") as mock_connect:
        mock_conn = MagicMock()
        # Set up independent mocks for the exposed endpoints
        mock_conn.root.exposed_symbols_get = MagicMock(name="exposed_symbols_get")
        mock_conn.root.exposed_symbol_info = MagicMock(name="exposed_symbol_info")
        mock_conn.root.exposed_symbol_info_tick = MagicMock(name="exposed_symbol_info_tick")
        mock_conn.root.exposed_symbol_select = MagicMock(name="exposed_symbol_select")
        mock_conn.root.exposed_copy_rates_from_pos = MagicMock(name="exposed_copy_rates_from_pos")
        mock_conn.root.exposed_copy_ticks_range = MagicMock(name="exposed_copy_ticks_range")
        mock_conn.root.exposed_copy_ticks_from = MagicMock(name="exposed_copy_ticks_from")

        # This one must NOT be called by the target methods
        mock_conn.root.exposed_positions_get = MagicMock(name="exposed_positions_get")

        mock_connect.return_value = mock_conn
        yield mock_connect, mock_conn

def test_symbols_get_routing(mock_rpyc_connect):
    mock_connect, mock_conn = mock_rpyc_connect
    mt5 = MetaTrader5()

    expected_return = "symbols_list"
    mock_conn.root.exposed_symbols_get.return_value = expected_return

    result = mt5.symbols_get(group="*USD*")

    mock_conn.root.exposed_symbols_get.assert_called_once_with(group="*USD*")
    assert result == expected_return
    mock_conn.root.exposed_positions_get.assert_not_called()

def test_symbol_info_routing(mock_rpyc_connect):
    mock_connect, mock_conn = mock_rpyc_connect
    mt5 = MetaTrader5()

    expected_return = {"name": "EURUSD"}
    mock_conn.root.exposed_symbol_info.return_value = expected_return

    result = mt5.symbol_info("EURUSD")

    mock_conn.root.exposed_symbol_info.assert_called_once_with("EURUSD")
    assert result == expected_return
    mock_conn.root.exposed_positions_get.assert_not_called()

def test_symbol_info_tick_routing(mock_rpyc_connect):
    mock_connect, mock_conn = mock_rpyc_connect
    mt5 = MetaTrader5()

    expected_return = "tick_data"
    mock_conn.root.exposed_symbol_info_tick.return_value = expected_return

    result = mt5.symbol_info_tick("EURUSD")

    mock_conn.root.exposed_symbol_info_tick.assert_called_once_with("EURUSD")
    assert result == expected_return
    mock_conn.root.exposed_positions_get.assert_not_called()

def test_symbol_select_routing(mock_rpyc_connect):
    mock_connect, mock_conn = mock_rpyc_connect
    mt5 = MetaTrader5()

    expected_return = True
    mock_conn.root.exposed_symbol_select.return_value = expected_return

    result = mt5.symbol_select("EURUSD", True)

    mock_conn.root.exposed_symbol_select.assert_called_once_with("EURUSD", True)
    assert result == expected_return
    mock_conn.root.exposed_positions_get.assert_not_called()

def test_copy_rates_from_pos_routing(mock_rpyc_connect):
    mock_connect, mock_conn = mock_rpyc_connect
    mt5 = MetaTrader5()

    expected_return = "rates_data"
    mock_conn.root.exposed_copy_rates_from_pos.return_value = expected_return

    result = mt5.copy_rates_from_pos("EURUSD", 1, 0, 10)

    mock_conn.root.exposed_copy_rates_from_pos.assert_called_once_with("EURUSD", 1, 0, 10)
    assert result == expected_return
    mock_conn.root.exposed_positions_get.assert_not_called()

def test_copy_ticks_range_routing(mock_rpyc_connect):
    mock_connect, mock_conn = mock_rpyc_connect
    mt5 = MetaTrader5()

    expected_return = "ticks_data_range"
    mock_conn.root.exposed_copy_ticks_range.return_value = expected_return

    result = mt5.copy_ticks_range("EURUSD", 1000, 2000, 0)

    mock_conn.root.exposed_copy_ticks_range.assert_called_once_with("EURUSD", 1000, 2000, 0)
    assert result == expected_return
    mock_conn.root.exposed_positions_get.assert_not_called()

def test_copy_ticks_from_routing(mock_rpyc_connect):
    mock_connect, mock_conn = mock_rpyc_connect
    mt5 = MetaTrader5()

    expected_return = "ticks_data_from"
    mock_conn.root.exposed_copy_ticks_from.return_value = expected_return

    result = mt5.copy_ticks_from("EURUSD", 1000, 10, 0)

    mock_conn.root.exposed_copy_ticks_from.assert_called_once_with("EURUSD", 1000, 10, 0)
    assert result == expected_return
    mock_conn.root.exposed_positions_get.assert_not_called()
