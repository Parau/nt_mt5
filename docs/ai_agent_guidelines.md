# AI Agent Guidelines for `nt_mt5`

**Purpose:** provide mandatory guidance for AI coding agents working on the `nt_mt5` MetaTrader 5 adapter for NautilusTrader.

This project is expected to evolve through many small tasks implemented by different agents. These guidelines exist to prevent architectural drift, inconsistent terminology, fragile tests, and unsupported capabilities being accidentally promoted as supported.

---

## 1. Read this before changing code

Before implementing any task, read these documents in this order:

1. `docs/index.md`
2. `docs/ai_agent_guidelines.md`
3. `docs/adapter_contract.md`
4. `docs/terminal_access_contract.md`
5. `docs/testing_contract.md`
6. `docs/data_capability_matrix.md`
7. `docs/execution_capability_matrix.md`
8. `docs/terminal_access_capability_audit.md`
9. `docs/decisions.md`

If your task changes public behavior, capability status, execution semantics, data semantics, terminal access, or testing strategy, update the relevant documentation in the same task.

---

## 2. Source of truth hierarchy

Use this hierarchy when resolving conflicts:

1. Official NautilusTrader behavior and interface contracts.
2. Local project decisions in `docs/decisions.md`.
3. Project contracts:
   - `docs/adapter_contract.md`
   - `docs/terminal_access_contract.md`
   - `docs/testing_contract.md`
4. Capability matrices:
   - `docs/data_capability_matrix.md`
   - `docs/execution_capability_matrix.md`
5. Operational documents and examples.

If a local document conflicts with official NautilusTrader behavior, upstream NautilusTrader wins unless `docs/decisions.md` records a deliberate local decision.

---

## 3. Non-negotiable architectural rules

### Terminal access

- `EXTERNAL_RPYC` is the currently supported public terminal access path.
- `MANAGED_TERMINAL` is a public future path and must fail with a controlled, explicit error until implemented.
- `DOCKERIZED` is not a top-level public terminal access mode.
- `DOCKERIZED` is only a future backend strategy inside `MANAGED_TERMINAL`.
- `EXTERNAL_RPYC` must not start, supervise, or stop the MT5 terminal or gateway process.
- `EXTERNAL_RPYC` controls only the adapter connection to an already-running external gateway.

### Bridge and adapter boundaries

- Keep the low-level bridge MT5-native.
- Do not wrap MT5 behavior in Interactive Brokers terminology or flow shape.
- Translate MT5 payloads into Nautilus domain types at the adapter boundary.
- Do not leak RPyC netrefs, bridge-only objects, mock-only objects, or raw MT5 payloads across the adapter boundary.
- Do not add generic abstractions that obscure MT5-native semantics unless there is a documented reason.

### Venue and identity

- The canonical venue is `METATRADER_5`.
- Broker, server, and account metadata must not become the structural venue.
- `config.account_id` is the source of truth for validating the MT5 login.
- Do not parse Nautilus `AccountId` to recover the MT5 login.

---

## 4. Capability support rules

A gateway method is not the same thing as a supported Nautilus capability.

A capability can be marked **Supported** only when all of these are true:

1. Production code implements the behavior.
2. The behavior passes through the Nautilus-level adapter flow, not only the wrapper.
3. A deterministic test covers the behavior.
4. The relevant capability matrix is updated.
5. Documentation describes the capability and its limitations.

Use these statuses consistently:

- **Supported**: production behavior + Nautilus-level flow + deterministic coverage + docs.
- **Partial**: gateway/wrapper/wiring exists, but Nautilus-level flow, reports, tester coverage, or docs are incomplete.
- **Unsupported**: not implemented and must fail safely.
- **Planned**: intentionally future work.

Do not mark a capability as **Supported** just because the external RPyC gateway exposes a method.

Examples:

- `history_deals_get` existing does not mean `FillReport` is supported.
- `order_send` working does not mean market order lifecycle is fully supported.
- `symbol_info_tick` working does not mean the data client is DataTester-compliant.
- `market_book_get` existing does not mean Nautilus order book support exists.

---

## 5. Testing rules for agents

Follow `docs/testing_contract.md`.

### Required behavior

