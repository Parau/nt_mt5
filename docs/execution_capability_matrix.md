# Execution Capability Matrix

This document translates the NautilusTrader **Execution Testing Spec** into an internal capability matrix for `nt_mt5`.

## Source of truth

Official reference:
- Published docs: https://nautilustrader.io/docs/latest/developer_guide/spec_exec_testing/

Upstream source reference:
- GitHub source: https://github.com/nautechsystems/nautilus_trader/blob/develop/docs/developer_guide/spec_exec_testing.md

If this file conflicts with NautilusTrader's published execution testing spec, the upstream spec wins. Use this file as a project planning and review aid, not as a replacement for the official spec.

## How to use this matrix

- **Required baseline** means the capability should normally be implemented and tested for a useful MT5 execution adapter.
- **Conditional** means it should be implemented and tested only if `nt_mt5` explicitly supports it.
- **Out of scope unless intentionally added** means it should normally be documented as unsupported for `nt_mt5`, unless the project intentionally adds support.
- Every supported capability should map to deterministic tests.
- Every unsupported capability should be denied or rejected safely and documented clearly.

The `Live coverage` column tracks Tier 2 live acceptance results. See `docs/testing_contract.md` — **Two-tier validation strategy** — for the selection criteria and rationale.

## Capability status definitions

Use these status values when tracking actual project support:

- **Supported**: production implementation exists, the Nautilus-level execution flow is exercised, deterministic tests exist, and docs/capability matrix are aligned.
- **Partial**: gateway/wrapper/wiring exists, but Nautilus-level flow, reports, reconciliation, ExecTester coverage, or documentation is incomplete.
- **Unsupported**: not implemented and should be denied, rejected, or documented as unavailable.
- **Planned**: intentionally future work.

A gateway method being available, or `order_send` returning successfully, is not enough to mark a Nautilus execution capability as `Supported`.

## Upstream framing

The NautilusTrader Execution Testing Spec defines a grouped test matrix using `ExecTester`. Each adapter must pass the subset of tests matching its supported capabilities. Adapter-specific behavior such as market-order simulation, time-in-force handling, and order flags should be documented in the adapter guide together with a capability matrix.

## Matrix

| Group | Upstream scope | Representative cases | `nt_mt5` expectation | Notes |
|---|---|---|---|---|
| 1. Market orders | Market buy/sell, IOC/FOK market TIF, quote quantity, close-on-stop | TC-E01–TC-E06 | **Required baseline, except quote quantity unless intentionally supported** | Market order submit/fill and close-on-stop are core for a practical MT5 adapter. Quote-quantity support should only be claimed if intentionally mapped. |
| 2. Limit orders | GTC, IOC, FOK, GTD, DAY, paired limits | TC-E10–TC-E19 | **Required baseline for GTC; conditional for IOC/FOK/GTD/DAY** | At minimum, accepted/open limit orders should work. Extended TIF behavior should only be claimed where the MT5 mapping is real and tested. |
| 3. Stop and conditional orders | Stop-market, stop-limit, MIT, LIT | TC-E20–TC-E27 | **Conditional** | MT5-native stop semantics are relevant; MIT/LIT-style support should only be claimed if there is a real mapping and tests. |
| 4. Order modification | Amend, cancel-replace, modify stop trigger, modify rejected | TC-E30–TC-E36 | **Conditional but strongly preferred** | If the adapter supports amend/replace behavior through MT5 semantics, it should be tested here. If not, safe denial/rejection must be documented. |
| 5. Order cancellation | Single cancel, cancel-all-on-stop, individual cancel, batch cancel, cancel rejection | TC-E40–TC-E44 | **Required baseline for single cancel and stop cleanup** | Cancel behavior and invalid-cancel rejection are core execution behaviors. Batch cancel is conditional. |
| 6. Bracket orders | Entry + TP + SL bracket workflows | TC-E50–TC-E53 | **Out of scope unless intentionally added** | These are advanced contingent workflows and should not be implied unless explicitly implemented and tested. |
| 7. Order flags | Post-only, reduce-only, display quantity, custom order params | TC-E60–TC-E63 | **Conditional** | Only claim flags that are truly supported through MT5-native semantics or a documented adapter mapping. Custom order params are useful for explicit adapter extensions. |
| 8. Rejection handling | Post-only rejection, reduce-only rejection, unsupported order type, unsupported TIF | TC-E70–TC-E73 | **Required baseline for unsupported type/TIF; conditional for flag-specific rejection** | Every adapter should deny unsupported order type and unsupported TIF cleanly before venue submission when possible. |
| 9. Lifecycle / reconciliation | Open-on-start, cancel-on-stop, close-on-stop, unsubscribe-on-stop, reconcile orders/fills/positions | TC-E80–TC-E87 | **Required baseline** | Bootstrap, stop behavior, and reconciliation are central for live execution reliability. |
| 10. Options trading | Option limits, alt pricing, option rejects, option reconciliation | TC-E90–TC-E101 | **Out of scope unless intentionally added** | Only applicable if `nt_mt5` intentionally supports options trading through Nautilus-native execution semantics. |

