# Adapter Contract

This document is the internal contract for the `nt_mt5` adapter.
It is derived from the official NautilusTrader adapter documentation and should be read together with the upstream references below and `docs/terminal_access_contract.md`.

## Source of truth

Official upstream references:
- Published docs: https://nautilustrader.io/docs/latest/developer_guide/adapters
- Published docs: https://nautilustrader.io/docs/latest/developer_guide/testing
- Published docs: https://nautilustrader.io/docs/latest/developer_guide/spec_data_testing
- Published docs: https://nautilustrader.io/docs/latest/developer_guide/spec_exec_testing

Optional upstream source references:
- Repository docs root: https://github.com/nautechsystems/nautilus_trader/tree/develop/docs
- Repository developer guide directory: https://github.com/nautechsystems/nautilus_trader/tree/develop/docs/developer_guide

If this document conflicts with upstream NautilusTrader behavior or interface contracts, upstream wins unless `docs/decisions.md` records an explicit local project decision.

## Purpose

`nt_mt5` is a NautilusTrader adapter for MetaTrader 5.
Its job is to translate MT5-native APIs and event flows into NautilusTrader's unified interface and normalized domain model.

## Required architecture

Follow NautilusTrader's layered adapter model:

- Low-level client layer for networking, transport, parsing, and venue-native concepts.
- Python adapter layer for:
  - `InstrumentProvider`
  - `LiveDataClient` / `LiveMarketDataClient`
  - `LiveExecutionClient`
  - config classes
  - factories

For this project, the MT5 bridge is the low-level venue-native layer.

### Terminal Access Model
The adapter distinguishes between two modes of terminal access:
- **EXTERNAL_RPYC**: The adapter connects to an existing MT5 terminal/gateway. Lifecycle is external.
- **MANAGED_TERMINAL**: The adapter is responsible for the terminal lifecycle (starting, healthchecking, stopping).

## Boundary rules

- Keep the low-level bridge MT5-native.
- Translate MT5 -> Nautilus at the adapter boundary.
- Do not leak bridge-only, RPyC-only, or mock-only types across the adapter.
- Do not reintroduce Interactive Brokers semantics, naming, or flow shape.
- Prefer direct MT5 concepts such as:
  - `account_info`
  - `terminal_info`
  - `symbol_info`
  - `symbols_get`
  - `symbol_info_tick`
  - `copy_ticks_*`
  - `copy_rates_*`
  - `orders_get`
  - `positions_get`
  - `history_orders_get`
  - `history_deals_get`
  - `order_check`
  - `order_send`

## Core adapter responsibilities

### 1. Instrument definitions
The adapter must:
- load and cache instruments through an `InstrumentProvider`
- map between venue-native symbols and Nautilus `InstrumentId`
- keep symbol normalization explicit and testable

### 2. Market data
The adapter must:
- support subscription workflows for the MT5-supported market data types
- support historical data requests where MT5 provides them
- emit Nautilus domain types from adapter code, not raw MT5 payloads

### 3. Execution
The adapter must:
- submit, modify, and cancel orders through MT5-native request semantics
- reconcile order, fill, and position state on connect
- generate Nautilus execution reports from MT5-native state

### 4. Configuration and factories
The adapter must:
- expose typed user-facing configs
- instantiate clients through factories
- keep factory wiring, examples, and README mutually consistent

## Implementation sequence

When changing the adapter, prefer the NautilusTrader dependency order:

1. Instrument definitions and symbol mapping
2. Market data subscriptions and historical requests
3. Order execution and reconciliation
4. Configuration and factories
5. Tests and runnable examples

Do not start with examples or tests that assume missing core behavior.

## Interface contract

The adapter must follow the modern NautilusTrader message contracts for data and execution clients.
Do not keep legacy or hybrid interfaces once a typed interface exists.

Unsupported operations must fail safely:
- log a warning, or
- return a controlled empty / unsupported result

Do not raise raw `NotImplementedError` in operational paths.

## Documentation contract

The adapter must clearly document:
- supported data types
- supported order types
- supported time-in-force behavior
- unsupported features and safe fallbacks
- any MT5-specific behavior that differs from a typical exchange adapter

Use:
- `docs/data_capability_matrix.md` as the local matrix for supported and unsupported data capabilities
- `docs/execution_capability_matrix.md` as the local matrix for supported and unsupported execution capabilities
- `docs/terminal_access_contract.md` as the local contract for terminal-access behavior and public terminal-access architecture

These matrices and contracts are operational project documents derived from the NautilusTrader specs; the published upstream docs remain the final source of truth.

## Notes for contributors and coding agents

Before changing behavior, check whether the change belongs to:
- upstream NautilusTrader contract, or
- a local project decision recorded in `docs/decisions.md`, or
- the stable terminal-access model recorded in `docs/terminal_access_contract.md`

Do not reopen settled architectural choices unless a real bug or upstream requirement forces the change.
