# Task Template for AI Coding Agents

Use this template when creating implementation tasks for `nt_mt5`.

The goal is to make each task self-contained while preventing architectural drift across many independent agent contributions.

---

# Task: `<short imperative title>`

## 1. Required context

Before implementing, read:

- `docs/index.md`
- `docs/ai_agent_guidelines.md`
- `docs/adapter_contract.md`
- `docs/terminal_access_contract.md`
- `docs/testing_contract.md`
- `docs/data_capability_matrix.md`
- `docs/execution_capability_matrix.md`
- `docs/terminal_access_capability_audit.md`
- `docs/decisions.md`

If the task involves live MT5/RPyC validation, also read:

- `docs/remote_mt5_test_gateway.md`

If the task changes public examples or usage, also inspect:

- `README.md`
- `examples/`

---

## 2. Objective

Describe the concrete outcome expected from this task.

Example:

```text
Implement deterministic Nautilus-level integration coverage for QuoteTick subscriptions through EXTERNAL_RPYC using the fake RPyC bridge.
```

---

## 3. Background

Explain the context and why this task exists.

Include links or references to relevant docs, code files, tests, issues, or previous decisions.

Example:

```text
The wrapper-level tests already validate `symbol_info_tick`, but they do not prove that `MetaTrader5DataClient` emits Nautilus `QuoteTick` objects through the data client flow.
```

---

## 4. Scope

List what must be changed.

Example:

```text
- Add a Nautilus-level integration test under `tests/integration_tests/adapters/mt5/`.
- Use `MT5LiveDataClientFactory`.
- Use the fake RPyC bridge.
- Verify a `QuoteTick` is emitted.
- Update `docs/data_capability_matrix.md` if status changes.
```

---

## 5. Out of scope

List what must not be changed.

Example:

```text
- Do not add live MT5 dependency.
- Do not change public terminal access modes.
- Do not implement `MANAGED_TERMINAL`.
- Do not change execution behavior.
- Do not mark the capability Supported unless the Nautilus-level test is complete.
```

---

## 6. Files likely to change

List expected files.

Example:

```text
tests/integration_tests/adapters/mt5/test_data_client_external_rpyc.py
tests/integration_tests/adapters/mt5/conftest.py
tests/support/fake_mt5_rpyc_bridge.py
docs/data_capability_matrix.md
```

If production code is expected to change, list those files explicitly.

---

## 7. Contracts that must not be broken

Check all that apply:

- [ ] `EXTERNAL_RPYC` remains the current functional public path.
- [ ] `MANAGED_TERMINAL` remains a future path unless this task explicitly implements it.
- [ ] `DOCKERIZED` remains a backend of `MANAGED_TERMINAL`, not a public access mode.
- [ ] The low-level bridge remains MT5-native.
- [ ] The adapter translates MT5 payloads into Nautilus domain types.
- [ ] Deterministic tests do not require live MT5, network, or external gateway.
- [ ] Unsupported operations fail safely.
- [ ] Capabilities are not marked **Supported** without deterministic coverage.
- [ ] Examples continue to use real public APIs.

Add task-specific invariants:

```text
- ...
```

---

## 8. Implementation requirements

Describe the expected implementation in actionable terms.

Example:

```text
- Reuse the existing fake RPyC bridge.
- Avoid monkeypatching `_cache`, `_clock`, or `_msgbus`.
- Prefer a reusable fixture over repeated local setup.
- Assert observable output rather than log text.
- Use polling with timeout for async effects.
```

---

## 9. Testing requirements

List required tests.

Example:

```text
- Add deterministic integration test for `SubscribeQuoteTicks`.
- Test must fail if the adapter does not emit a Nautilus `QuoteTick`.
- Test must not access `MT5_HOST`, `MT5_PORT`, or other live env vars.
- Run relevant existing tests:
  - pytest tests/unit/
  - pytest tests/integration_tests/adapters/mt5/
```

If live tests are involved:

```text
- Add test under `tests/live/`.
- Mark with `@pytest.mark.live`.
- Mark with `@pytest.mark.external_rpyc`.
- Skip if required env vars are absent.
- Do not submit orders unless `MT5_ENABLE_LIVE_EXECUTION=1`.
```

---

## 10. Documentation requirements

Check all that apply:

- [ ] Update `docs/data_capability_matrix.md`.
- [ ] Update `docs/execution_capability_matrix.md`.
- [ ] Update `docs/terminal_access_capability_audit.md`.
- [ ] Update `docs/decisions.md`.
- [ ] Update `docs/testing_contract.md`.
- [ ] Update `docs/remote_mt5_test_gateway.md`.
- [ ] Update README or examples.
- [ ] No docs update required; explain why.

Explanation:

```text
...
```

---

## 11. Acceptance criteria

The task is complete when:

- [ ] The implementation meets the objective.
- [ ] Required deterministic tests exist and pass.
- [ ] No deterministic test depends on live MT5/RPyC infrastructure.
- [ ] No capability is overstated.
- [ ] Relevant docs are updated.
- [ ] No stable project decision was silently changed.
- [ ] Unsupported paths fail safely.
- [ ] Public examples remain consistent.
- [ ] The final summary mentions any remaining `Partial`, `Unsupported`, or `Planned` behavior.

Add task-specific criteria:

- [ ] ...
- [ ] ...

---

## 12. Final response expected from the agent

The agent should summarize:

```text
- What changed
- Which tests were added or updated
- Which docs were updated
- Which commands were run
- Any known limitations
- Any capability status changes
```

The agent must not claim full NautilusTrader compliance unless the relevant DataTester/ExecTester subset and capability matrix support that claim.

---

# Quick checklist for task authors

Before sending a task to an agent:

- [ ] Is the objective narrow enough?
- [ ] Is the out-of-scope section explicit?
- [ ] Are required docs listed?
- [ ] Are expected tests listed?
- [ ] Are capability matrix updates required when needed?
- [ ] Are live dependencies prohibited or clearly marked?
- [ ] Are acceptance criteria observable?
- [ ] Does the task avoid asking the agent to make architecture decisions silently?
