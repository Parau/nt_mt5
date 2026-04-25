# Contract Tests Plan

**Purpose:** define a future `tests/contracts/` suite that converts the most important project documentation rules into executable checks.

This document is a plan. It does not implement the tests yet.

The goal is to make architectural drift detectable when many independent AI agents contribute changes over time.

---

## 1. Why contract tests are needed

The project already has strong documentation:

- `docs/adapter_contract.md`
- `docs/terminal_access_contract.md`
- `docs/testing_contract.md`
- `docs/data_capability_matrix.md`
- `docs/execution_capability_matrix.md`
- `docs/terminal_access_capability_audit.md`
- `docs/decisions.md`
- `docs/remote_mt5_test_gateway.md`

However, documentation alone is not enough. Agents can miss, reinterpret, or partially apply written guidance.

Contract tests should protect the most important invariants automatically.

---

## 2. Proposed layout

```text
tests/
  contracts/
    test_terminal_access_contract.py
    test_capability_matrix_contract.py
    test_docs_examples_contract.py
    test_live_tests_contract.py
    test_testing_contract.py
    test_decisions_contract.py
```

These tests should be lightweight and deterministic. They should not require MT5, RPyC, network access, or live credentials.

---

## 3. Test file: `test_terminal_access_contract.py`

### Purpose

Protect the public terminal access model.

### Protected docs

- `docs/terminal_access_contract.md`
- `docs/adapter_contract.md`
- `docs/decisions.md`

### Invariants

- `MT5TerminalAccessMode` contains `EXTERNAL_RPYC`.
- `MT5TerminalAccessMode` contains `MANAGED_TERMINAL`.
- `MT5TerminalAccessMode` does not contain `DOCKERIZED`.
- `DOCKERIZED` appears only as a `ManagedTerminalBackend` or equivalent internal backend.
- `EXTERNAL_RPYC` requires an `external_rpyc` config block.
- `EXTERNAL_RPYC` rejects `managed_terminal`.
- `MANAGED_TERMINAL` requires a `managed_terminal` config block.
- `MANAGED_TERMINAL` rejects `external_rpyc`.
- Top-level `dockerized_gateway` is rejected as a legacy public path.
- `MANAGED_TERMINAL` raises a controlled explicit error while unimplemented.
- `EXTERNAL_RPYC` does not start or manage terminal/gateway lifecycle.

### Example test names

```text
test_terminal_access_modes_are_stable
test_dockerized_is_not_public_terminal_access_mode
test_external_rpyc_requires_external_config
test_external_rpyc_rejects_managed_terminal_config
test_managed_terminal_requires_managed_config
test_managed_terminal_rejects_external_rpyc_config
test_legacy_dockerized_gateway_is_rejected
test_managed_terminal_unimplemented_error_is_controlled
```

---

## 4. Test file: `test_capability_matrix_contract.py`

### Purpose

Prevent unsupported or partial capabilities from being silently promoted.

### Protected docs

- `docs/data_capability_matrix.md`
- `docs/execution_capability_matrix.md`
- `docs/terminal_access_capability_audit.md`

### Invariants

- Capability matrices use only allowed status values:
  - `Supported`
  - `Partial`
  - `Unsupported`
  - `Planned`
- Every `Supported` capability has:
  - official test IDs where applicable;
  - deterministic coverage;
  - a `Validated by` entry or equivalent;
  - notes if behavior is MT5-specific.
- `Supported` must not appear with `N/A`, `pending`, or blank deterministic coverage.
- `Partial` capabilities must include notes describing the missing piece.
- Unsupported capabilities must not appear as supported in examples.
- Data capabilities include a row or section for:
  - instruments,
  - quotes,
  - trades,
  - bars,
  - order book,
  - lifecycle/unsubscribe.
- Execution capabilities include a row or section for:
  - market orders,
  - limit orders,
  - cancel orders,
  - unsupported order type,
  - unsupported TIF,
  - fill reports,
  - reconciliation.
- `terminal_access_capability_audit.md` must state that gateway method availability is not equivalent to Nautilus capability support.

### Example test names

```text
test_capability_matrices_use_allowed_status_values
test_supported_data_capabilities_have_deterministic_coverage
test_supported_execution_capabilities_have_deterministic_coverage
test_partial_capabilities_have_notes
test_data_matrix_tracks_trade_ticks_explicitly
test_execution_matrix_tracks_unsupported_type_and_tif
test_terminal_access_audit_distinguishes_rpc_from_capability
```

---

## 5. Test file: `test_docs_examples_contract.py`

### Purpose

Ensure public examples and docs remain aligned with the project architecture.

### Protected docs

- `docs/adapter_contract.md`
- `docs/terminal_access_contract.md`
- `docs/remote_mt5_test_gateway.md`
- `README.md`
- `examples/`

### Invariants

- Public examples for current usage use `MT5TerminalAccessMode.EXTERNAL_RPYC`.
- Public examples do not promote `dockerized_gateway` as the primary path.
- README does not list `MT5TerminalAccessMode.DOCKERIZED`.
- README documents `MANAGED_TERMINAL` as planned or not yet operational.
- Examples that use `MANAGED_TERMINAL` clearly state that it is placeholder/future if backend is unimplemented.
- Examples that may execute orders require explicit opt-in.
- `.env.example` or equivalent documents required environment variables.
- Docs do not present live gateway validation as the source of truth for regression.

