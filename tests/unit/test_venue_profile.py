"""
test_venue_profile.py
Unit tests for the VenueProfile capability system.
"""
import pytest

from nautilus_trader.model.instruments import Cfd, CurrencyPair

from nautilus_mt5.venue_profile import (
    SYMBOL_CALC_MODE_CFD,
    SYMBOL_CALC_MODE_CFDINDEX,
    SYMBOL_CALC_MODE_CFDLEVERAGE,
    SYMBOL_CALC_MODE_FOREX,
    SYMBOL_CALC_MODE_FOREX_NO_LEVERAGE,
    TICKMILL_DEMO_PROFILE,
    CalcModeCapability,
    CapabilityStatus,
    VenueProfile,
)


# ---------------------------------------------------------------------------
# CapabilityStatus enum
# ---------------------------------------------------------------------------


def test_capability_status_values():
    assert CapabilityStatus.ASSUMED == "assumed"
    assert CapabilityStatus.OBSERVED == "observed"
    assert CapabilityStatus.TESTED == "tested"
    assert CapabilityStatus.CERTIFIED == "certified"
    assert CapabilityStatus.UNSUPPORTED == "unsupported"


# ---------------------------------------------------------------------------
# CalcModeCapability
# ---------------------------------------------------------------------------


def test_calc_mode_capability_construction():
    cap = CalcModeCapability(
        nautilus_instrument_type=CurrencyPair,
        quote_ticks=CapabilityStatus.TESTED,
        trade_ticks=CapabilityStatus.UNSUPPORTED,
        bars=CapabilityStatus.ASSUMED,
    )
    assert cap.nautilus_instrument_type is CurrencyPair
    assert cap.quote_ticks == CapabilityStatus.TESTED
    assert cap.trade_ticks == CapabilityStatus.UNSUPPORTED
    assert cap.bars == CapabilityStatus.ASSUMED
    assert cap.notes is None


def test_calc_mode_capability_with_notes():
    cap = CalcModeCapability(
        nautilus_instrument_type=Cfd,
        quote_ticks=CapabilityStatus.OBSERVED,
        trade_ticks=CapabilityStatus.UNSUPPORTED,
        bars=CapabilityStatus.OBSERVED,
        notes="CFD index — last=0.0 on Tickmill",
    )
    assert cap.notes == "CFD index — last=0.0 on Tickmill"


def test_calc_mode_capability_is_frozen():
    cap = CalcModeCapability(
        nautilus_instrument_type=Cfd,
        quote_ticks=CapabilityStatus.TESTED,
        trade_ticks=CapabilityStatus.UNSUPPORTED,
        bars=CapabilityStatus.TESTED,
    )
    with pytest.raises((AttributeError, TypeError)):
        cap.quote_ticks = CapabilityStatus.ASSUMED  # type: ignore[misc]


# ---------------------------------------------------------------------------
# VenueProfile.get_capability
# ---------------------------------------------------------------------------


def _minimal_profile(strict: bool = False) -> VenueProfile:
    return VenueProfile(
        name="test-profile",
        capabilities={
            0: CalcModeCapability(
                nautilus_instrument_type=CurrencyPair,
                quote_ticks=CapabilityStatus.TESTED,
                trade_ticks=CapabilityStatus.UNSUPPORTED,
                bars=CapabilityStatus.TESTED,
            ),
            3: CalcModeCapability(
                nautilus_instrument_type=Cfd,
                quote_ticks=CapabilityStatus.ASSUMED,
                trade_ticks=CapabilityStatus.UNSUPPORTED,
                bars=CapabilityStatus.ASSUMED,
            ),
        },
        strict=strict,
    )


def test_get_capability_known_mode():
    profile = _minimal_profile()
    cap = profile.get_capability(0)
    assert cap.nautilus_instrument_type is CurrencyPair
    assert cap.quote_ticks == CapabilityStatus.TESTED


def test_get_capability_unknown_mode_raises():
    profile = _minimal_profile()
    with pytest.raises(ValueError, match="trade_calc_mode=99"):
        profile.get_capability(99)


def test_get_capability_error_message_lists_known_modes():
    profile = _minimal_profile()
    with pytest.raises(ValueError, match="Known modes: \\[0, 3\\]"):
        profile.get_capability(99)


# ---------------------------------------------------------------------------
# VenueProfile.check_capability
# ---------------------------------------------------------------------------


def test_check_capability_unsupported():
    profile = _minimal_profile()
    status = profile.check_capability(0, "trade_ticks")
    assert status == CapabilityStatus.UNSUPPORTED


