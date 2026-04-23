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
- reconciliation/report generation is coherent where applicable.

For each unsupported capability, confirm:
- it is documented as unsupported;
- the adapter denies or rejects the request safely;
- tests verify the unsupported-path behavior where Nautilus expects that behavior.
