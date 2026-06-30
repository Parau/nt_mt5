# Terminal Access Capability Audit

Last aligned with capability matrices and homologation: **2026-06-30**.

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
| **Live quotes** | WS feed (MQL5 Service); legacy `symbol_info_tick` poll | WS → `QuoteTick` when `feed.enabled=True` | TC-D20, `test_feed_*` | **Tickmill:** TC-HOM-D02. **XP/B3:** TC-HOM-D02 (`run_xp_open_market_feed.py`) | **Partial** |
| **Historical quotes** | `copy_ticks_from`, `copy_ticks_range` | `_request_quote_ticks` → `copy_ticks_from` | TC-D21 matrix | **Tickmill:** TC-HOM-D21. **XP/B3:** TC-HOM-D21 closed + **open** (`run_xp_backlog_homologation.py`, 2026-06-30) | **Partial** |
| **Trade ticks** | `copy_ticks_*`; RPyC `subscribe_ticks` AllLast | **Tickmill:** Unsupported. **XP/B3:** subscribe + request | TC-D30/D31 | **XP:** D21-T closed; D30/D31 open (`run_xp_trade_ticks_homologation.py`) | **Profile-dependent** |
| **Bars** | `copy_rates_*`; WS `subscribe_bars` | Hist + live WS bars | TC-D40/D41 | **Tickmill:** D03. **XP/B3:** D03 (`run_xp_open_market_feed.py`) | **Partial** |
| **Order book** | `market_book_get` (wrapper) | Safe reject | TC-D10 | N/A | **Unsupported** |
| **Instrument status** | N/A | N/A | N/A | N/A | **Unsupported** |
| **Lifecycle / unsubscribe** | `shutdown`; WS unsubscribe | D70 wiring + homolog D05 | TC-D70 | **Tickmill:** D05. **XP/B3:** D05+D06 feed | **Partial** |

**Operational note:** pass Unix `int` timestamps to `copy_ticks_from` on RPyC — `datetime` may fail with `(-2, Invalid arguments)`.

---

## Execution capabilities

Aligned with `docs/execution_capability_matrix.md`.

| Capability | Gateway RPC | Adapter (Nautilus) | Deterministic tests | Homologation | Status |
|---|---|---|---|---|---|
| **Market orders** | `order_send` | Submit + fill lifecycle | TC-EL-02/03/07/20 | **Tickmill:** E01. **XP/B3:** E01 WDON26/PETR4/DI1F27 21/21 each (`run_xp_exec_homologation.py`, 2026-06-30) | **Supported** |
| **Limit orders** | `order_send` pending | GTC/IOC/FOK/DAY mapping | TC-EL-18/19 | **Tickmill:** E03/E06. **XP/B3:** E03/E06/E06de/E07 | **Partial** |
| **Stop orders** | `order_send` pending | STOP_MARKET / STOP_LIMIT | TC-EL-21–24 | **Tickmill:** E02/E07b. **XP/B3:** E02/E07b | **Partial** |
| **Modify orders** | `order_send` `action=7` | `_modify_order` | TC-EL-11 | **Tickmill:** E07/E07b. **XP/B3:** E07/E07b | **Partial** |
| **Cancel orders** | `order_send` `action=8` | `_cancel_order` | TC-EL-10/12 | **Tickmill:** E03/E43/E04a. **XP/B3:** E03/E43/E04a | **Partial** |
| **Unsupported type/TIF** | N/A (pre-venue) | `validate_order_pre_venue` | TC-EL-13/14 | N/A | **Supported** |
| **Position reconcile** | `positions_get` | `generate_position_status_reports` | TC-EL-06 | **Tickmill:** E05/E81. **XP/B3:** E05/E10/E81 | **Partial** |
| **Order reports** | `orders_get` | `generate_order_status_reports` | TC-EL-08/09 | **Tickmill:** E81. **XP/B3:** E81 | **Partial** |
| **Fill reports** | `history_deals_get` | `generate_fill_reports` | TC-EL-04/05 | **Tickmill:** E05b. **XP/B3:** E05b | **Partial** |
| **Stop lifecycle** | `order_send`, `positions_get` | `cancel_on_stop`, `close_on_stop` | TC-EL-15–17 | **Tickmill:** E04/E10b. **XP/B3:** E04/E08/E10b–E10d | **Supported** |

---

## Known gaps (still open)

| Gap | Status |
|-----|--------|
| Order book Nautilus flow | **Unsupported** |
| Tickmill TradeTick live/historical | **Unsupported** by design (`VenueProfile`) |
| XP TradeTick live/historical (D30/D31) | Homolog **DONE** — WINQ26 (`run_xp_trade_ticks_homologation.py`, 2026-06-30) |
| XP exec open market (E01–E10) | Homolog **DONE** — WDON26, PETR4, DI1F27 21/21 each (2026-06-30) |
| XP D21 historical quotes (open) | Homolog **DONE** — `run_xp_backlog_homologation.py` (2026-06-30) |
| XP D06 gateway restart | Homolog **DONE** — `run_xp_backlog_homologation.py` (2026-06-30) |
| XP D06-SVC Service restart | Homolog **DONE** — `run_d06_svc_homologation.py` (2026-06-30) |
| Batch cancel / modify rejected explicit tests | Partial |
| `history_orders_get` full historical order reconcile | Partial |
| Instrument status streaming | **Unsupported** |
| Multi-symbol WS (**D07**) | Tickmill **DONE** (2026-06-29). XP/B3 **DONE** — feed suite + wave3 4/4 (PETR4=99 com pregão equity aberto, 2026-06-30) |

**Resolved (2026-06-30 XP baseline):** open-market feed D02–D07; D06 gateway + D06-SVC; D21 open; exec full suite WDON26/PETR4/DI1F27; wave3 E10/E10b; trade ticks WINQ26. Continuous `WIN$`/`WDO$` excluded from live homolog (data-only).

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
