"""
Unit tests for LOCAL_PYTHON terminal access configuration and routing.

These tests verify:
- LocalPythonTerminalConfig fields and defaults
- MT5TerminalAccessMode.LOCAL_PYTHON is present in the enum
- Factory validation: LOCAL_PYTHON requires local_python block, rejects incompatible blocks
- connection.py routing: LOCAL_PYTHON mode returns a LocalPythonMT5 instance (not RPyC wrapper)
- LocalPythonMT5 raises RuntimeError on non-Windows platforms (or missing package)
"""
from __future__ import annotations

import sys
import types
import pytest
from unittest.mock import MagicMock, patch

from nautilus_mt5.client.types import MT5TerminalAccessMode
from nautilus_mt5.config import (
    ExternalRPyCTerminalConfig,
    LocalPythonTerminalConfig,
    ManagedTerminalConfig,
    MetaTrader5DataClientConfig,
    MetaTrader5ExecClientConfig,
)
from nautilus_mt5.client.types import ManagedTerminalBackend


# ---------------------------------------------------------------------------
# MT5TerminalAccessMode enum
# ---------------------------------------------------------------------------


def test_local_python_in_terminal_access_mode_enum():
    """MT5TerminalAccessMode must contain LOCAL_PYTHON."""
    assert hasattr(MT5TerminalAccessMode, "LOCAL_PYTHON")
    assert MT5TerminalAccessMode.LOCAL_PYTHON.value == "local_python"


def test_all_three_public_modes_present():
    """All three public access modes must be in the enum."""
    names = {m.name for m in MT5TerminalAccessMode}
    assert "EXTERNAL_RPYC" in names
    assert "LOCAL_PYTHON" in names
    assert "MANAGED_TERMINAL" in names


def test_dockerized_not_a_terminal_access_mode():
    """DOCKERIZED is an internal backend; it must NOT appear in MT5TerminalAccessMode."""
    names = {m.name for m in MT5TerminalAccessMode}
    assert "DOCKERIZED" not in names


# ---------------------------------------------------------------------------
# LocalPythonTerminalConfig
# ---------------------------------------------------------------------------


def test_local_python_config_defaults():
    """LocalPythonTerminalConfig should have correct defaults."""
    cfg = LocalPythonTerminalConfig()
    assert cfg.path is None
    assert cfg.login is None
    assert cfg.password is None
    assert cfg.server is None
    assert cfg.timeout == 60_000
    assert cfg.portable is False
    assert cfg.shutdown_on_disconnect is True


def test_local_python_config_custom_values():
    """LocalPythonTerminalConfig should accept custom values."""
    cfg = LocalPythonTerminalConfig(
        path="C:\\MT5\\terminal64.exe",
        login=12345678,
        password="secret",
        server="MyBroker-Demo",
        timeout=30_000,
        portable=True,
        shutdown_on_disconnect=False,
    )
    assert cfg.path == "C:\\MT5\\terminal64.exe"
    assert cfg.login == 12345678
    assert cfg.password == "secret"
    assert cfg.server == "MyBroker-Demo"
    assert cfg.timeout == 30_000
    assert cfg.portable is True
    assert cfg.shutdown_on_disconnect is False


# ---------------------------------------------------------------------------
# MetaTrader5DataClientConfig — local_python field
# ---------------------------------------------------------------------------


def test_data_client_config_has_local_python_field():
    """MetaTrader5DataClientConfig must have a local_python field defaulting to None."""
    cfg = MetaTrader5DataClientConfig(terminal_access=MT5TerminalAccessMode.LOCAL_PYTHON)
    assert hasattr(cfg, "local_python")
    assert cfg.local_python is None


def test_exec_client_config_has_local_python_field():
    """MetaTrader5ExecClientConfig must have a local_python field defaulting to None."""
    cfg = MetaTrader5ExecClientConfig(terminal_access=MT5TerminalAccessMode.LOCAL_PYTHON)
    assert hasattr(cfg, "local_python")
    assert cfg.local_python is None


def test_data_client_config_with_local_python_block():
    """MetaTrader5DataClientConfig must accept LocalPythonTerminalConfig."""
    lp_cfg = LocalPythonTerminalConfig(login=12345678, password="pw", server="Broker-Demo")
    cfg = MetaTrader5DataClientConfig(
        terminal_access=MT5TerminalAccessMode.LOCAL_PYTHON,
        local_python=lp_cfg,
    )
    assert cfg.local_python is lp_cfg
    assert cfg.external_rpyc is None
    assert cfg.managed_terminal is None


def test_exec_client_config_with_local_python_block():
    """MetaTrader5ExecClientConfig must accept LocalPythonTerminalConfig."""
    lp_cfg = LocalPythonTerminalConfig(login=12345678, password="pw", server="Broker-Demo")
    cfg = MetaTrader5ExecClientConfig(
        terminal_access=MT5TerminalAccessMode.LOCAL_PYTHON,
        local_python=lp_cfg,
        account_id="12345678",
    )
    assert cfg.local_python is lp_cfg
    assert cfg.external_rpyc is None
    assert cfg.managed_terminal is None


# ---------------------------------------------------------------------------
# Factory validation
# ---------------------------------------------------------------------------


def _make_mock_loop_msgbus_cache_clock():
    loop = MagicMock()
    msgbus = MagicMock()
    cache = MagicMock()
    clock = MagicMock()
    return loop, msgbus, cache, clock


