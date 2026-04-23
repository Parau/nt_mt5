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
- there is at least one deterministic test path covering the behavior.

For each unsupported capability, confirm:
- it is documented as unsupported;
- tests do not falsely imply support;
- the adapter fails safely rather than pretending support exists.
