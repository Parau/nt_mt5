import pytest
from tests.support.fake_mt5_rpyc_bridge import make_fake_mt5_rpyc_connection

def test_fake_connection_has_root():
    """
    Validar que a fake connection possui atributo root.
    """
    connection = make_fake_mt5_rpyc_connection()
    assert connection.root is not None

def test_fake_bridge_has_all_minimum_endpoints():
    """
    Validar que connection.root possui todos os endpoints mínimos.
    """
    connection = make_fake_mt5_rpyc_connection()
    root = connection.root

    expected_endpoints = [
        "exposed_initialize",
        "exposed_login",
        "exposed_last_error",
        "exposed_version",
        "exposed_shutdown",
        "exposed_get_constant",
        "exposed_terminal_info",
        "exposed_account_info",
        "exposed_symbols_get",
        "exposed_symbol_info",
        "exposed_symbol_info_tick",
        "exposed_symbol_select",
        "exposed_copy_rates_from_pos",
        "exposed_copy_ticks_range",
        "exposed_copy_ticks_from",
        "exposed_order_send",
        "exposed_positions_get",
        "exposed_history_orders_total",
        "exposed_history_orders_get",
        "exposed_history_deals_total",
        "exposed_history_deals_get",
    ]

    for endpoint in expected_endpoints:
        assert hasattr(root, endpoint), f"Endpoint {endpoint} is missing from fake bridge root"
        method = getattr(root, endpoint)
        assert callable(method), f"Endpoint {endpoint} is not callable"

def test_fake_bridge_session_deterministic_returns():
    """
    Validar que sessao e diagnostico retornam valores deterministicos.
    """
    connection = make_fake_mt5_rpyc_connection()
    root = connection.root

    assert root.exposed_initialize() is True
    assert root.exposed_login(123456, password="pwd", server="FakeServer") is True
    assert root.exposed_last_error() == (0, "OK")
    assert root.exposed_shutdown() is True

    version = root.exposed_version()
    assert isinstance(version, (tuple, list))
    assert len(version) >= 2

    assert root.exposed_get_constant("TIMEFRAME_M1") == 1
    assert root.exposed_get_constant("NON_EXISTENT") is None

def test_fake_bridge_terminal_and_account_info():
    """
    Validar que terminal e conta retornam dados minimos esperados.
    """
    connection = make_fake_mt5_rpyc_connection()
    root = connection.root

    terminal_info = root.exposed_terminal_info()
    assert isinstance(terminal_info, dict)
    assert "connected" in terminal_info
    assert "trade_allowed" in terminal_info
    assert terminal_info["connected"] is True

    account_info = root.exposed_account_info()
    assert isinstance(account_info, dict)
    assert "login" in account_info
    assert "balance" in account_info
    assert "currency" in account_info
    assert account_info["login"] == 123456

def test_fake_bridge_symbols_and_market_data():
    """
    Validar que simbolos e market data retornam dados minimos determinísticos.
    """
    connection = make_fake_mt5_rpyc_connection()
    root = connection.root

    symbols = root.exposed_symbols_get()
    assert isinstance(symbols, list)
    assert "EURUSD" in symbols

    symbol_info = root.exposed_symbol_info("EURUSD")
    assert isinstance(symbol_info, dict)
    assert symbol_info["name"] == "EURUSD"

    tick = root.exposed_symbol_info_tick("EURUSD")
    assert isinstance(tick, dict)
    assert tick["symbol"] == "EURUSD"
    assert "bid" in tick
    assert "ask" in tick

    assert root.exposed_symbol_select("EURUSD", True) is True

    rates = root.exposed_copy_rates_from_pos("EURUSD", 1, 0, 2)
    assert isinstance(rates, list)
    assert len(rates) == 2
    assert "close" in rates[0]

    ticks_range = root.exposed_copy_ticks_range("EURUSD", 1700000000, 1700000060, 0)
    assert isinstance(ticks_range, list)
    assert len(ticks_range) > 0

    ticks_from = root.exposed_copy_ticks_from("EURUSD", 1700000000, 2, 0)
    assert isinstance(ticks_from, list)
    assert len(ticks_from) == 2

def test_fake_bridge_execution_and_history():
    """
    Validar que execucao e historico retornam dados minimos determinísticos.
    """
    connection = make_fake_mt5_rpyc_connection()
    root = connection.root

    result = root.exposed_order_send({"symbol": "EURUSD", "volume": 1.0})
    assert isinstance(result, dict)
    assert "retcode" in result

    positions = root.exposed_positions_get(symbol="EURUSD")
    assert isinstance(positions, list)
    assert len(positions) > 0
    assert positions[0]["symbol"] == "EURUSD"

    assert root.exposed_history_orders_total(1000, 2000) >= 1

    orders = root.exposed_history_orders_get(1000, 2000)
    assert isinstance(orders, list)
    assert len(orders) >= 1
    assert "ticket" in orders[0]

    assert root.exposed_history_deals_total(1000, 2000) >= 1

    deals = root.exposed_history_deals_get(1000, 2000)
    assert isinstance(deals, list)
    assert len(deals) >= 1
    assert "ticket" in deals[0]

def test_fake_bridge_unknown_method_raises_attribute_error():
    """
    Validar que métodos desconhecidos não são aceitos silenciosamente.
    """
    connection = make_fake_mt5_rpyc_connection()
    root = connection.root

    with pytest.raises(AttributeError):
        root.exposed_order_check

    with pytest.raises(AttributeError):
        root.non_exposed_method()

def test_fake_bridge_call_recording():
    """
    Validar que o registro de chamadas funciona.
    """
    connection = make_fake_mt5_rpyc_connection()
    root = connection.root

    root.reset_calls()
    root.exposed_initialize()
    root.exposed_symbol_info("EURUSD", timeout=10)

    assert [call.method for call in root.calls] == [
        "initialize",
        "symbol_info",
    ]

    # Validar argumentos preservados
    assert root.calls[1].args == ("EURUSD",)
    assert root.calls[1].kwargs == {"timeout": 10}

def test_fake_bridge_reset_calls():
    """
    Validar que reset/limpeza de chamadas funciona.
    """
    connection = make_fake_mt5_rpyc_connection()
    root = connection.root

    root.exposed_initialize()
    assert len(root.calls) > 0

    root.reset_calls()
    assert len(root.calls) == 0
