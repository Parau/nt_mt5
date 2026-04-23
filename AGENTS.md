# AGENTS.md

## 1) Project context
- `nt_mt5` is a NautilusTrader adapter for MetaTrader 5.
- The adapter must translate MT5-native APIs into NautilusTrader's unified interface and normalized domain model.
- The project should follow NautilusTrader's adapter guidance: a clear adapter boundary, a layered design, explicit capability handling, runnable examples, and meaningful automated tests.
- The canonical venue is always `METATRADER_5`.

## 2) Architecture and stable project decisions
- Follow NautilusTrader's layered adapter model:
  - low-level transport, networking, parsing, and bridge concerns in the client layer;
  - Python adapter layer for `DataClient`, `ExecutionClient`, provider, configs, and factories.
- Keep the bridge MT5-native. Do not reintroduce Interactive Brokers semantics, naming, or event models.
- Prefer direct MT5 concepts and APIs such as `account_info`, `terminal_info`, `symbol_info`, `symbols_get`, `symbol_info_tick`, `copy_ticks*`, `copy_rates*`, `orders_get`, `positions_get`, `history_orders_get`, `history_deals_get`, `order_check`, and `order_send`.
- Translate MT5 -> Nautilus at the adapter boundary. Do not leak bridge-specific, RPyC-specific, or mock-specific objects across the codebase.
- `METATRADER_5` is the structural venue everywhere.
- Broker/server/account details belong in instrument/account metadata, not in venue identity.
- `config.account_id` is the source of truth for validating the MT5 login.
- Nautilus `AccountId` is structural engine identity and must not be parsed to recover the MT5 login.
- The adapter must follow the modern NautilusTrader message contracts for data and execution clients.
- Unsupported operations must fail safely: log a warning or return a controlled empty/unsupported result. Do not raise raw `NotImplementedError` on operational paths.
- Do not reopen these decisions unless a real bug proves they are wrong.

## 3) Production-code rules
- Do not add production logic only to make tests pass.
- Do not add fake-success paths, mock fallbacks, or placeholder terminal/account states that hide real failures.
- Do not reintroduce legacy or hybrid interfaces once a modern typed interface exists.
- Prefer small, explicit fixes over broad redesigns.
- Keep production behavior aligned with actual MT5 capabilities and actual NautilusTrader contracts.
- If a test reveals a real production bug, fix the bug instead of weakening the test.

## 4) Testing rules
- Follow NautilusTrader testing intent and Phase 7 expectations: maintain meaningful unit, integration, acceptance/smoke, performance, and memory-stability coverage.
- Before changing supported/unsupported behavior or test scope, consult:
  - `docs/adapter_contract.md`
  - `docs/testing_contract.md`
  - `docs/data_capability_matrix.md`
  - `docs/execution_capability_matrix.md`
  - `docs/decisions.md`
- Prefer deterministic fakes/stubs over heavy mocking.
- Use mocks only where they keep the test focused; do not replace most of the adapter with mocks and still call it integration coverage.
- Integration tests should pass through real adapter logic whenever practical.
- Acceptance/smoke tests should validate public wiring and runnable examples without depending on external MT5 infrastructure unless the task explicitly requires live testing.
- Do not end tests with `assert True`.
- Do not use `pytest.skip(...)` to hide missing coverage unless the test is genuinely environment-dependent and a replacement exists.
- Performance tests should use lightweight, stable timing with generous thresholds and should measure real adapter logic, not only mock overhead.
- Memory-stability tests should watch real adapter structures for unintended growth across repeated cycles.
- Organize tests clearly by purpose whenever practical, and prefer reusable fixtures and parametrization over copy-pasted cases.

## 5) Documentation and examples
- Examples must reflect the real public API exactly.
- README, metadata, configs, factories, exports, and examples must stay mutually consistent.
- Keep docs concise, direct, and easy to maintain.
- Document adapter-specific capability limits and behavior clearly, especially supported order types, time-in-force rules, historical/live data support, and unsupported features.
- When compatibility choices are intentional, document them explicitly instead of leaving them implicit.
- Keep these project docs aligned with implementation, tests, and documented support limits:
  - `docs/adapter_contract.md`
  - `docs/testing_contract.md`
  - `docs/data_capability_matrix.md`
  - `docs/execution_capability_matrix.md`
  - `docs/decisions.md`

## 6) PR rules for coding agents
- Stay inside the requested scope.
- Do not declare the work done if core acceptance criteria are still open.
- Do not mix unrelated cleanups into a focused task.
- In each PR, include:
  - a short itemized summary of what changed;
  - the files changed;
  - tests added or updated;
  - any real bug fixes discovered while implementing the task;
  - any intentionally deferred items.
- Separate implementation fixes from test-only fixes.
- If a test reveals a production bug, fix the bug and mention it explicitly.
- If coverage is still partial, say so clearly instead of implying the task is fully complete.
