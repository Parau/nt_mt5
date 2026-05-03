"""
venue_profile.py
================
VenueProfile: broker-specific capability declarations for the MT5 adapter.

Each profile maps MT5 ``trade_calc_mode`` values to:
- The Nautilus instrument type to emit when parsing.
- The capability status of each data operation (quote ticks, trade ticks, bars).

Capability statuses follow an epistemic scale::

    ASSUMED   — declared by convention, not yet observed in real data.
    OBSERVED  — seen in a live session but not yet in automated tests.
    TESTED    — covered by a deterministic automated test.
    CERTIFIED — tested + validated against a live MT5 terminal.
    UNSUPPORTED — the adapter explicitly does not support this operation.

Usage::

    from nautilus_mt5 import TICKMILL_DEMO_PROFILE
    config = MetaTrader5DataClientConfig(
        ...,
        venue_profile=TICKMILL_DEMO_PROFILE,
    )

"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Type

from nautilus_trader.model.instruments import (
    Cfd,
    CurrencyPair,
    Equity,
    FuturesContract,
    Instrument,
)


class CapabilityStatus(str, Enum):
    """Epistemic confidence level for a data capability on a specific broker/mode combination."""

    ASSUMED = "assumed"
    OBSERVED = "observed"
    TESTED = "tested"
    CERTIFIED = "certified"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class CalcModeCapability:
    """
    Declares the Nautilus instrument type and data capability statuses for a
    specific MT5 ``trade_calc_mode`` value within a VenueProfile.

    Parameters
    ----------
    nautilus_instrument_type : Type[Instrument]
        The Nautilus instrument class to emit when parsing this calc mode.
    quote_ticks : CapabilityStatus
        Status of QuoteTick support (subscribe + request).
    trade_ticks : CapabilityStatus
        Status of TradeTick support (subscribe + request).
    bars : CapabilityStatus
        Status of Bar support (subscribe + request).
    notes : str, optional
        Free-text notes, e.g. live observations or known caveats.
    """

    nautilus_instrument_type: Type[Instrument]
    quote_ticks: CapabilityStatus
    trade_ticks: CapabilityStatus
    bars: CapabilityStatus
    notes: Optional[str] = None


@dataclass(frozen=True)
class VenueProfile:
    """
    Broker-specific capability profile for the MT5 adapter.

    Maps MT5 ``trade_calc_mode`` integer constants to ``CalcModeCapability``
    declarations.  The adapter consults the profile at two points:

    1. **Instrument parsing** (``parse_instrument``): the profile determines
       which Nautilus instrument type to create (``CurrencyPair``, ``Cfd``, etc.).
    2. **Data operations** (``_subscribe_trade_ticks``, ``_request_trade_ticks``,
       etc.): the profile gates whether the operation is allowed to proceed.

    Parameters
    ----------
    name : str
        Human-readable profile name, used in log messages.
    capabilities : dict[int, CalcModeCapability]
        Mapping of ``trade_calc_mode`` → capability declaration.
    strict : bool, optional
        When ``True``, treat ``ASSUMED`` and ``OBSERVED`` statuses as errors
        (raise ``ValueError`` instead of just logging a warning).
        Default is ``False``.
    """

    name: str
    capabilities: dict  # dict[int, CalcModeCapability] — dict avoids hash issues
    strict: bool = False

    def get_capability(self, calc_mode: int) -> CalcModeCapability:
        """
        Return the ``CalcModeCapability`` for *calc_mode*.

        Raises
        ------
        ValueError
            If *calc_mode* is not declared in this profile.
        """
        cap = self.capabilities.get(calc_mode)
        if cap is None:
            known = sorted(self.capabilities.keys())
            raise ValueError(
                f"MT5 trade_calc_mode={calc_mode} is not declared in VenueProfile "
                f"'{self.name}'. Known modes: {known}. "
                "Add this calc_mode to the profile or use a compatible profile."
            )
        return cap

    def check_capability(self, calc_mode: int, operation: str) -> CapabilityStatus:
        """
        Return the ``CapabilityStatus`` for *operation* on *calc_mode*.

        In ``strict`` mode, raises ``ValueError`` if the status is ``ASSUMED``
        or ``OBSERVED`` (i.e. not yet properly verified).

        Parameters
        ----------
        calc_mode : int
            The MT5 ``trade_calc_mode`` value from the instrument.
        operation : str
            One of ``"quote_ticks"``, ``"trade_ticks"``, ``"bars"``.

        Returns
        -------
        CapabilityStatus

        Raises
        ------
        ValueError
            If *calc_mode* is not declared, or if ``strict=True`` and the
            status is ``ASSUMED`` or ``OBSERVED``.
        """
        cap = self.get_capability(calc_mode)
        status: CapabilityStatus = getattr(cap, operation)
        if self.strict and status in (CapabilityStatus.ASSUMED, CapabilityStatus.OBSERVED):
            raise ValueError(
                f"VenueProfile '{self.name}': '{operation}' for trade_calc_mode={calc_mode} "
                f"has status={status.value!r} — strict mode requires TESTED or CERTIFIED. "
                "Update the profile status after verification."
            )
        return status


# ---------------------------------------------------------------------------
# MT5 trade_calc_mode constants
# Source: MetaTrader5 MQL5 ENUM_SYMBOL_CALC_MODE
# ---------------------------------------------------------------------------

SYMBOL_CALC_MODE_FOREX = 0
"""Forex mode (leverage, separate bid/ask — no reliable last price)."""

SYMBOL_CALC_MODE_FUTURES = 1
"""Futures mode (OTC, contract multiplier)."""

SYMBOL_CALC_MODE_CFD = 2
"""CFD mode (generic)."""

SYMBOL_CALC_MODE_CFDINDEX = 3
"""CFD on an index."""

SYMBOL_CALC_MODE_CFDLEVERAGE = 4
"""CFD with leverage multiplier."""

SYMBOL_CALC_MODE_FOREX_NO_LEVERAGE = 5
"""Forex without leverage."""

SYMBOL_CALC_MODE_EXCH_STOCKS = 6
"""Exchange stocks with real last price."""

SYMBOL_CALC_MODE_EXCH_FUTURES = 7
"""Exchange futures with real last price (B3 mini-contracts: WIN, WDO)."""

SYMBOL_CALC_MODE_EXCH_FUTURES_FORTS = 8
"""Moscow Exchange (FORTS) futures."""

SYMBOL_CALC_MODE_EXCH_BONDS = 9
"""Exchange bonds."""

SYMBOL_CALC_MODE_EXCH_STOCKS_MOEX = 10
"""Moscow Exchange stocks."""

SYMBOL_CALC_MODE_EXCH_BONDS_MOEX = 11
"""Moscow Exchange bonds."""


# ---------------------------------------------------------------------------
# Pre-built profiles
# ---------------------------------------------------------------------------

TICKMILL_DEMO_PROFILE = VenueProfile(
    name="tickmill-demo",
    capabilities={
        SYMBOL_CALC_MODE_FOREX: CalcModeCapability(
            nautilus_instrument_type=CurrencyPair,
            quote_ticks=CapabilityStatus.TESTED,
            trade_ticks=CapabilityStatus.UNSUPPORTED,
            bars=CapabilityStatus.TESTED,
            notes=(
                "FX OTC broker — last price field is unreliable or zero. "
                "Use bid/ask (QuoteTick) as the primary data source."
            ),
        ),
        SYMBOL_CALC_MODE_CFD: CalcModeCapability(
            nautilus_instrument_type=Cfd,
            quote_ticks=CapabilityStatus.TESTED,
            trade_ticks=CapabilityStatus.UNSUPPORTED,
            bars=CapabilityStatus.TESTED,
        ),
        SYMBOL_CALC_MODE_CFDINDEX: CalcModeCapability(
            nautilus_instrument_type=Cfd,
            quote_ticks=CapabilityStatus.TESTED,
            trade_ticks=CapabilityStatus.UNSUPPORTED,
            bars=CapabilityStatus.TESTED,
            notes="Index CFDs confirmed on USTEC (Tickmill-Demo, 2026-05-02).",
        ),
        SYMBOL_CALC_MODE_CFDLEVERAGE: CalcModeCapability(
            nautilus_instrument_type=Cfd,
            quote_ticks=CapabilityStatus.ASSUMED,
            trade_ticks=CapabilityStatus.UNSUPPORTED,
            bars=CapabilityStatus.ASSUMED,
        ),
        SYMBOL_CALC_MODE_FOREX_NO_LEVERAGE: CalcModeCapability(
            nautilus_instrument_type=CurrencyPair,
            quote_ticks=CapabilityStatus.ASSUMED,
            trade_ticks=CapabilityStatus.UNSUPPORTED,
            bars=CapabilityStatus.ASSUMED,
        ),
    },
)
"""
Pre-built VenueProfile for Tickmill Demo accounts.