## Operational traceability matrix

This section tracks the current implementation status. It should be updated whenever a task changes execution behavior, reports, tests, or documented support.

| Capability | Status | Official test IDs | Deterministic coverage | Live coverage | Validated by | Notes |
|---|---|---|---|---|---|---|
| Market orders | **Supported** | TC-E01–TC-E06 | **TC-EL-02**: `test_lifecycle_submit_order_calls_order_send` — `order_send` chamado com parâmetros corretos. **TC-EL-03**: `test_lifecycle_submit_order_generates_submitted_and_accepted` — `OrderSubmitted` + `OrderAccepted` com `venue_order_id` gerados. **TC-EL-07**: `test_lifecycle_submit_order_rejected_on_error_retcode` — retcode de erro → `OrderRejected`. **TC-EL-20**: `test_lifecycle_market_order_fill_end_to_end` (parametrizado BUY/SELL) — cadeia completa `OrderSubmitted → OrderAccepted → OrderFilled` via stub bridge; valida `trade_id`, `venue_order_id`, `last_qty`, `last_px`, `liquidity_side=TAKER`. | **Validado** em Tickmill-Demo USTEC (hedging, IOC fill, 2026-05-01): BUY `retcode=10009`, CLOSE com `position=<ticket>` `retcode=10009`, posições=0. **Validado** em Tickmill-Demo BTCUSD via `TradingNode` (2026-05-03): QuoteTick recebido via polling RPyC → BUY MARKET IOC 0.01 preenchido a 78636.50, SELL MARKET IOC 0.01 preenchido a 78626.50, round-trip completo sem erros — via `examples/exec_smoke_trading_node.py`. MQL5 probe 2026-06-29: Tickmill USTEC/BTCUSD market deals **IOC only** (`type_filling=1`). | `test_execution_lifecycle_external_rpyc.py` + `test_execution_client_external_rpyc.py` | Fill end-to-end determinístico coberto via stub (TC-EL-20). Tickmill market filling: IOC only (`SYMBOL_FILLING_MODE=2`); FOK/RETURN rejected by broker (`OrderCheck` retcode 10030). |
| Limit orders | **Partial** | TC-E10–TC-E19 | **TC-EL-18/19**: GTC limit submit (BUY/SELL). **E06** homologation: IOC passive/aggressive paths. **TC-E73-UNIT** / `validate_filling_mode`: FOK rejected when symbol bitmask lacks FOK bit. | ✅ GTC **E03**; IOC **E06**; DAY passive **E06e**; **E06d** adapter reject on Tickmill IOC-only (`run_wave4_homologation.py`, USTEC/BTCUSD 2026-06-29). MQL5 `OrderCheck` probe 2026-06-29: market FOK/RETURN → `10030 INVALID_FILL`, IOC OK — see `res/tickmill_restrictions.md`. | `test_execution_lifecycle_external_rpyc.py`, `homologation/run_homologation.py`, `tests/unit/test_execution_guards.py` | GTC/IOC/DAY limit homologados (Tickmill). **FOK limit:** supported only when `SYMBOL_FILLING_MODE` includes FOK bit (XP `=3`); Tickmill USTEC/BTCUSD `=2` (IOC only) → pre-venue reject. DAY/GTC limits map to `ORDER_FILLING_RETURN`. GTD/paired limits unsupported. Modify/cancel: **E07** volume+price, **E43** cancel rejection. |
| Stop and conditional orders | **Partial** | TC-E20–TC-E27 | **TC-EL-21/22/23/24**: STOP_MARKET e STOP_LIMIT submit (determinístico). | **TC-LIVE-STOP-01..04** (`test_live_stop_orders.py`); homolog **E02** stop pending; **E07b** BUY_STOP trigger amend (`run_wave4_homologation.py`, 2026-06-28) | `test_execution_lifecycle_external_rpyc.py`, `homologation/scenarios/stop_orders.py` | STOP_MARKET/LIMIT submit + live field validation. **E07b** covers pending BUY_STOP trigger amend. STOP_LIMIT amend e MIT/LIT fora do escopo. |
| Order modification | **Partial** | TC-E30–TC-E36 | **TC-EL-11**: `_modify_order` → `order_send` com `action=7` (TRADE_ACTION_MODIFY). | ✅ **E07** limit volume+price nudge; **E07b** BUY_STOP trigger (`run_wave4_homologation.py`, Tickmill 2026-06-28) | `test_execution_order_commands_external_rpyc.py`, `homologation/scenarios/exec_tester_suite.py` | Volume+price on pending limit (**E07**); stop trigger on pending BUY_STOP (**E07b**). Modify rejected (TC-E33–E36) e STOP_LIMIT amend ainda sem cobertura dedicada. |
| Order cancellation | **Partial** | TC-E40–TC-E44 | **TC-EL-10/12**: single cancel + cancel-all from cache. | ✅ **E03** GTC cancel; **E43** double-cancel → retcode 10013; **E04a** cancel_on_stop (`homologation`, Tickmill 2026-06-28) | `test_execution_order_commands_external_rpyc.py`, `homologation/run_e43_homologation.py` | Single cancel, cancel rejection (**E43**), and cancel-on-stop (**E04a**) homologados. Batch cancel conditional. |
| Bracket orders | Unsupported | TC-E50–TC-E53 | N/A | N/A | N/A | Out of scope unless intentionally implemented and tested. |
| Order flags | Unsupported | TC-E60–TC-E63 | N/A | N/A | N/A | Post-only, reduce-only, display quantity, and custom params must not be implied without real mapping. |
| Unsupported order type | **Supported** | TC-E72 | **TC-EL-07**: `test_lifecycle_submit_order_rejected_on_error_retcode` — retcode de erro do bridge → `OrderRejected` (pós-venue). **TC-EL-13**: `test_lifecycle_submit_order_rejected_for_unsupported_order_type` (parametrizado × 5 tipos) — `validate_order_pre_venue()` rejeitada antes de `order_send` para `MARKET_TO_LIMIT`, `MARKET_IF_TOUCHED`, `LIMIT_IF_TOUCHED`, `TRAILING_STOP_MARKET`, `TRAILING_STOP_LIMIT`. `place_order` não chamado; `OrderRejected` gerado com reason contendo o nome do tipo. | N/A | `test_execution_lifecycle_external_rpyc.py` + `test_mt5_mappings.py` | Guard pré-venue implementado via `validate_order_pre_venue()` em `parsing/execution.py`; chamado no topo de `_submit_order` antes de qualquer chamada ao bridge. |
| Unsupported TIF | **Supported** | TC-E73 | **TC-EL-14**: `test_lifecycle_submit_order_rejected_for_unsupported_tif` (parametrizado × 3 TIFs) — `validate_order_pre_venue()` rejeitada antes de `order_send` para `GTD`, `AT_THE_OPEN`, `AT_THE_CLOSE`. `place_order` não chamado; `OrderRejected` gerado com reason contendo o nome do TIF. **TC-E73-UNIT**: `test_validate_order_pre_venue_rejects_unsupported_tif` em `test_mt5_mappings.py`. **FOK/IOC filling guard**: `validate_filling_mode()` em `test_execution_guards.py`. | Homolog **E06d**: Tickmill IOC-only symbols → adapter reject before `order_send` (expected). XP FOK+IOC symbols → FOK limit submit when bitmask allows. | `test_execution_lifecycle_external_rpyc.py` + `test_mt5_mappings.py` + `tests/unit/test_execution_guards.py` | TIFs suportados no adapter: GTC, DAY, FOK, IOC. `GTD` / session TIFs rejeitados pré-venue. **FOK/IOC** também validados contra `SYMBOL_FILLING_MODE` bitmask — FOK em símbolo IOC-only (Tickmill) rejeitado antes do bridge. |
| Position reports / reconciliation | Partial | TC-E80, TC-E86, TC-E87 | **TC-EL-06**, **TC-EL-01** (determinístico). | ✅ TC-HOM-E05 + E81 via `homologation/run_open_market.py` (Tickmill BTCUSD) | `test_execution_lifecycle_external_rpyc.py`, `homologation/run_open_market.py` | Live mass_status + open-on-start reconcile homologados open-market 2026-06-28. |
| Order reports / reconciliation | Partial | TC-E84, TC-E85 | **TC-EL-08**, **TC-EL-09** (determinístico). | ✅ **E05** mass_status; **E81** pending overlap via `orders_get` (`run_open_market.py` / `run_wave4_homologation.py`, 2026-06-28) | `homologation/run_open_market.py` | Open pending orders via `get_open_orders` → `orders_get` (2026-06-28 fix). Position-inferred reports remain proxy; historical `history_orders_get` not full reconcile. |
| Fill reports | Partial | TC-E85 | **TC-EL-04**, **TC-EL-05** (determinístico). | ✅ TC-HOM-E05b via `run_open_market.py` (eventual consistency Tickmill documentada) | `homologation/run_open_market.py`, `run_e05b_homologation.py` | `history_deals_get` delay no Tickmill confirmado; smoke open-market valida path pós-fill. |
| Lifecycle / stop behavior | **Supported** | TC-E82, TC-E83 | **TC-EL-15/16/17**: cancel_on_stop, close_on_stop, flags false (determinístico). | ✅ **E04** cancel_on_stop + close_on_stop; **E04b** multi-leg close (`homologation`, Tickmill 2026-06-28) | `test_execution_lifecycle_external_rpyc.py`, `homologation/scenarios/mt5_edges.py` | `cancel_on_stop` (default `True`) and `close_on_stop` homologados live. Open-on-start reconcile is **TC-E80** / homolog **E81** (see Position reports row). |
| Options trading | Unsupported | TC-E90–TC-E101 | N/A | N/A | N/A | Out of scope unless intentionally added. |

## Recommended minimum target for `nt_mt5`

A practical minimum target for `nt_mt5` is:
- Group 1: Market orders, except quote-quantity unless explicitly supported
- Group 2: Core limit-order behavior, at least GTC, and any additional TIF that is genuinely mapped and tested
- Group 5: Cancellation behavior
- Group 8: Explicit denial/rejection for unsupported order types and unsupported TIF
- Group 9: Lifecycle, stop behavior, and reconciliation

Stop-order support from Group 3 should be included if it is part of the adapter's real MT5-native execution model.

## Project review checklist

For each supported execution capability, confirm all of the following:
- the behavior exists in production code using MT5-native semantics;
- the public docs list the capability and any caveats;
- deterministic tests cover the supported path;
- reconciliation/report generation is coherent where applicable;
- the flow is exercised at Nautilus adapter level, not only through wrapper/RPyC calls;
- the `Operational traceability matrix` above is updated.

For each unsupported capability, confirm:
- it is documented as unsupported;
- the adapter denies or rejects the request safely;
- tests verify the unsupported-path behavior where Nautilus expects that behavior.

For each partial capability, confirm:
- the missing piece is documented in `Notes`;
- future tests or implementation tasks can identify what must change before it becomes `Supported`.
