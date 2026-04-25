# `nt_mt5` Documentation Map

This directory contains the architectural contracts, capability matrices, decisions, and operational guidance for the `nt_mt5` MetaTrader 5 adapter for NautilusTrader.

Start here if you are a human contributor or AI coding agent.

---

## 1. Quick start for AI coding agents

Read these documents in order before changing code:

1. [`ai_agent_guidelines.md`](ai_agent_guidelines.md)
2. [`adapter_contract.md`](adapter_contract.md)
3. [`terminal_access_contract.md`](terminal_access_contract.md)
4. [`testing_contract.md`](testing_contract.md)
5. [`data_capability_matrix.md`](data_capability_matrix.md)
6. [`execution_capability_matrix.md`](execution_capability_matrix.md)
7. [`terminal_access_capability_audit.md`](terminal_access_capability_audit.md)
8. [`decisions.md`](decisions.md)

Use [`task_template.md`](task_template.md) when writing or assigning implementation tasks.

---

## 2. Core contracts

### [`adapter_contract.md`](adapter_contract.md)

Defines the internal adapter contract for `nt_mt5`.

Use it to understand:

- the layered adapter model;
- MT5-native low-level boundary;
- Python adapter layer responsibilities;
- instrument provider, data client, execution client, configs and factories;
- boundary rules for MT5 → Nautilus translation.

### [`terminal_access_contract.md`](terminal_access_contract.md)

Defines the public terminal access architecture.

Key rules:

- `EXTERNAL_RPYC` is the current functional path.
- `MANAGED_TERMINAL` is a future public path.
- `DOCKERIZED` is not a top-level public mode.
- `DOCKERIZED` is only a future backend of `MANAGED_TERMINAL`.
- `EXTERNAL_RPYC` does not manage gateway or terminal lifecycle.

### [`testing_contract.md`](testing_contract.md)

Defines testing expectations.

Use it to understand:

- unit, integration, acceptance, performance and memory tests;
- fake bridge strategy;
- why deterministic tests must not require live MT5;
- why tests should assert observable behavior, not log text;
- when mocks are appropriate.

---

## 3. Capability matrices

### [`data_capability_matrix.md`](data_capability_matrix.md)

Tracks supported, partial, unsupported and planned data capabilities.

Use it when working on:

- instruments;
- quote ticks;
- trade ticks;
- bars;
- order book;
- historical data;
- lifecycle/unsubscribe behavior.

Every supported data capability should map to deterministic tests and official NautilusTrader Data Testing Spec IDs where applicable.

### [`execution_capability_matrix.md`](execution_capability_matrix.md)

Tracks supported, partial, unsupported and planned execution capabilities.

Use it when working on:

- market orders;
- limit orders;
- stop/conditional orders;
- cancellation;
- unsupported order type;
- unsupported time-in-force;
- reports;
- fills;
- reconciliation;
- lifecycle behavior.

Every supported execution capability should map to deterministic tests and official NautilusTrader Execution Testing Spec IDs where applicable.

---

## 4. Audits and decisions

### [`terminal_access_capability_audit.md`](terminal_access_capability_audit.md)

Audits the relationship between:

1. RPC methods available in the gateway;
2. terminal access wiring;
3. actual Nautilus-level adapter capabilities;
4. documented supported/partial/unsupported status.

Important rule:

```text
Gateway method exists != Nautilus capability is supported.
```

### [`decisions.md`](decisions.md)

Records stable local project decisions.

Use it before changing:

- venue identity;
- account validation;
- bridge shape;
- terminal access model;
- execution semantics;
- readiness/lifecycle behavior;
- public API shape.

If a task requires changing a settled architectural decision, update this file in the same task.

---

## 5. Operational live validation

### [`remote_mt5_test_gateway.md`](remote_mt5_test_gateway.md)

Describes the external RPyC gateway used for optional live validation.

Key rules:

