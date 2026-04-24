import pytest
from tests.support.fake_mt5_rpyc_bridge import make_fake_mt5_rpyc_connection, FakeMT5RPyCCall

def test_fake_bridge_call_recording():
    """
    Verify that the fake bridge correctly records calls.
    """
    connection = make_fake_mt5_rpyc_connection()
    root = connection.root

    # Initial state should be empty
    assert len(root.calls) == 0

    # Call some methods
    root.exposed_initialize(login=12345, server="TestServer")
    root.exposed_symbol_info("EURUSD")
    root.exposed_order_send({"action": 1, "symbol": "EURUSD", "volume": 0.1})

    # Verify calls are recorded
    assert len(root.calls) == 3

    # Check first call: initialize
    call1 = root.calls[0]
    assert call1.method == "initialize"
    assert call1.kwargs == {"login": 12345, "server": "TestServer"}

    # Check second call: symbol_info
    call2 = root.calls[1]
    assert call2.method == "symbol_info"
    assert call2.args == ("EURUSD",)

    # Check third call: order_send
    call3 = root.calls[2]
    assert call3.method == "order_send"
    assert call3.args == ({"action": 1, "symbol": "EURUSD", "volume": 0.1},)

def test_fake_bridge_reset_calls():
    """
    Verify that reset_calls works as expected.
    """
    connection = make_fake_mt5_rpyc_connection()
    root = connection.root

    root.exposed_version()
    assert len(root.calls) == 1

    root.reset_calls()
    assert len(root.calls) == 0

def test_fake_bridge_recording_order():
    """
    Verify that the order of calls is preserved.
    """
    connection = make_fake_mt5_rpyc_connection()
    root = connection.root

    root.exposed_account_info()
    root.exposed_terminal_info()
    root.exposed_symbols_get()

    assert [call.method for call in root.calls] == [
        "account_info",
        "terminal_info",
        "symbols_get",
    ]

def test_fake_bridge_all_surface_methods_record_calls():
    """
    Verify that all methods in the minimum surface record calls.
    """
    connection = make_fake_mt5_rpyc_connection()
    root = connection.root

    methods_to_test = [
        ("exposed_initialize", (), {}),
        ("exposed_login", (), {}),
        ("exposed_last_error", (), {}),
        ("exposed_version", (), {}),
        ("exposed_shutdown", (), {}),
        ("exposed_get_constant", ("TIMEFRAME_M1",), {}),
        ("exposed_terminal_info", (), {}),
        ("exposed_account_info", (), {}),
        ("exposed_symbols_get", (), {}),
        ("exposed_symbol_info", ("EURUSD",), {}),
        ("exposed_symbol_info_tick", ("EURUSD",), {}),
        ("exposed_symbol_select", ("EURUSD",), {"enable": True}),
        ("exposed_copy_rates_from_pos", ("EURUSD", 1, 0, 10), {}),
        ("exposed_copy_ticks_range", ("EURUSD", None, None, 0), {}),
        ("exposed_copy_ticks_from", ("EURUSD", None, 5, 0), {}),
        ("exposed_order_send", ({},), {}),
        ("exposed_positions_get", (), {}),
        ("exposed_history_orders_total", (), {}),
        ("exposed_history_orders_get", (), {}),
        ("exposed_history_deals_total", (), {}),
        ("exposed_history_deals_get", (), {}),
    ]

    for method_name, args, kwargs in methods_to_test:
        root.reset_calls()
        method = getattr(root, method_name)
        method(*args, **kwargs)
        assert len(root.calls) == 1
        # Logical method name recorded should not have 'exposed_' prefix
        expected_method_name = method_name.replace("exposed_", "")
        assert root.calls[0].method == expected_method_name
