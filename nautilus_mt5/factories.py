import asyncio
import os

from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock
from nautilus_trader.common.component import MessageBus
from nautilus_trader.core.correctness import PyCondition
from nautilus_trader.live.factories import LiveDataClientFactory
from nautilus_trader.live.factories import LiveExecClientFactory
from nautilus_trader.model.identifiers import AccountId

from nautilus_mt5.client import MetaTrader5Client
from nautilus_mt5.client.types import (
    MT5TerminalAccessMode,
    TerminalConnectionMode,
)
from nautilus_mt5.constants import MT5_VENUE
from nautilus_mt5.config import (
    DockerizedMT5TerminalConfig,
    ExternalRPyCTerminalConfig,
    ManagedTerminalConfig,
    MetaTrader5DataClientConfig,
    MetaTrader5ExecClientConfig,
    MetaTrader5InstrumentProviderConfig,
    RpycConnectionConfig,
    EAConnectionConfig,
)
from nautilus_mt5.data import MetaTrader5DataClient
from nautilus_mt5.execution import MetaTrader5ExecutionClient
from nautilus_mt5.providers import MetaTrader5InstrumentProvider

MT5_CLIENTS: dict[tuple, MetaTrader5Client] = {}

def get_resolved_mt5_client(
    loop: asyncio.AbstractEventLoop,
    msgbus: MessageBus,
    cache: Cache,
    clock: LiveClock,
    config: MetaTrader5DataClientConfig | MetaTrader5ExecClientConfig,
) -> MetaTrader5Client:
    """
    Retrieve or create a cached MetaTrader5Client using the provided configuration.

    Parameters
    ----------
    loop: asyncio.AbstractEventLoop
        The event loop for the client.
    msgbus: MessageBus
        The message bus for the client.
    cache: Cache
        The cache for the client.
    clock: LiveClock
        The clock for the client.
    config: MetaTrader5DataClientConfig | MetaTrader5ExecClientConfig
        The client configuration.

    Returns
    -------
    MetaTrader5Client

    """
    terminal_access = config.terminal_access
    client_id = config.client_id
    connection_mode = config.mode
    ea_config = config.ea_config or EAConnectionConfig()

    rpyc_host: str | None = None
    rpyc_port: int | None = None
    rpyc_keep_alive: bool = False
    managed_backend: str | None = None

    if terminal_access == MT5TerminalAccessMode.EXTERNAL_RPYC:
        if config.managed_terminal is not None:
            raise ValueError(
                "managed_terminal config must be None for EXTERNAL_RPYC terminal access."
            )
        external_rpyc = config.external_rpyc
        if external_rpyc is None:
            # Fallback for transition if old rpyc_config exists
            if config.rpyc_config:
                rpyc_host = config.rpyc_config.host
                rpyc_port = config.rpyc_config.port
                rpyc_keep_alive = config.rpyc_config.keep_alive
            else:
                raise ValueError(
                    "external_rpyc config is required for EXTERNAL_RPYC terminal access."
                )
        else:
            rpyc_host = external_rpyc.host
            rpyc_port = external_rpyc.port
            rpyc_keep_alive = external_rpyc.keep_alive

    elif terminal_access == MT5TerminalAccessMode.MANAGED_TERMINAL:
        if config.external_rpyc is not None:
            raise ValueError(
                "external_rpyc config must be None for MANAGED_TERMINAL terminal access."
            )
        managed_terminal = config.managed_terminal
        if managed_terminal is None:
            raise ValueError(
                "managed_terminal config is required for MANAGED_TERMINAL terminal access."
            )
        else:
            # For now, we only have placeholder for managed terminal
            # If backend is DOCKERIZED, we could potentially use the old logic if available
            raise RuntimeError(
                f"MANAGED_TERMINAL access mode was recognized, but the backend '{managed_terminal.backend}' is not yet implemented in this phase."
            )
    else:
        # Legacy/Default handling if terminal_access is somehow not set
        rpyc_config = config.rpyc_config or RpycConnectionConfig()
        rpyc_host = rpyc_config.host
        rpyc_port = rpyc_config.port
        rpyc_keep_alive = rpyc_config.keep_alive

    # Re-wrap as RpycConnectionConfig for internal use
    resolved_rpyc_config = RpycConnectionConfig(
        host=rpyc_host,
        port=rpyc_port,
        keep_alive=rpyc_keep_alive,
    )

    client_key = (
        terminal_access,
        connection_mode,
        client_id,
        rpyc_host,
        rpyc_port,
        managed_backend,
        ea_config.host,
        ea_config.rest_port,
        ea_config.stream_port,
    )

    if client_key not in MT5_CLIENTS:
        client = MetaTrader5Client(
            loop=loop,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            connection_mode=connection_mode,
            mt5_config={
                "rpyc": resolved_rpyc_config,
                "ea": ea_config,
            },
            client_id=client_id,
            terminal_access=terminal_access,
        )
        client.start()
        MT5_CLIENTS[client_key] = client
    return MT5_CLIENTS[client_key]


