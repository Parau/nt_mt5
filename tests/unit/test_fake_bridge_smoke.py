import pytest
from tests.support.fake_mt5_rpyc_bridge import make_fake_mt5_rpyc_connection

def test_fake_bridge_surface():
    """
    Smoke test to verify the fake bridge helper is correctly implemented and importable.
    """
    connection = make_fake_mt5_rpyc_connection()
    assert connection.root.exposed_initialize() is True
    assert connection.root.exposed_login() is True
    assert connection.root.exposed_last_error() == (0, "OK")
    assert connection.root.exposed_version() == (500, 0, "Fake MT5")
    assert connection.root.exposed_shutdown() is True
    assert connection.root.exposed_get_constant("TIMEFRAME_M1") == 1

    terminal_info = connection.root.exposed_terminal_info()
    assert terminal_info["name"] == "Fake MetaTrader 5"

    account_info = connection.root.exposed_account_info()
    assert account_info["login"] == 123456

    assert connection.root.exposed_symbols_get() == ["EURUSD"]
    assert connection.root.exposed_symbol_info("EURUSD")["name"] == "EURUSD"
    assert connection.root.exposed_symbol_info_tick("EURUSD")["bid"] == 1.10000
    assert connection.root.exposed_symbol_select("EURUSD") is True

    assert len(connection.root.exposed_copy_rates_from_pos("EURUSD", 1, 0, 10)) == 10
    assert len(connection.root.exposed_copy_ticks_range("EURUSD", None, None, 0)) == 1
    assert len(connection.root.exposed_copy_ticks_from("EURUSD", None, 5, 0)) == 5

    assert connection.root.exposed_order_send({})["retcode"] == 10009
    assert len(connection.root.exposed_positions_get()) == 1
    assert connection.root.exposed_history_orders_total() == 1
    assert len(connection.root.exposed_history_orders_get()) == 1
    assert connection.root.exposed_history_deals_total() == 1
    assert len(connection.root.exposed_history_deals_get()) == 1

def test_fake_bridge_missing_method():
    """
    Verify that non-implemented methods raise AttributeError.
    """
    connection = make_fake_mt5_rpyc_connection()
    with pytest.raises(AttributeError):
        connection.root.exposed_non_existent_method()
