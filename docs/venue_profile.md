# VenueProfile — Broker-Specific Capability Declarations

## Purpose

`VenueProfile` maps MT5 `trade_calc_mode` integer constants to:

1. **The Nautilus instrument type** to emit when parsing a symbol (`CurrencyPair`, `Cfd`, etc.).
2. **Capability statuses** for each data operation (`quote_ticks`, `trade_ticks`, `bars`).

This solves two problems that arise from the diversity of MT5 brokers:

- **Instrument type ambiguity**: Without a profile, the adapter must guess whether mode=0 means `CurrencyPair` or `Cfd`. With a profile, the answer is explicit and broker-specific.
- **Unsupported operations**: Some brokers (e.g. Tickmill-Demo) have `last=0.0` for FX and CFD instruments, making `TradeTick` data semantically invalid. The profile gates these operations before they reach the MT5 client.

---

## Core types

### `CapabilityStatus` (enum)

An epistemic confidence scale for a data operation on a specific broker/mode:

| Value | Meaning |
|-------|---------|
| `ASSUMED` | Declared by convention, not yet observed in real data |
| `OBSERVED` | Seen in a live session, no automated test coverage yet |
| `TESTED` | Covered by a deterministic automated test |
| `CERTIFIED` | Tested + validated against a live MT5 terminal |
| `UNSUPPORTED` | The adapter explicitly does not support this operation |

### `CalcModeCapability`

A frozen dataclass declaring the instrument type and capability statuses for a single `trade_calc_mode`:

```python
CalcModeCapability(
    nautilus_instrument_type=CurrencyPair,
    quote_ticks=CapabilityStatus.TESTED,
    trade_ticks=CapabilityStatus.UNSUPPORTED,
    bars=CapabilityStatus.TESTED,
    notes="FX OTC broker — last price is unreliable.",
)
```

### `VenueProfile`

A frozen dataclass mapping `trade_calc_mode` → `CalcModeCapability`:

```python
VenueProfile(
    name="my-broker",
    capabilities={
        SYMBOL_CALC_MODE_FOREX: CalcModeCapability(...),
        SYMBOL_CALC_MODE_CFDINDEX: CalcModeCapability(...),
    },
    strict=False,
)
```

- `strict=True`: raises `ValueError` if an `ASSUMED` or `OBSERVED` status is queried (for regression safety).
- Unknown `trade_calc_mode` values raise `ValueError` at query time.

---

## `trade_calc_mode` constants

```python
SYMBOL_CALC_MODE_FOREX = 0           # FX OTC — no reliable last price
SYMBOL_CALC_MODE_FUTURES = 1         # OTC futures
SYMBOL_CALC_MODE_CFD = 2             # Generic CFD
SYMBOL_CALC_MODE_CFDINDEX = 3        # CFD on an index (USTEC, SP500, etc.)
SYMBOL_CALC_MODE_CFDLEVERAGE = 4     # CFD with leverage multiplier
SYMBOL_CALC_MODE_FOREX_NO_LEVERAGE = 5
SYMBOL_CALC_MODE_EXCH_STOCKS = 6     # Exchange stocks (real last price)
SYMBOL_CALC_MODE_EXCH_FUTURES = 7    # Exchange futures (B3: WIN, WDO)
SYMBOL_CALC_MODE_EXCH_FUTURES_FORTS = 8
SYMBOL_CALC_MODE_EXCH_BONDS = 9
SYMBOL_CALC_MODE_EXCH_STOCKS_MOEX = 10
SYMBOL_CALC_MODE_EXCH_BONDS_MOEX = 11
```

---

## Pre-built profiles

### `TICKMILL_DEMO_PROFILE`

```python
from nautilus_mt5 import TICKMILL_DEMO_PROFILE
```

Covers Tickmill-Demo and equivalent OTC FX/CFD brokers:

| `trade_calc_mode` | Instrument type | quote_ticks | trade_ticks | bars |
|-------------------|-----------------|-------------|-------------|------|
| 0 — FOREX | `CurrencyPair` | TESTED | **UNSUPPORTED** | TESTED |
| 2 — CFD | `Cfd` | TESTED | **UNSUPPORTED** | TESTED |
| 3 — CFDINDEX | `Cfd` | TESTED | **UNSUPPORTED** | TESTED |
| 4 — CFDLEVERAGE | `Cfd` | ASSUMED | **UNSUPPORTED** | ASSUMED |
| 5 — FOREX_NO_LEVERAGE | `CurrencyPair` | ASSUMED | **UNSUPPORTED** | ASSUMED |

`TradeTick` is `UNSUPPORTED` for all modes because Tickmill-Demo returns `last=0.0` for FX and CFD instruments (confirmed live 2026-05-02).

---

## Usage

### Configuring the data client

A `venue_profile` is **required** in `MetaTrader5DataClientConfig`. The adapter refuses to connect without one:

```python
from nautilus_mt5 import (
    TICKMILL_DEMO_PROFILE,
    MT5LiveDataClientFactory,
    MetaTrader5DataClientConfig,
)

config = MetaTrader5DataClientConfig(
    ...,
    venue_profile=TICKMILL_DEMO_PROFILE,
)
```

### Defining a custom profile

```python
from nautilus_mt5.venue_profile import (
    VenueProfile, CalcModeCapability, CapabilityStatus,
    SYMBOL_CALC_MODE_EXCH_FUTURES,
)
from nautilus_trader.model.instruments import FuturesContract

B3_PROFILE = VenueProfile(
    name="b3-xp",
    capabilities={
        SYMBOL_CALC_MODE_EXCH_FUTURES: CalcModeCapability(
            nautilus_instrument_type=FuturesContract,
            quote_ticks=CapabilityStatus.ASSUMED,
            trade_ticks=CapabilityStatus.ASSUMED,
            bars=CapabilityStatus.ASSUMED,
            notes="B3 mini-contracts (WIN, WDO) — real last price available.",
        ),
    },
)
```

---

## How the adapter uses the profile

### 1. Instrument parsing (`parse_instrument`)

When `venue_profile` is provided, `parse_instrument()` reads `symbol_details.trade_calc_mode` and selects the Nautilus constructor declared in the profile:

- `CurrencyPair` → `parse_currency_pair_contract()`
- `Cfd` → `parse_cfd_contract()`
- Unknown type → `ValueError`

Without a profile (legacy path), all instruments default to `Cfd`.

### 2. Data operation gating

`_subscribe_trade_ticks()` and `_request_trade_ticks()` call `profile.check_capability(calc_mode, "trade_ticks")`:

- `UNSUPPORTED` → log warning, return immediately (no call to MT5 client).
- `ASSUMED` / `OBSERVED` → log warning, proceed (unless `strict=True`).
- `TESTED` / `CERTIFIED` → proceed silently.

Same pattern applies to `quote_ticks` and `bars` if gated in the future.

---

## Testing

- **Unit tests**: `tests/unit/test_venue_profile.py` — covers `CapabilityStatus`, `CalcModeCapability`, `VenueProfile.get_capability()`, `VenueProfile.check_capability()`, `TICKMILL_DEMO_PROFILE` declarations.
- **Integration tests**: TC-D30/TC-D31 in `tests/integration_tests/adapters/mt5/test_data_tester_matrix_external_rpyc.py` verify profile-based rejection of trade tick operations.
