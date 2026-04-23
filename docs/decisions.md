# Project Decisions

This document records stable local decisions for `nt_mt5`.
These are project-level choices made while implementing the adapter against the NautilusTrader adapter contract.

## Source of truth

Official upstream references:
- Published docs: https://nautilustrader.io/docs/latest/developer_guide/adapters
- Published docs: https://nautilustrader.io/docs/latest/developer_guide/testing
- Published docs: https://nautilustrader.io/docs/latest/developer_guide/spec_data_testing
- Published docs: https://nautilustrader.io/docs/latest/developer_guide/spec_exec_testing

Optional upstream source references:
- GitHub source: https://github.com/nautechsystems/nautilus_trader/blob/develop/docs/developer_guide/adapters.md
- GitHub source: https://github.com/nautechsystems/nautilus_trader/blob/develop/docs/developer_guide/testing.md
- GitHub source: https://github.com/nautechsystems/nautilus_trader/blob/develop/docs/developer_guide/spec_data_testing.md
- GitHub source: https://github.com/nautechsystems/nautilus_trader/blob/develop/docs/developer_guide/spec_exec_testing.md

Upstream NautilusTrader documentation defines the adapter framework and testing expectations.
This file records only local decisions needed to implement `nt_mt5` consistently.

## Stable decisions

### 1. Venue identity
- The canonical venue is always `METATRADER_5`.
- Broker, server, and account metadata do not become the structural venue.
- Broker/server/account details belong in metadata or instrument/account info, not in venue identity.

### 2. Account validation
- `config.account_id` is the source of truth for validating the MT5 login.
- Nautilus `AccountId` is a structural engine identity.
- Do not parse Nautilus `AccountId` to recover the MT5 login.

### 3. Bridge shape
- The bridge stays MT5-native.
- Do not wrap MT5 behavior in Interactive Brokers terminology or flow shape.
- Keep MT5-native request/response semantics explicit in the adapter.

### 4. Execution semantics
- Order transformation must be based on MT5-native fields and behavior.
- Infer order side and order type from the correct MT5-native fields.
- Preserve explicit, tested rules for time-in-force and filling behavior.
- Do not keep hybrid order models once the MT5-native model is established.

### 5. Interface contract
- Use the modern NautilusTrader typed message contracts for data and execution clients.
- Do not keep legacy or hybrid method signatures once the typed path exists.

### 6. Unsupported operations
- Unsupported operational paths must fail safely.
- Prefer warnings or controlled empty/unsupported results.
- Do not raise raw `NotImplementedError` in operational paths.

### 7. Lifecycle and readiness
- Ready state must reflect real bootstrap success, not manually forced state.
- Connection and execution/account validation are related but distinct concerns.
- Do not mark the adapter as ready before transport/bootstrap state is genuinely established.

### 8. Tests versus production code
- Do not add production logic only to make tests pass.
- If tests need more realistic objects, improve the fake/fixture/test setup instead.
- Integration tests should prefer real adapter flows over manually injected final state.

### 9. Examples and public API
- Examples must use the real public API exactly.
- README, configs, factories, examples, and exported names must stay mutually consistent.

## How to use this file

When changing the adapter, ask:
1. Is this required by NautilusTrader upstream behavior?
2. Is this already settled by a local decision here?
3. Is the supported/unsupported capability status already captured in `docs/data_capability_matrix.md` or `docs/execution_capability_matrix.md`?
4. Is there a real bug that justifies changing the local decision?

If the answer to (2) is yes and (4) is no, keep the existing decision.
If the answer to (3) is yes, keep the capability matrices aligned with the implementation and tests.