def test_check_capability_tested():
    profile = _minimal_profile()
    status = profile.check_capability(0, "quote_ticks")
    assert status == CapabilityStatus.TESTED


def test_check_capability_assumed_no_strict():
    profile = _minimal_profile(strict=False)
    status = profile.check_capability(3, "quote_ticks")
    assert status == CapabilityStatus.ASSUMED


def test_check_capability_assumed_strict_raises():
    profile = _minimal_profile(strict=True)
    with pytest.raises(ValueError, match="strict mode requires TESTED or CERTIFIED"):
        profile.check_capability(3, "quote_ticks")


def test_check_capability_observed_strict_raises():
    profile = VenueProfile(
        name="test",
        capabilities={
            0: CalcModeCapability(
                nautilus_instrument_type=CurrencyPair,
                quote_ticks=CapabilityStatus.OBSERVED,
                trade_ticks=CapabilityStatus.UNSUPPORTED,
                bars=CapabilityStatus.OBSERVED,
            )
        },
        strict=True,
    )
    with pytest.raises(ValueError, match="strict mode"):
        profile.check_capability(0, "bars")


def test_check_capability_unsupported_strict_does_not_raise():
    """UNSUPPORTED in strict mode should return without raising — it's a valid, tested status."""
    profile = _minimal_profile(strict=True)
    status = profile.check_capability(0, "trade_ticks")
    assert status == CapabilityStatus.UNSUPPORTED


# ---------------------------------------------------------------------------
# TICKMILL_DEMO_PROFILE
# ---------------------------------------------------------------------------


def test_tickmill_profile_name():
    assert TICKMILL_DEMO_PROFILE.name == "tickmill-demo"


def test_tickmill_profile_forex_is_currency_pair():
    cap = TICKMILL_DEMO_PROFILE.get_capability(SYMBOL_CALC_MODE_FOREX)
    assert cap.nautilus_instrument_type is CurrencyPair


def test_tickmill_profile_cfd_is_cfd():
    cap = TICKMILL_DEMO_PROFILE.get_capability(SYMBOL_CALC_MODE_CFD)
    assert cap.nautilus_instrument_type is Cfd


def test_tickmill_profile_cfdindex_is_cfd():
    cap = TICKMILL_DEMO_PROFILE.get_capability(SYMBOL_CALC_MODE_CFDINDEX)
    assert cap.nautilus_instrument_type is Cfd


def test_tickmill_profile_cfdleverage_is_cfd():
    cap = TICKMILL_DEMO_PROFILE.get_capability(SYMBOL_CALC_MODE_CFDLEVERAGE)
    assert cap.nautilus_instrument_type is Cfd


def test_tickmill_profile_forex_no_leverage_is_currency_pair():
    cap = TICKMILL_DEMO_PROFILE.get_capability(SYMBOL_CALC_MODE_FOREX_NO_LEVERAGE)
    assert cap.nautilus_instrument_type is CurrencyPair


@pytest.mark.parametrize(
    "calc_mode",
    [
        SYMBOL_CALC_MODE_FOREX,
        SYMBOL_CALC_MODE_CFD,
        SYMBOL_CALC_MODE_CFDINDEX,
        SYMBOL_CALC_MODE_CFDLEVERAGE,
        SYMBOL_CALC_MODE_FOREX_NO_LEVERAGE,
    ],
)
def test_tickmill_profile_trade_ticks_unsupported_for_all_modes(calc_mode):
    cap = TICKMILL_DEMO_PROFILE.get_capability(calc_mode)
    assert cap.trade_ticks == CapabilityStatus.UNSUPPORTED, (
        f"trade_ticks must be UNSUPPORTED for calc_mode={calc_mode} in TICKMILL_DEMO_PROFILE"
    )


@pytest.mark.parametrize(
    "calc_mode",
    [
        SYMBOL_CALC_MODE_FOREX,
        SYMBOL_CALC_MODE_CFD,
        SYMBOL_CALC_MODE_CFDINDEX,
    ],
)
def test_tickmill_profile_bars_status_is_tested_or_assumed(calc_mode):
    cap = TICKMILL_DEMO_PROFILE.get_capability(calc_mode)
    assert cap.bars in (CapabilityStatus.TESTED, CapabilityStatus.ASSUMED, CapabilityStatus.OBSERVED)


def test_tickmill_profile_unknown_mode_raises():
    with pytest.raises(ValueError, match="trade_calc_mode=99"):
        TICKMILL_DEMO_PROFILE.get_capability(99)