- Prefer deterministic hand-written fakes/stubs.
- Use `MagicMock` only when call assertions or complex state simulation are genuinely needed.
- Test through real adapter flows whenever practical.
- Prefer polling helpers with timeout over arbitrary `asyncio.sleep(...)`.
- Assert observable behavior:
  - emitted data,
  - emitted events,
  - reports,
  - state changes,
  - controlled exceptions,
  - fake bridge calls.

### Prohibited or strongly discouraged

- Do not introduce live MT5, network, or gateway dependencies into deterministic tests.
- Do not patch internals of the object under test.
- Do not assert exact log text when observable behavior can be asserted.
- Do not add production logic only to accommodate mocks.
- Do not end tests with `assert True`.
- Do not hide missing coverage with `pytest.skip(...)` unless the test is truly environment-dependent and a deterministic replacement exists.
- Do not use raw `NotImplementedError` in operational paths.

### Live tests

Live tests must:

- live under `tests/live/` or be explicitly marked;
- use `@pytest.mark.live`;
- use `@pytest.mark.external_rpyc` if they require a real RPyC gateway;
- use `@pytest.mark.demo_execution` if they may submit orders;
- skip when required environment variables are missing;
- never run by default;
- require `MT5_ENABLE_LIVE_EXECUTION=1` before submitting demo orders.

---

## 6. Documentation update rules

Update documentation when your task changes any of the following:

| Change | Required doc update |
|---|---|
| Public terminal access behavior | `terminal_access_contract.md`, `decisions.md` if architectural |
| Data capability | `data_capability_matrix.md`, possibly `terminal_access_capability_audit.md` |
| Execution capability | `execution_capability_matrix.md`, possibly `terminal_access_capability_audit.md` |
| Test strategy | `testing_contract.md` |
| Stable local architecture decision | `decisions.md` |
| Gateway/live validation behavior | `remote_mt5_test_gateway.md` |
| Public usage or examples | `README.md`, relevant `examples/` docs |

When in doubt, update the relevant matrix with **Partial** rather than overstating support.

---

## 7. Task implementation workflow

Use this workflow for every task:

1. Read the required docs.
2. Identify which contracts and matrices the task touches.
3. Confirm what is in scope and out of scope.
4. Implement the smallest change that satisfies the task.
5. Add deterministic tests.
6. Update docs and capability matrices if behavior changed.
7. Run relevant tests.
8. Check that no architectural invariant was broken.
9. Summarize what changed and what remains unsupported or partial.

---

## 8. AI agent checklist before finalizing a task

- [ ] I read the relevant docs.
- [ ] I did not promote `DOCKERIZED` to a public terminal access mode.
- [ ] I did not make `EXTERNAL_RPYC` responsible for terminal lifecycle.
- [ ] I did not declare a capability **Supported** without deterministic coverage.
- [ ] I did not confuse gateway RPC surface with Nautilus adapter support.
- [ ] I did not add live MT5 dependency to deterministic tests.
- [ ] I did not patch internals of the object under test.
- [ ] I did not assert exact log text when behavior was observable.
- [ ] I updated capability matrices if support status changed.
- [ ] I updated `docs/decisions.md` if I made or changed an architectural decision.
- [ ] I used controlled failures for unsupported operational paths.
- [ ] I kept examples aligned with the public API.
- [ ] I left `managed_terminal` as planned/placeholder unless the task explicitly implements it.

---

## 9. Common anti-patterns

Avoid these:

- Adding a new config field because one test needs it.
- Creating a second public model for terminal access.
- Treating `dockerized_gateway` as the recommended user path.
- Implementing behavior in examples before production code supports it.
- Calling wrapper tests “adapter integration tests” when the Nautilus client flow is not exercised.
- Marking a feature **Supported** when it only works through direct wrapper calls.
- Making fake payloads unrealistic when real anonymized fixtures are available.
- Solving a failing test by weakening production validation.
- Introducing undocumented fallback behavior.

---

## 10. Escalate when needed

If a task appears to require changing a stable decision, do not silently change it.

Instead:

1. Record the proposed change in `docs/decisions.md`.
2. Explain why the previous decision no longer works.
3. Update affected contracts and matrices.
4. Add or update tests that protect the new decision.
