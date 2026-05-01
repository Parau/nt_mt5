import ast
from pathlib import Path
import pytest

SOURCE_PATH = Path("nautilus_mt5/metatrader5/MetaTrader5.py")

def get_exposed_positions_get_usage():
    if not SOURCE_PATH.exists():
        pytest.fail(f"Source file {SOURCE_PATH} not found")

    tree = ast.parse(SOURCE_PATH.read_text(encoding="utf-8"))

    violations = []

    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.current_method = None
            self.violations = []

        def visit_FunctionDef(self, node):
            old_method = self.current_method
            self.current_method = node.name
            self.generic_visit(node)
            self.current_method = old_method

        def visit_Attribute(self, node):
            if node.attr == "exposed_positions_get":
                if self.current_method != "positions_get":
                    self.violations.append(self.current_method)
            self.generic_visit(node)

    visitor = Visitor()
    visitor.visit(tree)
    return visitor.violations

def test_only_positions_get_uses_exposed_positions_get():
    """
    AST Audit: Ensure exposed_positions_get is ONLY used within positions_get.
    """
    violations = get_exposed_positions_get_usage()

    assert not violations, (
        f"exposed_positions_get must only be used by positions_get, "
        f"but was found in: {', '.join(sorted(set(violations)))}"
    )

def test_surface_coverage():
    """
    Ensure the audit covers at least the minimum required surface area.
    """
    tree = ast.parse(SOURCE_PATH.read_text(encoding="utf-8"))

    methods = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            methods.append(node.name)

    required_surface = [
        "initialize", "login", "last_error", "version", "shutdown",
        "get_constant", "terminal_info", "account_info", "symbols_get",
        "symbol_info", "symbol_info_tick", "symbol_select",
        "copy_rates_from_pos", "copy_ticks_range", "copy_ticks_from",
        "order_send", "positions_get", "history_orders_total",
        "history_orders_get", "history_deals_total", "history_deals_get"
    ]

    missing = [m for m in required_surface if m not in methods]
    assert not missing, f"Missing methods in MetaTrader5 wrapper: {missing}"

from unittest.mock import MagicMock, patch
from nautilus_mt5.metatrader5.MetaTrader5 import MetaTrader5

@pytest.fixture
def mock_rpyc_conn():
    with patch("rpyc.connect") as mock_connect:
        mock_conn = MagicMock()
        # Mock exposed_positions_get to raise error if called unexpectedly
        mock_conn.root.exposed_positions_get = MagicMock(side_effect=AssertionError("Unexpected call to exposed_positions_get"))

        # Other methods should not raise by default
        mock_conn.root.exposed_initialize = MagicMock()
        mock_conn.root.exposed_login = MagicMock()
        mock_conn.root.exposed_market_book_add = MagicMock()
        mock_conn.root.exposed_order_send = MagicMock()
        mock_conn.root.exposed_history_orders_get = MagicMock()

        mock_connect.return_value = mock_conn
        yield mock_conn

def test_behavioral_no_fallback(mock_rpyc_conn):
    """
    Behavioral Test: Ensure non-position methods do not call exposed_positions_get.
    """
    mt5 = MetaTrader5()

    # These should NOT call exposed_positions_get
    mt5.initialize()
    mt5.login(123)
    mt5.market_book_add("EURUSD")
    mt5.order_send({"action": 1})
    mt5.history_orders_get(1000, 2000)

    # This SHOULD call exposed_positions_get, so we need to reset the side_effect
    mock_rpyc_conn.root.exposed_positions_get.side_effect = None
    mock_rpyc_conn.root.exposed_positions_get.return_value = (1, 2, 3)

    res = mt5.positions_get()
    assert res == (1, 2, 3)
    mock_rpyc_conn.root.exposed_positions_get.assert_called_once()
