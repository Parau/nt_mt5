"""
LocalPythonMT5 — thin wrapper over the official MetaTrader5 Python package.

This module provides LOCAL_PYTHON terminal access: direct calls to the MetaTrader5
package installed on the local machine (Windows only), without any RPyC layer.

Usage
-----
The adapter creates a LocalPythonMT5 instance when terminal_access=LOCAL_PYTHON.
It exposes the same surface as the RPyC-based MetaTrader5 wrapper so that
MetaTrader5Client can use either interchangeably.

Compatibility
-------------
- Expected to work only on Windows where the official MetaTrader5 package is installed.
- Raises RuntimeError with a clear message on incompatible platforms or missing package.
- Does NOT open RPyC connections.
"""
from __future__ import annotations

import sys
from typing import Any


def _load_mt5_module() -> Any:
    """
    Import and return the official MetaTrader5 module.

    Raises
    ------
    RuntimeError
        When the platform is not Windows or the MetaTrader5 package is not installed.
    """
    if sys.platform != "win32":
        raise RuntimeError(
            "LOCAL_PYTHON terminal access requires the official MetaTrader5 Python package, "
            f"which is only available on Windows. Current platform: {sys.platform}. "
            "Use EXTERNAL_RPYC to connect to an MT5 terminal from a non-Windows host."
        )
    try:
        import MetaTrader5 as _mt5  # noqa: PLC0415
        return _mt5
    except ImportError as exc:
        raise RuntimeError(
            "LOCAL_PYTHON terminal access requires the MetaTrader5 Python package. "
            "Install it with: pip install MetaTrader5\n"
            "The package is only available on Windows."
        ) from exc


