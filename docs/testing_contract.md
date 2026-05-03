# Testing Contract

This document defines the testing architecture, invariants, and conventions for `nt_mt5`.
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

## Test categories: current state

The NautilusTrader testing guide identifies: unit, integration, acceptance, performance, property-based, fuzzing, and memory-leak tests. The table below shows which categories `nt_mt5` implements today.

| Category | Status | Location |
|---|---|---|
| Unit tests | Implemented | `tests/unit/` |
| Integration — client layer | Implemented | `tests/integration/` |
| Integration — adapter layer | Implemented | `tests/integration_tests/adapters/mt5/` |
| Contract / invariant tests | Implemented (local addition) | `tests/contracts/` |
| Performance benchmarks | Implemented | `tests/performance/` |
| Memory-stability | Implemented | `tests/memory/` |
| Live acceptance (Tier 2) | Implemented — manual only | `tests/acceptance/` |
| Property-based tests | Not implemented — deferred | — |
| Fuzzing | Not implemented — out of scope | — |

Property-based tests are deferred, not ruled out. Fuzzing is out of scope for this adapter given its I/O-heavy, thin-translation nature.

### Unit tests

Cover small, deterministic logic with no external dependencies:
- instrument parsing (`parse_instrument`, `parse_currency_pair_contract`, `parse_cfd_contract`)
- `sec_type_to_asset_class` and symbol normalization
- `InstrumentId` ↔ `MT5Symbol` conversion
- order transformation and MT5 request building
- execution mapping tables (order type, side, TIF, filling mode)
- account bootstrap logic
- factory/cache key behavior
- config wiring and venue profile declarations

Fixture data for parser tests lives in `tests/test_data/` as real MT5 API payloads captured from a live terminal using `examples/capture_symbol_info_fixtures.py`. Each JSON file records the broker server, MT5 build number, and capture timestamp in its `_comment` field. To refresh fixtures or add new symbols, run the capture script against a live terminal (see `tests/test_data/README.md`).

### Integration tests — client layer (`tests/integration/`)

Test `MetaTrader5Client` directly, below the factory stack, using the fake RPyC bridge or targeted mocks:
- connect / disconnect lifecycle
- symbol detail retrieval
- historical bar and tick requests
- execution submission and result handling

Integration tests must pass through real adapter logic whenever practical. Do not build the final state by hand if the adapter can reach it through its own code paths.

### Integration tests — adapter layer (`tests/integration_tests/adapters/mt5/`)

Test the full Factory → DataClient / ExecClient stack — the canonical NT adapter integration layer:
- factory creates the correct client types and caches the shared `MetaTrader5Client`
- provider loads and parses instruments end-to-end
- data client subscribe / unsubscribe / historical flows
- execution client submit / modify / cancel flows with reconciliation
- error handling and lifecycle events

### Performance tests

Target hot-path adapter logic with lightweight, stable measurements:
- parsing ticks and bars
- transforming orders

Use stable timing and generous thresholds. The goal is regression detection, not micro-benchmark precision.

### Memory-stability tests

Detect unintended growth across repeated cycles:
- connect / disconnect
- subscribe / unsubscribe
- request / completion
- factory/client reuse

Prefer checking real adapter structures and queues over synthetic counters.

## Test rules

### Style (applies to all contributors)

Derived from NautilusTrader guidance:

- Prefer deterministic hand-written fakes/stubs over heavy mocking.
- Use `MagicMock` only when call assertions or complex state simulation are genuinely needed.
- Avoid mocking the object under test.
- Use fixtures and parametrization to reduce duplication.
- Prefer polling helpers over arbitrary sleeps when waiting for async effects.
- Do not assert on log text when observable behavior can be asserted directly.
- Do not end tests with `assert True`.
- Do not hide missing coverage with `pytest.skip(...)` unless the test is truly environment-dependent and a meaningful replacement exists.
- If a new test reveals a production bug, fix the bug and mention it explicitly in the PR.

### Additional rules for coding agents

These rules keep the suite useful across many independent AI-generated changes. They supplement, not replace, the upstream NautilusTrader guidance.

