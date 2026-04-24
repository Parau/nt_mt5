import asyncio
import platform
from typing import Dict, Union
from nautilus_trader.common.enums import LogColor

from nautilus_mt5.constants import NO_VALID_ID, TERMINAL_CONNECT_FAIL
from nautilus_mt5.metatrader5 import MetaTrader5, EAClient
from nautilus_mt5.common import BaseMixin
from nautilus_mt5.client.types import (
    ErrorInfo,
    MT5TerminalAccessMode,
    TerminalConnectionMode,
    TerminalConnectionState,
    TerminalPlatform,
)


class MetaTrader5ClientConnectionMixin(BaseMixin):
    """
    Manages the connection to MetaTrader 5 Terminal.
    """

    async def _connect(self) -> None:
        """Establish the connection with Terminal."""
        self._terminal_platform = TerminalPlatform(platform.system().capitalize())
        self.set_conn_state(TerminalConnectionState.CONNECTING)
        
        try:
            await self._initialize_and_connect()
            await self._fetch_terminal_info()
            await self._fetch_account_info()
            self.set_conn_state(TerminalConnectionState.CONNECTED)
            self._log_connection_info()
        except asyncio.CancelledError:
            self._log.info("Connection cancelled.")
            await self._disconnect()
        except Exception as e:
            self._log.error(f"Connection failed: {e}")
            self._handle_connection_error()
            await self._handle_reconnect()

    async def _disconnect(self) -> None:
        """Disconnect from Terminal and clear connection flag."""
        try:
            self._clear_clients()
            self.set_conn_state(TerminalConnectionState.DISCONNECTED)
            if self._is_mt5_connected.is_set():
                self._log.debug("_is_mt5_connected unset by _disconnect.", LogColor.BLUE)
                self._is_mt5_connected.clear()
            self._log.info("Disconnected from MetaTrader 5 Terminal.")
        except Exception as e:
            self._log.error(f"Disconnection failed: {e}")

    async def _handle_reconnect(self) -> None:
        """Attempt to reconnect to Terminal."""
        self._reset()
        self._resume()

    async def _initialize_and_connect(self) -> None:
        """Initialize connection parameters and establish connection."""
        self._mt5_client = await asyncio.to_thread(self._create_mt5_client)
        if self._mt5_client['mt5']:
            self._mt5_client['mt5'].id = self._client_id
            # Initialize MT5 terminal connection via gateway
            success = await asyncio.to_thread(self._mt5_client['mt5'].initialize)
            if not success:
                code, msg = self._mt5_client['mt5'].last_error()
                raise ConnectionError(f"Failed to initialize MT5 terminal via gateway (code={code}, msg={msg}).")
        if self._mt5_client['ea']:
            self._mt5_client['ea'].id = self._client_id

    def _create_mt5_client(self) -> Dict[str, Union[MetaTrader5, EAClient]]:
        """Create and return the appropriate MetaTrader5 client."""
        clients = {'mt5': None, 'ea': None}
        if self._terminal_connection_mode == TerminalConnectionMode.IPC:
            clients['mt5'] = self._create_ipc_client()
        elif self._terminal_connection_mode == TerminalConnectionMode.EA:
            clients['ea'] = self._create_ea_client()
        elif self._terminal_connection_mode == TerminalConnectionMode.EA_IPC:
            clients.update(self._create_ea_ipc_client())
        else:
            raise ValueError(f"Invalid connection mode: {self._terminal_connection_mode}")
        return clients

    def _create_ipc_client(self) -> MetaTrader5:
        """Create an IPC-based MetaTrader5 client."""
        if self._terminal_access == MT5TerminalAccessMode.EXTERNAL_RPYC:
            config = self._mt5_config['rpyc']
            self._log.info(f"Connecting to External RPYC host: {config.host}, port: {config.port}")
            return MetaTrader5(
                host=config.host,
                port=config.port,
                keep_alive=config.keep_alive,
                timeout=config.timeout_secs,
            )

        if self._terminal_platform != TerminalPlatform.WINDOWS:
            config = self._mt5_config['rpyc']
            self._log.info(f"Connecting to RPYC host: {config.host}, port: {config.port}")
            return MetaTrader5(
                host=config.host,
                port=config.port,
                keep_alive=config.keep_alive,
                timeout=config.timeout_secs,
            )
        self._log.info(f"Connecting to IPC Process with client id: {self._client_id}")
        return MetaTrader5()

    def _create_ea_client(self) -> EAClient:
        """Create an EA-based MetaTrader5 client."""
        config = self._mt5_config['ea']
        self._log.info(f"Connecting to EA config: {config} with client id: {self._client_id}")
        return EAClient(config)

    def _create_ea_ipc_client(self) -> Dict[str, Union[MetaTrader5, EAClient]]:
        """Create a client that supports both EA and IPC modes."""
        return {'mt5': self._create_ipc_client(), 'ea': self._create_ea_client()}

    async def _fetch_terminal_info(self) -> None:
        try:
            terminal_info = getattr(self._mt5_client['mt5'], "terminal_info", None)()
            if terminal_info:
                if hasattr(terminal_info, "_asdict"):
                    info = terminal_info._asdict()
                elif hasattr(terminal_info, "__dict__"):
                    info = terminal_info.__dict__
                else:
                    info = dict(terminal_info)

                if not info.get("connected", True):
                    raise ConnectionError("MetaTrader 5 terminal is not connected to a server via gateway.")

                self._terminal_info = {
                    "version": 5,
                    "build": info.get("build", 0),
                    "build_release_date": "Unavailable",
                    "connection_time": "Unavailable"
                }
            else:
                raise ConnectionError("terminal_info indisponível: Failed to fetch terminal info from external_rpyc gateway.")
        except Exception as e:
            if isinstance(e, ConnectionError):
                raise
            self._log.error(f"Error fetching terminal info: {e}")
            raise ConnectionError(f"terminal_info indisponível: Failed to fetch terminal info from external_rpyc gateway: {e}")

    async def _fetch_account_info(self) -> None:
        try:
            account_info = getattr(self._mt5_client['mt5'], "account_info", None)()
            if account_info is None:
                raise ConnectionError("account_info indisponível: Failed to fetch account info from external_rpyc gateway.")
        except Exception as e:
            if isinstance(e, ConnectionError):
                raise
            self._log.error(f"Error fetching account info: {e}")
            raise ConnectionError(f"account_info indisponível: Failed to fetch account info from external_rpyc gateway: {e}")

    def process_connection_closed(self) -> None:
        """Handle terminal disconnection."""
        for future in self._requests.get_futures():
            if not future.done():
                future.set_exception(ConnectionError("Terminal disconnected."))
        if self._is_mt5_connected.is_set():
            self._log.debug("_is_mt5_connected unset by connectionClosed.", LogColor.BLUE)
            self._is_mt5_connected.clear()

    def set_conn_state(self, state: int) -> None:
        """Set the current connection state."""
        self._conn_state = state

    def get_conn_state(self) -> int:
        """Retrieve the current connection state."""
        return self._conn_state

    def _log_connection_info(self) -> None:
        """Log connection details."""
        self._log.info(
            f"Connected to MT5 Terminal (v{self._terminal_info['version']}, "
            f"{self._terminal_info['build']}, {self._terminal_info['build_release_date']}) at "
            f"{self._terminal_info['connection_time']} | Client ID: {self._client_id}."
        )

    def _handle_error(self, id: int, code: int, msg: str) -> None:
        """Handle and log errors."""
        self._log.error(f"Error {code}: {msg}")
        raise ValueError(id, code, msg)

    def _handle_connection_error(self) -> None:
        """Handle connection errors."""
        if self._mt5_client['mt5']:
            code, msg = self._mt5_client['mt5'].last_error()
            if code != MetaTrader5.RES_E_INTERNAL_FAIL_INIT:
                err_code = TERMINAL_CONNECT_FAIL.code
                err_msg = TERMINAL_CONNECT_FAIL.msg
            else:
                error_info = ErrorInfo(code, f"Terminal init failed: {msg}")
                err_code = error_info.code()
                err_msg = error_info.msg()
            self._handle_error(NO_VALID_ID, err_code, err_msg)

    def _clear_clients(self) -> None:
        """Clear client references."""
        self._mt5_client = {'mt5': None, 'ea': None}
