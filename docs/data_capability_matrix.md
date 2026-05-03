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
| Quote ticks | Partial | TC-D20 | TC-D20 coberto em `test_data_tester_matrix_external_rpyc.py` (subscribe reach) e `test_external_rpyc_data_tester.py` (live bid/ask confirmado) | ✅ Validado live (USTEC bid/ask confirmados; BTCUSD validado em 2026-05-02) | `test_data_tester_matrix_external_rpyc.py`, `test_external_rpyc_data_tester.py` | Fluxo Nautilus-level completo (parsing → cache → handler) ainda não coberto end-to-end. **Comportamento observado**: o primeiro `QuoteTick` recebido após subscribe pode chegar com `bid=0.00 ask=0.00` antes do preço real ser entregue pelo stream (confirmado com BTCUSD/Tickmill-Demo). Estratégias devem ignorar ticks com preço zero antes de operar. |
| Historical quote ticks | Partial | TC-D21 | TC-D21 coberto em `test_data_tester_matrix_external_rpyc.py`: wiring (reach) + end-to-end (`QuoteTick` objects chegam a `_handle_quote_ticks`) + `start=None` usa `tick_capacity` como limit + resultado vazio não chama `_handle_quote_ticks` + `correlation_id` é repassado intacto. | Não — fluxo live via Nautilus-level pendente | `test_data_tester_matrix_external_rpyc.py::test_tc_d21_*` | **Comportamentos cobertos determinísticamente (2026-05-02)**: (1) `start=None` → `limit` substituído por `tick_capacity` (loop roda duas vezes com `request.limit=1`); (2) resultado vazio → `_handle_quote_ticks` não é chamado, adaptador loga warning; (3) `correlation_id` da request é repassado sem alteração. **Nota**: `correlation_id` é `None` no contexto de teste sem DataEngine — comportamento esperado. **Ainda pendente**: fluxo Nautilus-level completo (`_handle_quote_ticks` → msgbus → cache → handler do engine) requer nó live. |
| Trade ticks | Unsupported | TC-D30 | TC-D30 coberto em `test_data_tester_matrix_external_rpyc.py`: rejeição pelo VenueProfile testada (`_subscribe_trade_ticks` não chama `subscribe_ticks`); unknown-instrument path testado; unsubscribe (`unsubscribe_ticks(AllLast)`) testado. | ✅ Confirmado live: `last=0.0` para todos os ticks de CFD/FX index no Tickmill-Demo | `test_data_tester_matrix_external_rpyc.py::test_tc_d30_*` | **Decisão final (2026-05-02): Unsupported.** Enforçado pelo `VenueProfile`: `TICKMILL_DEMO_PROFILE` declara `trade_ticks=UNSUPPORTED` para todos os modos OTC. `_subscribe_trade_ticks` rejeita via `check_capability()` antes de chegar ao cliente MT5. |
| Historical trade ticks | Unsupported | TC-D31 | TC-D31 coberto em `test_data_tester_matrix_external_rpyc.py`: EURUSD (FOREX/`CurrencyPair`) e USTEC (CFDINDEX/`Cfd`) rejeitados pelo VenueProfile antes de `get_historical_ticks`. `parse_instrument()` agora retorna `CurrencyPair` para FOREX com `TICKMILL_DEMO_PROFILE`. | N/A | `test_data_tester_matrix_external_rpyc.py::test_tc_d31_*` | **Bug resolvido (2026-05-02)**: o bloco `isinstance(instrument, CurrencyPair)` em `_request_trade_ticks` era código morto porque `parse_instrument()` sempre retornava `Cfd`. Resolvido com `VenueProfile`: EURUSD é agora `CurrencyPair` (mode=0→FOREX), e ambos EURUSD e USTEC são barrados por `check_capability(calc_mode, "trade_ticks") == UNSUPPORTED`. O bloco dead-code foi substituído pela gate de profile. |
| Bars | Partial | TC-D40, TC-D41 | TC-D40: wiring (reach) + end-to-end (parsing→`Bar`→`_handle_bars`) cobertos em `test_data_tester_matrix_external_rpyc.py`; TC-D41: path histórico (subscribe_historical_bars) + path 5s (subscribe_realtime_bars) cobertos; live M1 e M5 em `test_external_rpyc_data_tester.py` | ✅ Validado live (M1: 5 bars, M5: 10 bars do USTEC) | `test_data_tester_matrix_external_rpyc.py`, `test_external_rpyc_data_tester.py` | TC-D40 end-to-end coberto em 2026-05-02: `_request_bars()` recebe `Bar` objects reais e os despacha para `_handle_bars` (testado com fake USTEC instrument). TC-D41 5s path coberto: bars de 5s usam `subscribe_realtime_bars`, não `subscribe_historical_bars`. Fluxo live completo (parsing → cache → entrega via msgbus) pendente para status `Supported`. |
| Derivatives data | Unsupported | TC-D50–TC-D53 | N/A | N/A | N/A | Out of scope unless intentionally mapped from real MT5/venue concepts. |
| Instrument status / close | Unsupported | TC-D60, TC-D61 | N/A | N/A | N/A | Conditional only if a reliable MT5-native source is introduced. |
| Option greeks / chain | Unsupported | TC-D62, TC-D63 | N/A | N/A | N/A | Out of scope unless intentionally added. |
| Lifecycle / unsubscribe / custom params | Partial | TC-D70–TC-D72 | TC-D70 coberto em `test_data_tester_matrix_external_rpyc.py`: `_unsubscribe_quote_ticks` → `unsubscribe_ticks(BidAsk)`, `_unsubscribe_bars` não-5s → `unsubscribe_historical_bars`, `_unsubscribe_bars` 5s → `unsubscribe_realtime_bars`. TC-D71/D72 documentados como unsupported (sem custom params na API pública). | Pendente | `test_data_tester_matrix_external_rpyc.py::test_tc_d70_*`, `test_tc_d71_*`, `test_tc_d72_*` | Unsubscribe para order book e instruments loga warning e não levanta (já coberto em TC-D10/TC-D02). Custom params explicitamente fora do escopo da API pública. |

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
