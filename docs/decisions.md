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

### 10. Terminal Access Model
- The adapter adopts `EXTERNAL_RPYC`, `LOCAL_PYTHON`, and `MANAGED_TERMINAL` as public access modes.
- `EXTERNAL_RPYC` is for existing/external terminals accessed via RPyC gateway.
- `LOCAL_PYTHON` is for direct local access using the official `MetaTrader5` Python package installed on the local machine.
- `MANAGED_TERMINAL` is for when the adapter controls the terminal lifecycle.
- Internally, `DOCKERIZED` is a backend for `MANAGED_TERMINAL`, not a top-level access mode.

### 11. Python/RPyC low-level layer
- Although the official NautilusTrader adapter guide describes a Rust-first architecture for new high-performance adapters, `nt_mt5` intentionally uses a Python/RPyC low-level boundary because the MetaTrader5 Python package and terminal availability dictate the integration boundary.
- This decision does not change the Nautilus layering principles used by the project:
  - keep the low-level boundary venue-native;
  - keep adapter responsibilities in the Python adapter layer;
  - expose typed configs, factories, provider, data client, and execution client;
  - use deterministic fake bridge tests for regression;
  - use optional live smoke tests only as supplementary validation.
- Do not introduce a second low-level architecture unless a future decision explicitly supersedes this one.

### 12. Live tests are supplementary
- Live tests with real MT5/RPyC are useful for validation, but they are not the source of truth for regression.
- The deterministic fake bridge suite remains the main correctness guard.
- Live tests must be optional, explicitly marked, and skipped when required environment variables are absent.
- Live execution tests must require explicit opt-in, such as `MT5_ENABLE_LIVE_EXECUTION=1`.

### 13. Capability support definition
- A capability is only `Supported` when it has production implementation, Nautilus-level flow coverage, deterministic tests, and updated docs.
- Gateway method availability alone is not sufficient.
- Wrapper-level routing tests are valuable, but they do not by themselves prove that a Nautilus-level capability is supported.
- If gateway/wrapper/wiring exists but Nautilus-level flow or tester coverage is incomplete, the capability should be marked `Partial`.
- Unsupported capabilities must be denied, rejected, or reported safely and documented clearly.

### 14. Fill reports source
- When fill reports are implemented, the preferred source is MT5 deal history through `history_deals_get` / `history_deals_total`, unless a better MT5-native source is explicitly adopted.
- `history_deals_get` existing in the gateway or wrapper does not, by itself, mean that Nautilus `FillReport` generation is supported.
- Fill-report support must include MT5 payload normalization, Nautilus report generation, deterministic tests, and execution capability matrix updates.

### 15. Trade tick decision point
- Trade tick support must be decided explicitly.
- If MT5/gateway data can provide last-trade semantics suitable for Nautilus `TradeTick`, the adapter should implement and test that mapping before declaring trade ticks supported.
- If the available MT5 data is quote-only or does not provide a reliable trade-tick semantic for a given asset class, the limitation must be documented in `docs/data_capability_matrix.md` and related docs.
- Do not treat quote ticks as trade ticks without an explicit documented mapping decision.

### 16. LOCAL_PYTHON terminal access
- `LOCAL_PYTHON` is a third public access mode alongside `EXTERNAL_RPYC` and `MANAGED_TERMINAL`.
- It uses the official `MetaTrader5` Python package installed directly on the local machine (normally Windows).
- It calls MT5-native functions (`initialize`, `login`, `terminal_info`, `account_info`, `symbol_info`, `symbol_info_tick`, `copy_rates_*`, `copy_ticks_*`, `order_send`, `positions_get`, `history_orders_get`, `history_deals_get`) on the locally imported module.
- It does not manage an external gateway process, RPyC connection, or Docker container.
- The only lifecycle it controls is the normal `MetaTrader5.initialize()` / `shutdown()` cycle.
- It must fail with a controlled, explicit error when used on an incompatible platform or when the `MetaTrader5` package is not installed.
- This mode is intentionally separate from `EXTERNAL_RPYC` and must not silently fall back to RPyC behavior.
- `DOCKERIZED` is not affected by this decision; it remains an internal backend of `MANAGED_TERMINAL` only.

## How to use this file

When changing the adapter, ask:
1. Is this required by NautilusTrader upstream behavior?
2. Is this already settled by a local decision here?
3. Is the supported/unsupported capability status already captured in `docs/data_capability_matrix.md` or `docs/execution_capability_matrix.md`?
4. Is there a real bug that justifies changing the local decision?

If the answer to (2) is yes and (4) is no, keep the existing decision.
If the answer to (3) is yes, keep the capability matrices aligned with the implementation and tests.

When an implementation task requires changing one of these decisions, update this file in the same task and explain why the previous decision no longer applies.