- Do not introduce live MT5, network, or gateway dependencies into deterministic tests.
- Do not patch internals of the object under test.
- Do not use arbitrary sleeps as the primary async synchronization mechanism.
- If a fake is insufficient, improve the fake instead of weakening production code.
- Do not declare a capability `Supported` unless deterministic tests cover it.
- Do not treat wrapper-level RPyC method coverage as proof of Nautilus-level adapter support.
- Do not add production code only to make a mock or fragile test pass.
- If a deterministic test needs MT5-like data, prefer `tests/test_data/` fixtures or the fake bridge over live infrastructure.

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

## Live infrastructure policy

The deterministic test suite is the main regression authority for this project.
Live validation against a real MT5 terminal or an external RPyC gateway is useful, but it is supplementary.

Tests requiring live infrastructure must:
- live under `tests/live/` or be explicitly marked with `@pytest.mark.live`;
- use `@pytest.mark.external_rpyc` when they require a real RPyC gateway;
- use `@pytest.mark.demo_execution` when they may submit demo orders;
- skip when required environment variables are missing;
- never run as part of the default deterministic regression suite;
- require `MT5_ENABLE_LIVE_EXECUTION=1` before sending any order.

Deterministic tests outside `tests/live/` must not read live environment variables such as:
- `MT5_HOST`
- `MT5_PORT`
- `MT5_ACCOUNT_NUMBER`
- `MT5_PASSWORD`
- `MT5_ENABLE_LIVE_EXECUTION`

## Two-tier validation strategy

The test suite is organized into two tiers with complementary, non-overlapping purposes.

### Tier 1 — Deterministic (always runs)

| Attribute | Detail |
|---|---|
| Location | `tests/unit/`, `tests/integration/`, `tests/integration_tests/`, `tests/contracts/`, `tests/performance/`, `tests/memory/` |
| Infrastructure | Fake RPyC bridge (`tests/support/fake_mt5_rpyc_bridge.py`) or mocks |
| Runs in CI | Yes — no external dependencies |
| Purpose | Regression protection, Nautilus contract validation, adapter wiring |

Tier 1 covers the full lifecycle of every supported capability through the real adapter code path, using a deterministic fake that returns controlled retcodes and order results. The fake bridge must be kept accurate: when a real MT5 field name or behavior changes, the fake must be updated to match.

### Tier 2 — Live acceptance (manual / on-demand)

| Attribute | Detail |
|---|---|
| Location | `tests/acceptance/` (live-marked files) |
| Infrastructure | Real MT5 terminal, real RPyC bridge, Tickmill-Demo account |
| Runs in CI | No — requires `MT5_ENABLE_LIVE_EXECUTION=1` and live MT5 |
| Purpose | Catch what the fake bridge cannot: real MT5 field validation, real retcodes, real price constraints, transport lag |

Tier 2 tests are **not** a duplicate of Tier 1. Each live test must justify its existence by covering something the fake bridge structurally cannot:

| What live tests cover | Why the fake cannot cover it |
|---|---|
| Real MT5 field validation (e.g., correct `order_send` key names) | Fake bridge accepts any dict key without complaint |
| Real retcodes (10016 invalid stops, 10014 invalid volume, 10019 no money) | Fake always returns configured success retcodes |
| Real price constraints (stop above/below market, stoplimit relationship) | Fake does not validate price levels against live market |
| Real `type_filling` compatibility per broker/symbol | Fake does not check filling mode availability |
| Transport timeout and RPyC lag under real network conditions | Fake is local in-process with no network |
| Reconciliation against real open orders and positions on connect | Fake state is constructed, not real MT5 account state |

**The `stoplimit` bug (2026-05-03) is the canonical example of Tier 2 value**: all Tier 1 tests passed with the wrong field name `stpx` because the fake bridge accepted any key. Only running TC-LIVE-STOP-03/04 against real MT5 revealed that the correct key is `stoplimit`.

### Selection criteria for Tier 2 tests

Add a live acceptance test when **all** of the following are true:

1. There is a corresponding Tier 1 test that passes deterministically.
2. The live test exercises at least one thing the fake bridge cannot validate (see table above).
3. The test is self-contained and cleans up after itself (cancels pending orders, closes positions).
4. The test passes on a known-good Tickmill-Demo connection before being committed.