Confirmed capabilities (2026-05-02):
- FOREX  → CurrencyPair / QuoteTicks TESTED / TradeTicks UNSUPPORTED / Bars TESTED
- CFD    → Cfd          / QuoteTicks TESTED / TradeTicks UNSUPPORTED / Bars TESTED
- CFDINDEX → Cfd        / QuoteTicks TESTED / TradeTicks UNSUPPORTED / Bars TESTED
"""


__all__ = [
    "CapabilityStatus",
    "CalcModeCapability",
    "VenueProfile",
    "TICKMILL_DEMO_PROFILE",
    # calc_mode constants
    "SYMBOL_CALC_MODE_FOREX",
    "SYMBOL_CALC_MODE_FUTURES",
    "SYMBOL_CALC_MODE_CFD",
    "SYMBOL_CALC_MODE_CFDINDEX",
    "SYMBOL_CALC_MODE_CFDLEVERAGE",
    "SYMBOL_CALC_MODE_FOREX_NO_LEVERAGE",
    "SYMBOL_CALC_MODE_EXCH_STOCKS",
    "SYMBOL_CALC_MODE_EXCH_FUTURES",
    "SYMBOL_CALC_MODE_EXCH_FUTURES_FORTS",
    "SYMBOL_CALC_MODE_EXCH_BONDS",
    "SYMBOL_CALC_MODE_EXCH_STOCKS_MOEX",
    "SYMBOL_CALC_MODE_EXCH_BONDS_MOEX",
]