- The gateway is part of `EXTERNAL_RPYC`.
- The gateway is not `MANAGED_TERMINAL`.
- Running the gateway in a container does not make it the `DOCKERIZED` backend.
- Live validation is supplementary.
- The deterministic fake bridge suite remains the main regression guard.

Live tests should use markers such as:

```python
@pytest.mark.live
@pytest.mark.external_rpyc
@pytest.mark.demo_execution
```

Execution tests must require explicit opt-in before sending demo orders.

### Technical specification

[`specs/spec_terminal_access_with_gateway.md`](specs/spec_terminal_access_with_gateway.md) defines the technical specification for terminal access through an external RPyC gateway.

Use it when working on:

- `EXTERNAL_RPYC` wiring;
- required RPC surface;
- gateway method expectations;
- external bridge behavior;
- terminal access validation.

This spec complements [`terminal_access_contract.md`](terminal_access_contract.md) and [`remote_mt5_test_gateway.md`](remote_mt5_test_gateway.md).

## 6. Agent task specification

### [`ai_agent_guidelines.md`](ai_agent_guidelines.md)

Short mandatory guide for agents. Read this before implementing any task.

### [`task_template.md`](task_template.md)

Template for specifying implementation tasks for AI agents.

Use it to define:

- context;
- objective;
- scope;
- out of scope;
- files expected to change;
- contracts that must not be broken;
- tests required;
- docs to update;
- acceptance criteria.

### [`contract_tests_plan.md`](contract_tests_plan.md)

Plan for converting documentation rules into executable `tests/contracts/` checks.

Use it when implementing architectural invariant tests.

---

## 7. Suggested reading by task type

### Config/factory task

Read:

- `adapter_contract.md`
- `terminal_access_contract.md`
- `testing_contract.md`
- `decisions.md`

Check:

- terminal access validation;
- cache key behavior;
- public examples;
- legacy field rejection.

### Data capability task

Read:

- `adapter_contract.md`
- `testing_contract.md`
- `data_capability_matrix.md`
- `terminal_access_capability_audit.md`

Check:

- MT5 payload parsing;
- Nautilus domain output;
- fake bridge coverage;
- DataTester applicability;
- capability status.

### Execution capability task

Read:

- `adapter_contract.md`
- `testing_contract.md`
- `execution_capability_matrix.md`
- `terminal_access_capability_audit.md`
- `decisions.md`

Check:

- order transformation;
- MT5-native semantics;
- reports;
- fills;
- reconciliation;
- ExecTester applicability;
- capability status.

### Live validation task

Read:

- `remote_mt5_test_gateway.md`
- `testing_contract.md`
- `terminal_access_contract.md`

Check:

- live markers;
- env var skip behavior;
- demo execution opt-in;
- no live dependency in deterministic tests.

### Documentation/governance task

Read:

- `ai_agent_guidelines.md`
- `task_template.md`
- `contract_tests_plan.md`
- all affected contracts/matrices.

Check:

- consistency across docs;
- status terminology;
- links between decisions and contracts;
- capability status not overstated.

---

## 8. Status terminology

Use these status values consistently:

- **Supported**: production implementation exists, Nautilus-level flow is exercised, deterministic tests exist, and docs/capability matrix are aligned.
- **Partial**: gateway/wrapper/wiring exists, but Nautilus-level flow, tester coverage, reports, or docs are incomplete.
- **Unsupported**: not implemented and must fail safely.
- **Planned**: intentionally future work.

Do not mark a feature **Supported** just because the RPyC gateway exposes a method.

---

## 9. Most important project invariants

- `EXTERNAL_RPYC` is the current functional public terminal access path.
- `MANAGED_TERMINAL` is a future public path and must fail explicitly until implemented.
- `DOCKERIZED` is a future backend strategy, not a public terminal access mode.
- The bridge remains MT5-native.
- The adapter translates MT5 payloads into Nautilus domain types.
- Live MT5/RPyC tests are optional and must not block the deterministic regression suite.
- A capability is not supported until it has production behavior, Nautilus-level flow coverage, deterministic tests and docs.
- New architectural decisions must be recorded in `decisions.md`.
