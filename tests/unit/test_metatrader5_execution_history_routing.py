import pytest
from unittest.mock import MagicMock, patch
from nautilus_mt5.metatrader5.MetaTrader5 import MetaTrader5

@pytest.fixture
def mock_rpyc_connect():
    """
    Fixture to mock rpyc.connect and return a fake connection with independent mocks
    for the exposed endpoints for execution and history.
    """
    with patch("rpyc.connect") as mock_connect:
        mock_conn = MagicMock()
        # Set up independent mocks for the exposed endpoints
        mock_conn.root.exposed_order_send = MagicMock(name="exposed_order_send")
        mock_conn.root.exposed_positions_get = MagicMock(name="exposed_positions_get")
        mock_conn.root.exposed_history_orders_total = MagicMock(name="exposed_history_orders_total")
        mock_conn.root.exposed_history_orders_get = MagicMock(name="exposed_history_orders_get")
        mock_conn.root.exposed_history_deals_total = MagicMock(name="exposed_history_deals_total")
        mock_conn.root.exposed_history_deals_get = MagicMock(name="exposed_history_deals_get")

        # Mock sentinels to ensure no routing to other domains
        mock_conn.root.exposed_initialize = MagicMock(name="exposed_initialize")
        mock_conn.root.exposed_symbol_info = MagicMock(name="exposed_symbol_info")
        mock_conn.root.exposed_copy_rates_from_pos = MagicMock(name="exposed_copy_rates_from_pos")

        mock_connect.return_value = mock_conn
        yield mock_connect, mock_conn

def test_order_send_routing(mock_rpyc_connect):
    _, mock_conn = mock_rpyc_connect
    mt5 = MetaTrader5()
    request = {"action": 1, "symbol": "EURUSD", "volume": 1.0}
    expected_return = "order_result"
    mock_conn.root.exposed_order_send.return_value = expected_return

    result = mt5.order_send(request)

    mock_conn.root.exposed_order_send.assert_called_once_with(request)
    assert result == expected_return
    mock_conn.root.exposed_positions_get.assert_not_called()

def test_positions_get_routing(mock_rpyc_connect):
    _, mock_conn = mock_rpyc_connect
    mt5 = MetaTrader5()
    expected_return = "positions_list"
    mock_conn.root.exposed_positions_get.return_value = expected_return

    result = mt5.positions_get(symbol="EURUSD")

    mock_conn.root.exposed_positions_get.assert_called_once_with(symbol="EURUSD")
    assert result == expected_return

def test_history_orders_total_routing(mock_rpyc_connect):
    _, mock_conn = mock_rpyc_connect
    mt5 = MetaTrader5()
    expected_return = 10
    mock_conn.root.exposed_history_orders_total.return_value = expected_return

    result = mt5.history_orders_total(1000, 2000)

    mock_conn.root.exposed_history_orders_total.assert_called_once_with(1000, 2000)
    assert result == expected_return
    mock_conn.root.exposed_positions_get.assert_not_called()

def test_history_orders_get_routing(mock_rpyc_connect):
    _, mock_conn = mock_rpyc_connect
    mt5 = MetaTrader5()
    expected_return = "history_orders_list"
    mock_conn.root.exposed_history_orders_get.return_value = expected_return

    result = mt5.history_orders_get(1000, 2000, group="*USD*")

    mock_conn.root.exposed_history_orders_get.assert_called_once_with(1000, 2000, group="*USD*")
    assert result == expected_return
    mock_conn.root.exposed_positions_get.assert_not_called()

def test_history_deals_total_routing(mock_rpyc_connect):
    _, mock_conn = mock_rpyc_connect
    mt5 = MetaTrader5()
    expected_return = 5
    mock_conn.root.exposed_history_deals_total.return_value = expected_return

    result = mt5.history_deals_total(1000, 2000)

    mock_conn.root.exposed_history_deals_total.assert_called_once_with(1000, 2000)
    assert result == expected_return
    mock_conn.root.exposed_positions_get.assert_not_called()

def test_history_deals_get_routing(mock_rpyc_connect):
    _, mock_conn = mock_rpyc_connect
    mt5 = MetaTrader5()
    expected_return = "history_deals_list"
    mock_conn.root.exposed_history_deals_get.return_value = expected_return

    result = mt5.history_deals_get(1000, 2000, group="*USD*")

    mock_conn.root.exposed_history_deals_get.assert_called_once_with(1000, 2000, group="*USD*")
    assert result == expected_return
    mock_conn.root.exposed_positions_get.assert_not_called()