def get_cached_mt5_instrument_provider(
    client: MetaTrader5Client,
    config: MetaTrader5InstrumentProviderConfig,
) -> MetaTrader5InstrumentProvider:
    """
    Cache and return a MetaTrader5InstrumentProvider.

    If a cached provider already exists, then that cached provider will be returned.

    Parameters
    ----------
    client : MetaTrader5Client
        The client for the instrument provider.
    config: MetaTrader5InstrumentProviderConfig
        The instrument provider config.

    Returns
    -------
    MetaTrader5InstrumentProvider

    """
    return MetaTrader5InstrumentProvider(client=client, config=config)


class MT5LiveDataClientFactory(LiveDataClientFactory):
    """
    Factory for creating MetaTrader5 live data clients.
    """

    @staticmethod
    def create(
        loop: asyncio.AbstractEventLoop,
        name: str,
        config: MetaTrader5DataClientConfig,
        msgbus: MessageBus,
        cache: Cache,
        clock: LiveClock,
    ) -> MetaTrader5DataClient:
        """
        Create a new MetaTrader5 data client.

        Parameters
        ----------
        loop : asyncio.AbstractEventLoop
            The event loop for the client.
        name : str
            The custom client ID.
        config : MetaTrader5DataClientConfig
            The configuration for the client.
        msgbus : MessageBus
            The message bus for the client.
        cache : Cache
            The cache for the client.
        clock : LiveClock
            The clock for the client.

        Returns
        -------
        MetaTrader5DataClient

        """
        client = get_resolved_mt5_client(
            loop=loop,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            config=config,
        )

        # Get instrument provider singleton
        provider = get_cached_mt5_instrument_provider(
            client=client,
            config=config.instrument_provider,
        )

        # Create client
        data_client = MetaTrader5DataClient(
            loop=loop,
            client=client,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            instrument_provider=provider,
            mt5_client_id=config.client_id,
            config=config,
            name=name,
        )
        return data_client


class MT5LiveExecClientFactory(LiveExecClientFactory):
    """
    Factory for creating MetaTrader5 live execution clients.
    """

    @staticmethod
    def create(
        loop: asyncio.AbstractEventLoop,
        name: str,
        config: MetaTrader5ExecClientConfig,
        msgbus: MessageBus,
        cache: Cache,
        clock: LiveClock,
    ) -> MetaTrader5ExecutionClient:
        """
        Create a new MetaTrader5 execution client.

        Parameters
        ----------
        loop : asyncio.AbstractEventLoop
            The event loop for the client.
        name : str
            The custom client ID.
        config : MetaTrader5ExecClientConfig
            The configuration for the client.
        msgbus : MessageBus
            The message bus for the client.
        cache : Cache
            The cache for the client.
        clock : LiveClock
            The clock for the client.

        Returns
        -------
        MetaTrader5ExecutionClient

        """
        client = get_resolved_mt5_client(
            loop=loop,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            config=config,
        )

        # Get instrument provider singleton
        provider = get_cached_mt5_instrument_provider(
            client=client,
            config=config.instrument_provider,
        )

        # Set account ID
        mt5_account = config.account_id or os.environ.get("MT5_ACCOUNT_NUMBER")
        assert (
            mt5_account
        ), f"Must pass `{config.__class__.__name__}.account_id` or set `MT5_ACCOUNT_NUMBER` env var."

        account_id = AccountId(f"{name or MT5_VENUE.value}-{mt5_account}")

        # Create client
        exec_client = MetaTrader5ExecutionClient(
            loop=loop,
            client=client,
            account_id=account_id,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            instrument_provider=provider,
            config=config,
            name=name,
        )
        return exec_client