class LocalPythonMT5:
    """
    Thin wrapper over the official MetaTrader5 Python package for LOCAL_PYTHON access.

    Exposes the same minimum surface used by the adapter as the RPyC-based MetaTrader5
    wrapper, so MetaTrader5Client can use either transparently.

    The official MetaTrader5 module is imported lazily (on first instantiation) to
    avoid import errors on Linux/CI environments where the package is not installed.

    Parameters
    ----------
    path : str | None
        Optional path to the terminal executable. Passed to MT5.initialize().
    login : int | None
        Optional account number for auto-login.
    password : str | None
        Optional password for auto-login.
    server : str | None
        Optional server name for auto-login.
    timeout : int
        Timeout in milliseconds for initialize(). Default 60000.
    portable : bool
        Launch terminal in portable mode. Default False.
    """

    def __init__(
        self,
        path: str | None = None,
        login: int | None = None,
        password: str | None = None,
        server: str | None = None,
        timeout: int = 60_000,
        portable: bool = False,
    ) -> None:
        self._mt5 = _load_mt5_module()
        self._path = path
        self._login = login
        self._password = password
        self._server = server
        self._timeout = timeout
        self._portable = portable
        # id attribute mirrors the RPyC wrapper convention used by MetaTrader5Client
        self.id: int = 1

    # ------------------------------------------------------------------
    # Session
    # ------------------------------------------------------------------

    def initialize(self, *args: Any, **kwargs: Any) -> bool:
        """
        Initialize the MetaTrader5 terminal connection.

        If path/login/password/server/timeout/portable were provided at construction
        time, they are used as defaults (can be overridden by explicit kwargs).
        """
        # Build kwargs from stored config, allowing caller overrides
        init_kwargs: dict[str, Any] = {}
        if self._path is not None:
            init_kwargs["path"] = self._path
        if self._login is not None:
            init_kwargs["login"] = self._login
        if self._password is not None:
            init_kwargs["password"] = self._password
        if self._server is not None:
            init_kwargs["server"] = self._server
        init_kwargs["timeout"] = self._timeout
        init_kwargs["portable"] = self._portable
        # Explicit caller kwargs win
        init_kwargs.update(kwargs)
        if args:
            return self._mt5.initialize(*args, **init_kwargs)
        return self._mt5.initialize(**init_kwargs)

    def login(self, login: int, password: str = "", server: str = "", timeout: int = 60_000) -> bool:
        return self._mt5.login(login, password=password, server=server, timeout=timeout)

    def shutdown(self) -> None:
        self._mt5.shutdown()

    def last_error(self) -> tuple[int, str]:
        return self._mt5.last_error()

    def version(self) -> tuple[int, int, str] | None:
        return self._mt5.version()

    # ------------------------------------------------------------------
    # Terminal and account state
    # ------------------------------------------------------------------

    def terminal_info(self) -> Any:
        return self._mt5.terminal_info()

    def account_info(self) -> Any:
        return self._mt5.account_info()

    # ------------------------------------------------------------------
    # Symbol management
    # ------------------------------------------------------------------

    def symbols_get(self, group: str = "") -> Any:
        if group:
            return self._mt5.symbols_get(group)
        return self._mt5.symbols_get()

    def symbol_info(self, symbol: str) -> Any:
        return self._mt5.symbol_info(symbol)

    def symbol_info_tick(self, symbol: str) -> Any:
        return self._mt5.symbol_info_tick(symbol)

    def symbol_select(self, symbol: str, enable: bool = True) -> bool:
        return self._mt5.symbol_select(symbol, enable)

    # ------------------------------------------------------------------
    # Market data and history
    # ------------------------------------------------------------------

    def copy_rates_from_pos(self, symbol: str, timeframe: int, start_pos: int, count: int) -> Any:
        return self._mt5.copy_rates_from_pos(symbol, timeframe, start_pos, count)

    def copy_ticks_range(self, symbol: str, date_from: Any, date_to: Any, flags: int) -> Any:
        return self._mt5.copy_ticks_range(symbol, date_from, date_to, flags)

    def copy_ticks_from(self, symbol: str, date_from: Any, count: int, flags: int) -> Any:
        return self._mt5.copy_ticks_from(symbol, date_from, count, flags)

    # ------------------------------------------------------------------
    # Execution and operational history
    # ------------------------------------------------------------------

    def order_send(self, request: dict) -> Any:
        return self._mt5.order_send(request)

    def orders_get(self, symbol: str = "", group: str = "", ticket: int = 0) -> Any:
        kwargs: dict[str, Any] = {}
        if symbol:
            kwargs["symbol"] = symbol
        if group:
            kwargs["group"] = group
        if ticket:
            kwargs["ticket"] = ticket
        return self._mt5.orders_get(**kwargs) if kwargs else self._mt5.orders_get()

    def positions_get(self, symbol: str = "", group: str = "", ticket: int = 0) -> Any:
        kwargs: dict[str, Any] = {}
        if symbol:
            kwargs["symbol"] = symbol
        if group:
            kwargs["group"] = group
        if ticket:
            kwargs["ticket"] = ticket
        return self._mt5.positions_get(**kwargs) if kwargs else self._mt5.positions_get()

    def history_orders_total(self, date_from: Any, date_to: Any) -> int:
        return self._mt5.history_orders_total(date_from, date_to)

    def history_orders_get(self, date_from: Any, date_to: Any, **kwargs: Any) -> Any:
        return self._mt5.history_orders_get(date_from, date_to, **kwargs)

    def history_deals_total(self, date_from: Any, date_to: Any) -> int:
        return self._mt5.history_deals_total(date_from, date_to)

    def history_deals_get(self, date_from: Any, date_to: Any, **kwargs: Any) -> Any:
        return self._mt5.history_deals_get(date_from, date_to, **kwargs)

    # ------------------------------------------------------------------
    # Constants helper (mirrors RPyC wrapper convention)
    # ------------------------------------------------------------------

    def get_constant(self, name: str) -> Any:
        """Return an MT5 constant by name (e.g. 'TIMEFRAME_M1')."""
        return getattr(self._mt5, name, None)
