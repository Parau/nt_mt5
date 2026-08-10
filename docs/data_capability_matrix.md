# Data Capability Matrix

This document translates the NautilusTrader **Data Testing Spec** into an internal capability matrix for `nt_mt5`.

## Source of truth

Official reference:
- Published docs: https://nautilustrader.io/docs/latest/developer_guide/spec_data_testing/

Upstream source reference:
- GitHub source: https://github.com/nautechsystems/nautilus_trader/blob/develop/docs/developer_guide/spec_data_testing.md

If this file conflicts with NautilusTrader's published testing spec, the upstream spec wins. Use this file as a project planning and review aid, not as a replacement for the official spec.

## How to use this matrix

- **Required baseline** means the capability should normally be implemented and tested for a useful MT5 adapter.
- **Conditional** means it should be implemented and tested only if `nt_mt5` explicitly supports it.
- **Out of scope unless intentionally added** means it should normally be documented as unsupported for `nt_mt5`, unless the project intentionally adds support.
- Every supported capability should map to concrete tests in the project test suite.
- Every unsupported capability should be documented explicitly in adapter docs rather than silently ignored.

## Capability status definitions

Use these status values when tracking actual project support:

- **Supported**: production implementation exists, the Nautilus-level data flow is exercised, deterministic tests exist, and docs/capability matrix are aligned.
- **Partial**: gateway/wrapper/wiring exists, but Nautilus-level flow, DataTester coverage, lifecycle behavior, or documentation is incomplete.
- **Unsupported**: not implemented and should fail safely or be documented as unavailable.
- **Planned**: intentionally future work.

A gateway method being available is not enough to mark a Nautilus data capability as `Supported`.

## Upstream framing

The NautilusTrader Data Testing Spec defines a grouped test matrix using `DataTester`. Each adapter must pass the subset of tests matching its supported data types. Test groups are ordered from least derived to most derived data, and an adapter that passes groups 1–4 is considered baseline data compliant. Adapter-specific data behavior should be documented in the adapter's own guide, not in the upstream spec.

## Matrix

| Group | Upstream scope | Representative cases | `nt_mt5` expectation | Notes |
|---|---|---|---|---|
| 1. Instruments | Instrument loading and instrument subscription | TC-D01, TC-D02, TC-D03 | **Required baseline** | Instrument provider behavior, symbol normalization, cache population, and request/subscribe flows should be covered. |
| 2. Order book | Book deltas, interval snapshots, depth snapshots, one-shot snapshots, managed books, historical book deltas | TC-D10–TC-D15 | **Conditional** | MT5 adapters often do not expose a native full order book in the same shape as exchange adapters. Support should be declared explicitly; unsupported paths should be documented and safely rejected. |
| 3. Quotes | Live quote ticks and historical quote ticks | TC-D20, TC-D21 | **Required baseline** | Quote subscription is a core live-data capability. Historical quote support is expected if the MT5 path provides it. |
| 4. Trades | Live trade ticks and historical trade ticks | TC-D30, TC-D31 | **Required baseline if MT5 trade-tick data is exposed** | For `nt_mt5`, this should be treated as core if the bridge exposes trade tick or equivalent last-trade data. If not, the limitation must be documented. |
| 5. Bars | Live bars and historical bars | TC-D40, TC-D41 | **Required baseline** | Bar subscriptions and historical bar requests are natural core features for MT5 and should be part of the supported baseline. |
| 6. Derivatives data | Mark price, index price, funding rates, historical funding | TC-D50–TC-D53 | **Out of scope unless intentionally added** | These are derivative-exchange concepts. They should only be claimed if the adapter intentionally maps real MT5/venue concepts to them. |
| 7. Instrument status | Instrument status and instrument close subscriptions | TC-D60, TC-D61 | **Conditional** | Useful if the bridge or venue path can provide state-change and close events. Otherwise document as unsupported. |
| 8. Option greeks / chain | Option greeks and option chain slice subscriptions | TC-D62, TC-D63 | **Out of scope unless intentionally added** | Only relevant if `nt_mt5` intentionally supports options-specific analytics in Nautilus-native form. |
| 9. Lifecycle / custom params | Unsubscribe on stop, custom subscribe params, custom request params | TC-D70–TC-D72 | **Required where applicable** | Clean unsubscribe and pass-through custom params should be tested for supported flows. Adapter-specific params must be documented in project docs. |

## Operational traceability matrix

This section tracks the current implementation status. It should be updated whenever a task changes data behavior, tests, or documented support.

