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
| Market orders | Partial | TC-E01–TC-E06 | Wrapper/fake `order_send` coverage exists; full Nautilus event lifecycle still needs explicit coverage | Demo smoke pending | `tests/integration/test_external_rpyc_execution_flow.py` and future ExecTester subset | Do not mark `Supported` until lifecycle such as submitted/accepted/filled or equivalent reports is tested. |
| Limit orders | Partial | TC-E10–TC-E19 | Partial wiring coverage; full order status lifecycle pending | Pending | Future `test_execution_lifecycle_external_rpyc.py` | GTC support should be proven before extended TIFs are claimed. |
| Stop and conditional orders | Planned | TC-E20–TC-E27 | Pending | Pending | N/A | Add only if MT5-native mapping is explicit and tested. |
| Order modification | Unsupported | TC-E30–TC-E36 | N/A | N/A | N/A | If added later, must be tested through MT5-native semantics and Nautilus command/report flow. |
| Order cancellation | Partial | TC-E40–TC-E44 | Some cancel wiring may exist; lifecycle, invalid cancel, and stop cleanup need explicit coverage | Pending | Future execution lifecycle tests | Single cancel and stop cleanup are baseline targets. |
| Bracket orders | Unsupported | TC-E50–TC-E53 | N/A | N/A | N/A | Out of scope unless intentionally implemented and tested. |
| Order flags | Unsupported | TC-E60–TC-E63 | N/A | N/A | N/A | Post-only, reduce-only, display quantity, and custom params must not be implied without real mapping. |
| Unsupported order type | Planned | TC-E72 | Pending | N/A | Future deterministic rejection tests | Must reject safely before venue submission when possible. |
| Unsupported TIF | Planned | TC-E73 | Pending | N/A | Future deterministic rejection tests | Must reject safely before venue submission when possible. |
| Position reports / reconciliation | Partial | TC-E80, TC-E86, TC-E87 | `positions_get` fake/wrapper coverage exists; Nautilus reconciliation flow needs explicit coverage | Pending | `tests/integration/test_external_rpyc_execution_flow.py` and future ExecTester subset | Open long/short support should match actual MT5/venue capability. |
| Order reports / reconciliation | Partial | TC-E84, TC-E85 | `history_orders_get` coverage exists; Nautilus reconciliation flow needs explicit coverage | Pending | Future execution lifecycle tests | Must distinguish raw history availability from Nautilus report generation. |
| Fill reports | Partial | TC-E85 | `history_deals_get` coverage exists; `FillReport` generation is pending or incomplete | Pending | Future `generate_fill_reports` tests | Preferred source is `history_deals_get` / `history_deals_total`. |
| Lifecycle / stop behavior | Partial | TC-E81, TC-E82, TC-E83 | Partial connection/disconnection coverage exists; cancel-on-stop, close-on-stop, unsubscribe-on-stop need explicit coverage | Pending | Future ExecTester subset | Required before claiming broad execution compliance. |
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
