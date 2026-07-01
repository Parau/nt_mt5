"""
Provides an API integration for the MetaTrader 5 Trading Platform.
"""

from nautilus_mt5.config import (
    DockerizedMT5TerminalConfig,
    ExternalRPyCTerminalConfig,
    FeedGatewayConfig,
    LocalPythonTerminalConfig,
    ManagedTerminalConfig,
    MetaTrader5DataClientConfig,
    MetaTrader5ExecClientConfig,
    MetaTrader5InstrumentProviderConfig,
)
from nautilus_mt5.data import MetaTrader5DataClient
from nautilus_mt5.execution import MetaTrader5ExecutionClient
from nautilus_mt5.factories import MT5LiveDataClientFactory, MT5LiveExecClientFactory
from nautilus_mt5.providers import MetaTrader5InstrumentProvider
from nautilus_mt5.venue_profile import (
    AMP_US_PROFILE,
    CapabilityStatus,
    CalcModeCapability,
    VenueProfile,
    TICKMILL_DEMO_PROFILE,
    XP_B3_PROFILE,
    resolve_venue_profile,
)

__all__ = [
    "CapabilityStatus",
    "CalcModeCapability",
    "DockerizedMT5TerminalConfig",
    "ExternalRPyCTerminalConfig",
    "FeedGatewayConfig",
    "LocalPythonTerminalConfig",
    "ManagedTerminalConfig",
    "MetaTrader5DataClient",
    "MetaTrader5DataClientConfig",
    "MetaTrader5ExecClientConfig",
    "MetaTrader5ExecutionClient",
    "MetaTrader5InstrumentProvider",
    "MetaTrader5InstrumentProviderConfig",
    "MT5LiveDataClientFactory",
    "MT5LiveExecClientFactory",
    "AMP_US_PROFILE",
    "TICKMILL_DEMO_PROFILE",
    "XP_B3_PROFILE",
    "VenueProfile",
    "resolve_venue_profile",
]