| Capability | Status | Official test IDs | Deterministic coverage | Live coverage | Validated by | Notes |
|---|---|---|---|---|---|---|
| Instruments | Partial | TC-D01, TC-D02, TC-D03 | TC-D01 (load), TC-D02 (subscribe→warning, no raise) e TC-D03 (request) cobertos em `test_data_tester_matrix_external_rpyc.py` (determinístico); TC-D01/TC-D03 também em `test_external_rpyc_data_tester.py` (live USTEC) | ✅ Validado live (Tickmill-Demo, USTEC e BTCUSD crypto CFD) | `test_data_tester_matrix_external_rpyc.py`, `test_external_rpyc_data_tester.py` | TC-D02 coberto em 2026-05-02: `_subscribe_instruments` é unsupported — loga warning e retorna sem levantar exceção. BTCUSD validado em exec_smoke_trading_node.py (2026-05-02): instrumento carregado e resolvido corretamente pelo provider. |
| Order book | Unsupported | TC-D10–TC-D15 | TC-D10: rejeição segura documentada e testada em `test_data_tester_matrix_external_rpyc.py` | N/A | `test_data_tester_matrix_external_rpyc.py::test_tc_d10_order_book_unsupported_logs_warning` | Não implementar sem fluxo Nautilus order book completo. |
| Quote ticks | Partial | TC-D20 | **Live WS feed:** Tier 1 matrix + homolog. **Legacy poll:** TC-D20 wiring. | ✅ **Tickmill:** TC-HOM-D02 (`run_open_market.py`, BTCUSD, 2026-06-28). **XP/B3:** WDON26 feed suite; **PETR4/DI1F27** hist D21 + multi-symbol D07 (`run_xp_symbol_quote_trade_confirm.py`, `run_wave3_homologation.py`, 2026-06-30) | `homologation/run_open_market.py`, `run_xp_open_market_feed.py`, `run_wave3_homologation.py`, `run_xp_symbol_quote_trade_confirm.py` | Live WS: PETR4/DI1F27 histórico PASS; stream isolado D02 com timeout de harness (quotes recebidas em multi-symbol). |
| Historical quote ticks | Partial | TC-D21 | TC-D21 coberto em `test_data_tester_matrix_external_rpyc.py`: wiring + end-to-end + `limit=0` usa `tick_capacity`; **`start=None` com `limit` explícito honra o limit** + resultado vazio não chama `_handle_quote_ticks` + `correlation_id` repassado. Live Nautilus-level: `homologation/run_open_market.py` (TC-HOM-D21). | ✅ **Tickmill:** TC-HOM-D21 (`run_open_market.py` / `run_closed_market.py`). **XP/B3:** TC-HOM-D21 closed (`run_xp_closed_market.py`) + **open** (`run_xp_backlog_homologation.py`, 50 ticks, 2026-06-30) | `test_data_tester_matrix_external_rpyc.py::test_tc_d21_*`, `homologation/run_open_market.py`, `homologation/run_xp_closed_market.py`, `homologation/run_xp_backlog_homologation.py` | **Fix D21 (2026-06-28):** path canônico `get_historical_ticks` → **`copy_ticks_from`**. `start=None` + `limit>0` respeita o limit. RPyC: preferir timestamps Unix `int`. |
| Trade ticks | **Profile-dependent** | TC-D30 | **Tickmill:** rejeição via `VenueProfile` (`test_tc_d30_*`). **XP_B3:** subscribe passa gate + homolog open. **AMP_US:** Tier 1 gate (`test_tc_d30_amp_*`) + homolog open. | **Tickmill:** N/A (`last=0`). **XP/B3:** WINQ26, **PETR4**, **DI1F27** live (`run_xp_symbol_quote_trade_confirm.py`, 2026-06-30); `VenueProfile` **TESTED**. **AMP:** MESU26/MNQU26/ENQU26 (`run_amp_symbol_quote_trade_confirm.py`) | `homologation/run_xp_trade_ticks_homologation.py`, `homologation/run_amp_trade_ticks_homologation.py` | **Tickmill = Unsupported.** **XP_B3** and **AMP_US** homologated on exchange futures. |
| Historical trade ticks | **Profile-dependent** | TC-D31 | **Tickmill:** FOREX/CFD rejeitados (`test_tc_d31_*`). **XP_B3** + **AMP_US:** nominais entrega `TradeTick` via fake bridge + homolog. **A05 bounded:** `start/end + limit=0` → `copy_ticks_range(COPY_TICKS_TRADE)` + live routing; empty ndarray → `DataResponse([])`; `None` → `MT5HistoricalDataError` (`test_a05_*`, `test_a05_bounded_*`, Actor/DataEngine `test_a05_actor_*`). **EXTERNAL_RPYC wire:** `MT5_TICKS_V1` brine-safe frame (no `allow_pickle`); MetaTrader5 reconstructs exact local ndarray. **Live AMP ENQU26 (2026-08-10):** A05 bounded PASS on V1 frame (2666 ticks / empty success; flags=2) | **Tickmill:** N/A. **XP/B3:** WINQ26, **PETR4**, **DI1F27** open. **AMP:** MESU26 etc. + **ENQU26 A05/D30/D31 (2026-08-10)**. **bounded A05 real-provider request:** PASS on AMP ENQU26 (V1 frame). **full historical/live stream parity:** FAIL on AMP ENQU26 (2026-08-10) — live=96 vs hist=40 in ~45s capture; see `last_a05_trade_tick_parity_report.json` — blocks B07 warmup | `test_data_tester_matrix_external_rpyc.py::test_tc_d31_*`, `test_a05_bounded_trade_ticks.py`, `test_a05_actor_data_engine_bounded.py`, `test_tick_transport.py`, `homologation/run_amp_a05_bounded.py`, `homologation/run_a05_trade_tick_parity.py` | A05 implementation: deterministic code-complete. A05 bounded real-provider: PASS AMP V1. A05 hist↔live parity: FAIL (count/aggressor divergence). B07 warmup certification: BLOCKED. |
| Bars | Partial | TC-D40, TC-D41, TC-HOM-D03, TC-HOM-D04b | TC-D40: hist `_request_bars` via `copy_rates_*` (wiring + stub e2e + fake-bridge e2e); TC-D41: live subscribe via WS `subscribe_bars` when `feed.enabled` (Tier 1 matrix); TC-HOM-D03 live smoke `homologation/run_bar_smoke.py`; TC-HOM-D04b closed-market `_request_bars` E2E | ✅ **Tickmill:** live M1 bar via WS (BTCUSD, 2026-06-28). **XP/B3:** TC-HOM-D03 (`run_xp_open_market_feed.py`, WDON26 M1, 2026-06-29). **AMP:** TC-HOM-D03 (`run_amp_open_market_feed.py`, MESU26 M1, 2026-07-01) + TC-HOM-D04a/b (`run_amp_closed_market.py`) | `test_data_tester_matrix_external_rpyc.py`, `test_feed_data_client.py`, `homologation/run_bar_smoke.py`, `homologation/run_xp_open_market_feed.py`, `homologation/run_amp_open_market_feed.py`, `homologation/run_amp_closed_market.py` | Live bar subscribe **requires** `feed.enabled=True` + `NT5TickFeedService`. |
| Derivatives data | Unsupported | TC-D50–TC-D53 | N/A | N/A | N/A | Out of scope unless intentionally mapped from real MT5/venue concepts. |
| Instrument status / close | Unsupported | TC-D60, TC-D61 | N/A | N/A | N/A | Conditional only if a reliable MT5-native source is introduced. |
| Option greeks / chain | Unsupported | TC-D62, TC-D63 | N/A | N/A | N/A | Out of scope unless intentionally added. |
| Lifecycle / unsubscribe / custom params | Partial | TC-D70–TC-D72 | TC-D70 Tier 1 matrix. TC-D71/D72 documented unsupported. | ✅ **Tickmill:** TC-HOM-D05 (`run_open_market.py`, 2026-06-28). **XP/B3:** TC-HOM-D05 + D06 gateway + **D06-SVC** (`run_xp_open_market_feed.py`, `run_xp_backlog_homologation.py`, `run_d06_svc_homologation.py`, 2026-06-30) | `homologation/run_open_market.py`, `homologation/run_xp_open_market_feed.py`, `homologation/run_xp_backlog_homologation.py`, `homologation/run_d06_svc_homologation.py` | Quote + bar unsubscribe on stop validated open-market. D06-SVC: manual NT5TickFeedService stop/start + dedup validated XP. |

## Recommended minimum target for `nt_mt5`

A practical minimum target for `nt_mt5` is:
- Group 1: Instruments
- Group 3: Quotes
- Group 4: Trades, if the adapter exposes trade-tick semantics
- Group 5: Bars
- Group 9: Lifecycle/unsubscribe behavior for supported subscriptions

This aligns best with the upstream notion of baseline data compliance being centered on groups 1–4, while also treating bars as a practical core capability for an MT5 adapter.

## Project review checklist

For each supported data capability, confirm all of the following:
- the provider/client path exists in production code;
- the public API documents the capability;
- the unsupported-path behavior is explicit where capability is absent;
- there is at least one deterministic test path covering the behavior;
- the flow is exercised at Nautilus adapter level, not only through wrapper/RPyC calls;
- the `Operational traceability matrix` above is updated.

For each unsupported capability, confirm:
- it is documented as unsupported;
- tests do not falsely imply support;
- the adapter fails safely rather than pretending support exists.

For each partial capability, confirm:
- the missing piece is documented in `Notes`;
- future tests or implementation tasks can identify what must change before it becomes `Supported`.
