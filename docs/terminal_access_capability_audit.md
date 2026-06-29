# Terminal Access Capability Audit

Last aligned with capability matrices and homologation: **2026-06-28**.

## Purpose

Verify coherence between `EXTERNAL_RPYC` terminal access, the RPyC gateway RPC surface, and capabilities effectively supported by `nt_mt5` at the **Nautilus adapter** boundary.

This audit separates:

1. **Gateway RPC surface** — methods exposed by the external RPyC bridge.
2. **Terminal-access wiring** — adapter routes to those methods correctly.
3. **Nautilus-level capability** — full DataClient / ExecClient flow produces correct domain objects and lifecycle behavior.
4. **Documented status** — matches `docs/data_capability_matrix.md` and `docs/execution_capability_matrix.md`.

Broker differences use **`VenueProfile`** (`TICKMILL_DEMO_PROFILE`, `XP_B3_PROFILE`) — not separate adapters. See `docs/decisions.md` §20 and `docs/venue_profile.md`.

---

## Status definitions

| Status | Meaning |
|--------|---------|
| **Supported** | Production path, Nautilus-level flow exercised, deterministic tests, docs aligned. |
| **Partial** | RPC/wiring exists; missing full Nautilus flow, homologation, reports, or profile-specific validation. |
| **Unsupported** | Not implemented; fails safely and documented. |
| **Profile-dependent** | Behavior differs by `VenueProfile` (e.g. TradeTick on Tickmill vs XP/B3). |

Gateway method availability alone does **not** imply **Supported**.

---

## Data capabilities

Aligned with `docs/data_capability_matrix.md`.

| Capability | Gateway RPC | Adapter (Nautilus) | Deterministic tests | Homologation / live | Status |
|---|---|---|---|---|---|
| **Instruments** | `symbols_get`, `symbol_info` | Provider load/request | TC-D01–D03 | Tickmill + XP closed (`run_closed_market.py`, `run_xp_closed_market.py`) | **Partial** |
| **Live quotes** | WS feed (MQL5 Service); legacy `symbol_info_tick` poll | WS → `QuoteTick` when `feed.enabled=True` | TC-D20, `test_feed_*` | **TC-HOM-D02** (`run_open_market.py`, Tickmill) | **Partial** |
| **Historical quotes** | `copy_ticks_from`, `copy_ticks_range` | `_request_quote_ticks` → `get_historical_ticks` → **`copy_ticks_from`** (IB `req_historical_ticks` removed, 2026-06-28) | TC-D21 matrix | **TC-HOM-D21** (Tickmill); XP closed | **Partial** — live Nautilus-level OK; promote to Supported when DataEngine path is required |
| **Trade ticks** | `copy_ticks_*` (`last` field) | **Tickmill:** gated **Unsupported**. **XP/B3:** **Partial** (OBSERVED) | TC-D30/D31 + XP unit tests | XP **TC-HOM-D21-T** closed; live WS OPEN (pregão) | **Profile-dependent** |
| **Bars** | `copy_rates_*`; WS `subscribe_bars` | Hist + live WS bars | TC-D40/D41 | D03/D04b homolog | **Partial** |
| **Order book** | `market_book_get` (wrapper) | Safe reject | TC-D10 | N/A | **Unsupported** |
| **Instrument status** | N/A | N/A | N/A | N/A | **Unsupported** |
| **Lifecycle / unsubscribe** | `shutdown`; WS unsubscribe | D70 wiring + homolog D05 | TC-D70 | **TC-HOM-D05** | **Partial** |

**Operational note:** pass Unix `int` timestamps to `copy_ticks_from` on RPyC — `datetime` may fail with `(-2, Invalid arguments)`.

---

## Execution capabilities

Aligned with `docs/execution_capability_matrix.md`.

| Capability | Gateway RPC | Adapter (Nautilus) | Deterministic tests | Homologation (Tickmill) | Status |
|---|---|---|---|---|---|
| **Market orders** | `order_send` | Submit + fill lifecycle | TC-EL-02/03/07/20 | **E01** round-trip | **Supported** |
| **Limit orders** | `order_send` pending | GTC/IOC/FOK/DAY mapping via `MAP_TIME_IN_FORCE` + `type_filling` | TC-EL-18/19 | **E03**, **E06**, **E06de** | **Partial** |
| **Stop orders** | `order_send` pending | STOP_MARKET / STOP_LIMIT | TC-EL-21–24 | **E02**, **E07b** trigger amend | **Partial** |
| **Modify orders** | `order_send` `action=7` | `_modify_order` → `modify_order` | TC-EL-11 | **E07**, **E07b** | **Partial** |
| **Cancel orders** | `order_send` `action=8` | `_cancel_order` | TC-EL-10/12 | **E03**, **E43** (10013), **E04a** | **Partial** |
| **Unsupported type/TIF** | N/A (pre-venue) | `validate_order_pre_venue` | TC-EL-13/14 | N/A | **Supported** |
| **Position reconcile** | `positions_get` | `generate_position_status_reports` | TC-EL-06 | **E05**, **E81** | **Partial** |
| **Order reports** | `orders_get` | `generate_order_status_reports` via `get_open_orders` (2026-06-28 fix) | TC-EL-08/09 | **E81** pending overlap | **Partial** |
| **Fill reports** | `history_deals_get` | `generate_fill_reports` | TC-EL-04/05 | **E05b** | **Partial** |
| **Stop lifecycle** | `order_send`, `positions_get` | `cancel_on_stop`, `close_on_stop` on `_disconnect` | TC-EL-15–17 | **E04**, **E04b**, **E10b** | **Supported** |
| **XP/B3 execution** | Same RPC surface | Not homologated open-market yet | Tier 1 stubs only | OPEN (pregão) | **Planned** / profile TBD |

---

## Known gaps (still open)

| Gap | Status |
|-----|--------|
| Order book Nautilus flow | **Unsupported** |
| Tickmill TradeTick live/historical | **Unsupported** by design (`VenueProfile`) |
| XP TradeTick live stream | **Partial** — closed-market hist OK; open pregão pending |
| XP execution homologation | Not started (open market) |
| Batch cancel / modify rejected explicit tests | Partial |
| `history_orders_get` full historical order reconcile | Partial |
| Instrument status streaming | **Unsupported** |
| Multi-symbol WS (**D07** USTEC) | Tickmill homolog **DONE** (2026-06-29) |

**Resolved (2026-06-28 Wave 4):** historical quotes via `copy_ticks_from`; `get_open_orders`; fill reports live path; cancel rejection 10013; FOK/DAY limit submit; stop trigger amend; open-on-start reconcile; `MAP_TIME_IN_FORCE` on submit.

---

## Interpretation rules

1. **RPC method ≠ capability** — exposure in gateway/wrapper is necessary but not sufficient.
2. **Supported** requires production behavior + Nautilus-level exercise + deterministic tests + matrix alignment.
3. **Homologation** (`homologation/`) is the manual operational gate on real MT5; see `docs/testing_contract.md` Tier 1.5.
4. **Matrices are authoritative for status** — update this audit when matrices change.
5. **VenueProfile** — always state broker/profile when claiming data or execution behavior.

---

## References

- `docs/adapter_contract.md`
- `docs/terminal_access_contract.md`
- `docs/testing_contract.md`
- `docs/data_capability_matrix.md`
- `docs/execution_capability_matrix.md`
- `docs/decisions.md`
- `docs/venue_profile.md`
- `res/proximos testes adaptador.md` — homologation tracker
- `res/tickmill_restrictions.md` / `res/xp_b3_restrictions.md` — broker profiles
