import pytest
from unittest.mock import MagicMock, patch
from nautilus_mt5.metatrader5.MetaTrader5 import MetaTrader5

@pytest.fixture
def mock_rpyc_connect():
    with patch("rpyc.connect") as mock_connect:
        mock_conn = MagicMock()
        # Default mock_conn should not have 'eval' unless we specifically add it
        # However, rpyc connections might have it. Let's ensure we can control it.
        del mock_conn.eval
        mock_connect.return_value = mock_conn
        yield mock_connect, mock_conn

def test_initialize_routing(mock_rpyc_connect):
    mock_connect, mock_conn = mock_rpyc_connect
    mt5 = MetaTrader5()

    mt5.initialize("path", login=123, password="pwd", server="srv", timeout=1000)

    mock_conn.root.exposed_initialize.assert_called_once_with(
        "path", login=123, password="pwd", server="srv", timeout=1000
    )
    mock_conn.root.exposed_positions_get.assert_not_called()

def test_login_routing(mock_rpyc_connect):
    mock_connect, mock_conn = mock_rpyc_connect
    mt5 = MetaTrader5()

    mt5.login(123, password="pwd", server="srv", timeout=1000)

    mock_conn.root.exposed_login.assert_called_once_with(
        123, password="pwd", server="srv", timeout=1000
    )
    mock_conn.root.exposed_positions_get.assert_not_called()

def test_shutdown_routing(mock_rpyc_connect):
    mock_connect, mock_conn = mock_rpyc_connect
    mt5 = MetaTrader5()

    mt5.shutdown()

    mock_conn.root.exposed_shutdown.assert_called_once()
    mock_conn.root.exposed_positions_get.assert_not_called()

def test_version_routing(mock_rpyc_connect):
    mock_connect, mock_conn = mock_rpyc_connect
    mt5 = MetaTrader5()

    mt5.version()

    mock_conn.root.exposed_version.assert_called_once()
    mock_conn.root.exposed_positions_get.assert_not_called()

def test_last_error_routing(mock_rpyc_connect):
    mock_connect, mock_conn = mock_rpyc_connect
    mt5 = MetaTrader5()

    mt5.last_error()

    mock_conn.root.exposed_last_error.assert_called_once()
    mock_conn.root.exposed_positions_get.assert_not_called()

def test_terminal_info_routing(mock_rpyc_connect):
    mock_connect, mock_conn = mock_rpyc_connect
    # We want it to call exposed_terminal_info regardless of eval presence
    # The current implementation has a bug that branches on 'eval' presence
    # but still calls the wrong thing in one branch.

    # Test case 1: eval is present (common in RPyC classic/service connections)
    mock_conn.eval = MagicMock()
    mt5 = MetaTrader5()
    mt5.terminal_info()
    mock_conn.root.exposed_terminal_info.assert_called_once()
    mock_conn.root.exposed_positions_get.assert_not_called()

def test_terminal_info_routing_no_eval(mock_rpyc_connect):
    mock_connect, mock_conn = mock_rpyc_connect
    # Test case 2: eval is NOT present
    if hasattr(mock_conn, "eval"):
        del mock_conn.eval

    mt5 = MetaTrader5()
    mt5.terminal_info()
    mock_conn.root.exposed_terminal_info.assert_called_once()
    mock_conn.root.exposed_positions_get.assert_not_called()

def test_account_info_routing(mock_rpyc_connect):
    mock_connect, mock_conn = mock_rpyc_connect
    mt5 = MetaTrader5()

    mt5.account_info()

    mock_conn.root.exposed_account_info.assert_called_once()
    mock_conn.root.exposed_positions_get.assert_not_called()

def test_get_constant_routing(mock_rpyc_connect):
    mock_connect, mock_conn = mock_rpyc_connect
    mt5 = MetaTrader5()

    # This method is expected to exist in the MetaTrader5 wrapper
    # and route to exposed_get_constant
    mt5.get_constant("TIMEFRAME_M1")

    mock_conn.root.exposed_get_constant.assert_called_once_with("TIMEFRAME_M1")
    mock_conn.root.exposed_positions_get.assert_not_called()
