# Testing Contract

This document defines the minimum testing expectations for `nt_mt5`.
It is derived from the NautilusTrader testing guide and adapter/testing specs and should be read together with the upstream references below.

## Source of truth

Official upstream references:
- Published docs: https://nautilustrader.io/docs/latest/developer_guide/testing
- Published docs: https://nautilustrader.io/docs/latest/developer_guide/adapters
- Published docs: https://nautilustrader.io/docs/latest/developer_guide/spec_data_testing
- Published docs: https://nautilustrader.io/docs/latest/developer_guide/spec_exec_testing

Optional upstream source references:
- Repository docs root: https://github.com/nautechsystems/nautilus_trader/tree/develop/docs
- Repository developer guide directory: https://github.com/nautechsystems/nautilus_trader/tree/develop/docs/developer_guide

If this document conflicts with upstream guidance, upstream wins unless `docs/decisions.md` records an explicit local project decision.

## Test suite purpose

Tests are executable specifications.
For this adapter, the suite must do three things:

- protect correctness of MT5 -> Nautilus translation
- protect public adapter wiring and lifecycle behavior
- catch regressions without depending on unstable external environments by default

## Required test categories

NautilusTrader's testing guide identifies these categories:
- unit tests
- integration tests
- acceptance tests
- performance tests
- property-based tests
- fuzzing
- memory leak tests

`nt_mt5` does not need to implement every category at the same depth immediately, but the suite should evolve toward that model.

## Minimum expectations for this project

### Unit tests
Use unit tests for small, deterministic logic such as:
- symbol normalization
- `InstrumentId` conversion
- order transformation
- MT5 request building
- parsing of bars, ticks, orders, deals, and positions
- account bootstrap logic
- factory/cache key behavior

### Integration tests
Integration tests should exercise public adapter behavior against deterministic fake infrastructure.
Preferred targets:
- provider load flows
- data client connect / disconnect
- subscribe / unsubscribe behavior
- historical request flows
- execution submit / modify / cancel flows
- reconciliation and report generation
- error handling and retry-related behavior where applicable

Integration tests should pass through real adapter logic whenever practical.
Avoid building the final state by hand if the adapter can reach it through its own code paths.

### Acceptance / smoke tests
Acceptance tests should validate the public surface:
- example wiring
- factory wiring
- config coherence
- provider / client creation
- adapter startup shape for supported flows

These tests do not need to use live MT5 by default.

### Performance tests
Performance tests should target hot-path adapter logic with lightweight, stable measurements.
Good candidates:
- parsing ticks
- parsing bars
- transforming orders
- generating reports

Use stable timing and generous thresholds.
The goal is regression detection, not micro-benchmark perfection.

### Memory-stability tests
Memory-oriented tests should detect unintended growth across repeated cycles such as:
- connect / disconnect
- subscribe / unsubscribe
- request / completion
- factory/client reuse

Prefer checking real adapter structures and queues over synthetic counters.

## Test style rules

Derived from NautilusTrader guidance:

- Prefer deterministic hand-written fakes/stubs over heavy mocking.
- Use `MagicMock` only when call assertions or complex state simulation are genuinely needed.
- Avoid mocking the object under test.
- Use fixtures and parametrization to reduce duplication.
- Prefer polling helpers over arbitrary sleeps when waiting for async effects.
- Do not assert on log text when observable behavior can be asserted directly.

## Rules for this project

- Do not end tests with `assert True`.
- Do not add production logic only to accommodate mocks.
- Do not hide missing coverage with `pytest.skip(...)` unless the test is truly environment-dependent and a meaningful replacement exists.
- Do not rely on MT5 real/network access for the main regression suite.
- If a new test reveals a production bug, fix the bug and mention it explicitly in the PR.

## Adapter-spec alignment

### Data testing
Use the NautilusTrader Data Testing Spec as the checklist for supported data capabilities.
Each adapter must pass the subset of data tests matching its supported data types.
For `nt_mt5`, document unsupported data capabilities rather than silently pretending support exists.

Use `docs/data_capability_matrix.md` as the operational checklist for:
- which data-capability groups are currently in scope for `nt_mt5`
- which capabilities are intentionally unsupported
- which gaps should be treated as missing implementation versus out of scope

### Execution testing
Use the NautilusTrader Execution Testing Spec as the checklist for supported execution capabilities.
Cover the subset of order lifecycle and account-state flows that MT5 supports through this adapter.
Document unsupported capabilities clearly.

Use `docs/execution_capability_matrix.md` as the operational checklist for:
- which execution-capability groups are currently in scope for `nt_mt5`
- which capabilities are intentionally unsupported
- which gaps should be treated as missing implementation versus out of scope

## Practical layout

Keep test organization readable. A structure like this is preferred when practical:

- `tests/unit/`
- `tests/integration/`
- `tests/acceptance/`
- `tests/performance_tests/`
- `tests/memory/`

The exact tree may evolve, but category intent should remain obvious.