Do **not** add a live test merely because it is important or interesting — if the fake bridge can cover it adequately, Tier 1 is the right place.

### Current Tier 2 coverage

| File | Tests | What Tier 1 cannot cover |
|---|---|---|
| `tests/acceptance/test_live_stop_orders.py` | TC-LIVE-STOP-01..04 | Real price validation for stop orders; correct `stoplimit` field name; `type_filling` compatibility on BTCUSD at Tickmill |
| `tests/acceptance/test_live_acceptance.py` | Market order round-trip | Real BTCUSD fill against live market; venue_order_id assigned by real MT5 |
| `tests/acceptance/test_live_hedging.py` | Hedging position mode | Real hedging semantics on Tickmill-Demo (position ticket, close-by-ticket path) |

## Directory layout

The `tests/` tree has a fixed, documented layout. Each directory has a single, well-defined semantic. A contract test enforces this layout and will fail if an undocumented directory is introduced.

| Directory | Layer tested | Infrastructure | Runs in CI |
|---|---|---|---|
| `tests/unit/` | Pure logic (parsing, transforms, config, cache keys) | No external dependencies | Yes |
| `tests/integration/` | `MetaTrader5Client` internals (connect, subscribe, historical, execution) | Fake RPyC bridge or mocks | Yes |
| `tests/integration_tests/adapters/mt5/` | Factory → DataClient / ExecClient stack (canonical NT adapter layer) | Fake RPyC bridge or mocks | Yes |
| `tests/acceptance/` | **Tier 2 live only** — real MT5 terminal; all files must be `test_live_*.py` marked `@pytest.mark.live` | Real MT5 + real RPyC gateway | No (manual) |
| `tests/contracts/` | Architectural invariants expressed as executable tests | Reads source files only | Yes |
| `tests/performance/` | Hot-path adapter benchmarks; stable timing; generous thresholds | Mocks or fake bridge | Yes |
| `tests/memory/` | Unintended growth across connect/disconnect/subscribe cycles | Real adapter structures | Yes |
| `tests/support/` | Shared test infrastructure (fake bridge, harnesses, helpers); not a test suite itself | N/A | N/A |
| `tests/live/` | Raw bridge tests without the adapter stack (RPyC only; `@pytest.mark.live`) | Real MT5 + real RPyC gateway | No (manual) |
| `tests/test_data/` | Static JSON fixture files with **real MT5 API payloads** captured via `examples/capture_symbol_info_fixtures.py`; consumed by unit tests for direct parser testing; contains no `test_*.py` files | N/A | N/A |

### Layer decision rules

Use the following rules to decide where a new test belongs:

1. **No external state needed, logic only** → `tests/unit/`
2. **Tests `MetaTrader5Client` directly** (below the factory stack, above raw RPyC) → `tests/integration/`
3. **Tests via `MT5LiveDataClientFactory` or `MT5LiveExecClientFactory`** → `tests/integration_tests/adapters/mt5/`
4. **Validates a doc/config/source invariant by reading files** → `tests/contracts/`
5. **Requires real MT5 to cover something the fake bridge structurally cannot** → `tests/acceptance/` (must be `test_live_*.py`, must have `@pytest.mark.live`)
6. **Measures execution time or memory growth** → `tests/performance/` or `tests/memory/`
7. **Shared helpers, fakes, harnesses** → `tests/support/` (not `test_*.py` unless the helper itself is the subject, e.g., `test_fake_mt5_rpyc_bridge.py`)
8. **Static JSON/fixture data for direct parser testing** → `tests/test_data/` (no Python test files; consumed by `tests/unit/`)

### Protected invariants (enforced by tests/contracts/)

- `tests/acceptance/` contains only `test_live_*.py` files, all marked `@pytest.mark.live`.
- No deterministic test reads live environment variables (`MT5_HOST`, `MT5_ACCOUNT_NUMBER`, etc.).
- No bare `assert True` anywhere in the test suite.
- No monkeypatching of Nautilus internal attributes (`_cache`, `_clock`, `_msgbus`).
- `tests/contracts/` itself exists and is non-empty.
- The set of top-level subdirectories of `tests/` matches the documented layout exactly.
- `tests/test_data/` contains no `test_*.py` files (it is a data directory, not a test suite).