### Example test names

```text
test_readme_does_not_promote_dockerized_as_public_mode
test_external_rpyc_example_uses_current_public_path
test_managed_terminal_example_is_marked_planned_or_placeholder
test_examples_do_not_use_legacy_dockerized_gateway_as_primary_path
test_execution_examples_require_explicit_opt_in
```

---

## 6. Test file: `test_live_tests_contract.py`

### Purpose

Keep live tests optional, safe, and separate from deterministic regression.

### Protected docs

- `docs/testing_contract.md`
- `docs/remote_mt5_test_gateway.md`
- `docs/ai_agent_guidelines.md`

### Invariants

- Tests under `tests/live/` are marked with `@pytest.mark.live`.
- Tests that use a real RPyC gateway are marked with `@pytest.mark.external_rpyc`.
- Tests that may submit orders are marked with `@pytest.mark.demo_execution`.
- Live execution tests require `MT5_ENABLE_LIVE_EXECUTION=1`.
- Live tests skip when required environment variables are missing.
- Deterministic tests outside `tests/live/` do not read:
  - `MT5_HOST`
  - `MT5_PORT`
  - `MT5_ACCOUNT_NUMBER`
  - `MT5_PASSWORD`
  - `MT5_ENABLE_LIVE_EXECUTION`
- No deterministic test opens a real RPyC connection unless patched to fake infrastructure.

### Example test names

```text
test_live_tests_are_marked_live
test_external_rpyc_live_tests_are_marked_external_rpyc
test_demo_execution_tests_require_opt_in
test_non_live_tests_do_not_read_live_env_vars
```

---

## 7. Test file: `test_testing_contract.py`

### Purpose

Protect test quality rules.

### Protected docs

- `docs/testing_contract.md`
- `docs/ai_agent_guidelines.md`

### Invariants

- No tests end with `assert True`.
- Deterministic tests do not rely on raw sleeps where a helper/polling pattern is expected.
- Tests do not assert exact log text when behavior can be observed.
- Known forbidden monkeypatch patterns are absent or explicitly justified.
- Integration tests prefer real adapter flows over manually injected final state.

### Suggested static checks

These checks can start simple:

- text scan for `assert True`;
- text scan for `caplog.text` or exact log message assertions;
- text scan for monkeypatching `_cache`, `_clock`, `_msgbus`;
- text scan for `asyncio.sleep` in integration tests, with allowlist if needed.

### Example test names

```text
test_no_assert_true_in_tests
test_no_known_internal_monkeypatch_patterns
test_no_live_env_access_in_deterministic_tests
test_async_sleep_usage_is_allowlisted
```

---

## 8. Test file: `test_decisions_contract.py`

### Purpose

Ensure stable project decisions are visible and not silently contradicted.

### Protected docs

- `docs/decisions.md`
- `docs/adapter_contract.md`
- `docs/terminal_access_contract.md`

### Invariants

- `docs/decisions.md` contains decisions for:
  - canonical venue identity;
  - account validation source;
  - MT5-native bridge shape;
  - terminal access model;
  - ready-state semantics.
- If `MANAGED_TERMINAL` appears in examples/docs, docs must state current implementation status.
- If a capability matrix marks a major feature as `Supported`, the decision docs must not contradict it.

### Example test names

```text
test_decisions_document_core_project_decisions
test_terminal_access_decision_matches_contract
test_decisions_do_not_contradict_capability_matrices
```

---

## 9. Implementation phases

### Phase 1 — read-only static contract tests

Implement tests that inspect docs, README, examples, and test files as text.

Recommended first tests:

```text
test_dockerized_is_not_public_terminal_access_mode
test_readme_does_not_promote_dockerized_as_public_mode
test_capability_matrices_use_allowed_status_values
test_live_tests_are_marked_live
test_no_assert_true_in_tests
```

### Phase 2 — import-level contract tests

Import project enums/configs/factories and verify public API invariants.

Recommended tests:

```text
test_terminal_access_modes_are_stable
test_external_rpyc_requires_external_config
test_managed_terminal_unimplemented_error_is_controlled
```

### Phase 3 — behavior-level contract tests

Use deterministic fake bridge and existing factory paths to verify behavior.

Recommended tests:

```text
test_external_rpyc_does_not_use_managed_lifecycle
test_supported_capabilities_have_nautilus_level_tests
```

---

## 10. Acceptance criteria for this plan

This plan is complete when:

- It lists the first contract test files to create.
- It maps each contract test area to the docs it protects.
- It defines invariants around terminal access, capabilities, examples, live tests, and testing quality.
- It separates static checks from import-level and behavior-level checks.
- It does not require MT5 real or live RPyC infrastructure.

---

## 11. Long-term goal

The long-term goal is to make this true:

```text
If an AI agent accidentally changes the project direction,
a contract test fails before the drift becomes embedded.
```

Contract tests do not replace human review or architectural documentation. They make the most important rules executable.