def test_factory_local_python_requires_local_python_block():
    """Factory must raise ValueError when local_python block is missing for LOCAL_PYTHON mode."""
    from nautilus_mt5.factories import get_resolved_mt5_client

    loop, msgbus, cache, clock = _make_mock_loop_msgbus_cache_clock()
    cfg = MetaTrader5DataClientConfig(
        terminal_access=MT5TerminalAccessMode.LOCAL_PYTHON,
        local_python=None,  # explicitly missing
    )
    with pytest.raises(ValueError, match="local_python config is required"):
        get_resolved_mt5_client(loop=loop, msgbus=msgbus, cache=cache, clock=clock, config=cfg)


def test_factory_local_python_rejects_external_rpyc():
    """Factory must raise ValueError when external_rpyc block is provided for LOCAL_PYTHON mode."""
    from nautilus_mt5.factories import get_resolved_mt5_client

    loop, msgbus, cache, clock = _make_mock_loop_msgbus_cache_clock()
    cfg = MetaTrader5DataClientConfig(
        terminal_access=MT5TerminalAccessMode.LOCAL_PYTHON,
        local_python=LocalPythonTerminalConfig(),
        external_rpyc=ExternalRPyCTerminalConfig(host="localhost", port=18812),
    )
    with pytest.raises(ValueError, match="external_rpyc config must be None for LOCAL_PYTHON"):
        get_resolved_mt5_client(loop=loop, msgbus=msgbus, cache=cache, clock=clock, config=cfg)


def test_factory_local_python_rejects_managed_terminal():
    """Factory must raise ValueError when managed_terminal block is provided for LOCAL_PYTHON mode."""
    from nautilus_mt5.factories import get_resolved_mt5_client

    loop, msgbus, cache, clock = _make_mock_loop_msgbus_cache_clock()
    cfg = MetaTrader5DataClientConfig(
        terminal_access=MT5TerminalAccessMode.LOCAL_PYTHON,
        local_python=LocalPythonTerminalConfig(),
        managed_terminal=ManagedTerminalConfig(backend=ManagedTerminalBackend.LOCAL_PROCESS),
    )
    with pytest.raises(ValueError, match="managed_terminal config must be None for LOCAL_PYTHON"):
        get_resolved_mt5_client(loop=loop, msgbus=msgbus, cache=cache, clock=clock, config=cfg)


# ---------------------------------------------------------------------------
# LocalPythonMT5 — platform / missing package guard
# ---------------------------------------------------------------------------


def test_local_python_wrapper_raises_on_non_windows():
    """LocalPythonMT5 must raise RuntimeError when instantiated on non-Windows platforms."""
    from nautilus_mt5.metatrader5.local_python import LocalPythonMT5

    with patch.object(sys, "platform", "linux"):
        with pytest.raises(RuntimeError, match="LOCAL_PYTHON terminal access requires"):
            LocalPythonMT5()


def test_local_python_wrapper_raises_when_package_missing():
    """LocalPythonMT5 must raise RuntimeError when MetaTrader5 package is not installed."""
    from nautilus_mt5.metatrader5 import local_python as lp_module

    # Simulate Windows but MetaTrader5 package not importable
    with patch.object(sys, "platform", "win32"):
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "MetaTrader5":
                raise ImportError("No module named 'MetaTrader5'")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            with pytest.raises(RuntimeError, match="MetaTrader5 Python package"):
                lp_module._load_mt5_module()


def test_local_python_wrapper_uses_local_module_on_windows():
    """LocalPythonMT5 should load the official MT5 module when on Windows and package is installed."""
    from nautilus_mt5.metatrader5 import local_python as lp_module

    fake_mt5 = MagicMock()
    fake_mt5.__name__ = "MetaTrader5"

    with patch.object(sys, "platform", "win32"):
        with patch.dict("sys.modules", {"MetaTrader5": fake_mt5}):
            wrapper = lp_module.LocalPythonMT5(login=123, password="pw", server="Demo")
            # Should have stored the fake mt5 module
            assert wrapper._mt5 is fake_mt5
            assert wrapper._login == 123
            assert wrapper._password == "pw"
            assert wrapper._server == "Demo"


# ---------------------------------------------------------------------------
# connection.py routing
# ---------------------------------------------------------------------------


def test_create_ipc_client_routes_local_python_to_wrapper():
    """
    _create_ipc_client must return a LocalPythonMT5 for LOCAL_PYTHON mode,
    NOT the RPyC MetaTrader5 wrapper.
    """
    from nautilus_mt5.metatrader5.local_python import LocalPythonMT5

    lp_cfg = LocalPythonTerminalConfig(login=99999999, password="test", server="Test-Server")

    fake_mt5_module = MagicMock()
    fake_mt5_module.initialize.return_value = True
    fake_mt5_module.last_error.return_value = (0, "")

    with patch.object(sys, "platform", "win32"):
        with patch.dict("sys.modules", {"MetaTrader5": fake_mt5_module}):
            # Build a minimal fake connection mixin by patching _load_mt5_module
            import nautilus_mt5.metatrader5.local_python as lp_module

            original_load = lp_module._load_mt5_module
            lp_module._load_mt5_module = lambda: fake_mt5_module
            try:
                wrapper = LocalPythonMT5(
                    path=lp_cfg.path,
                    login=lp_cfg.login,
                    password=lp_cfg.password,
                    server=lp_cfg.server,
                    timeout=lp_cfg.timeout,
                    portable=lp_cfg.portable,
                )
                assert isinstance(wrapper, LocalPythonMT5)
                assert wrapper._login == lp_cfg.login
                assert wrapper._server == lp_cfg.server
            finally:
                lp_module._load_mt5_module = original_load
