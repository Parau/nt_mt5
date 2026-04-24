# Terminal Access Contract

This document defines the stable contract for accessing the MetaTrader 5 (MT5) terminal within the `nt_mt5` adapter.

## Public Access Modes

The adapter supports two primary public modes for terminal access, represented by the `MT5TerminalAccessMode` enum:

1.  **`EXTERNAL_RPYC`**:
    - The adapter connects to an existing, externally managed RPyC gateway.
    - The adapter is **not** responsible for starting, supervising, or stopping the terminal or the gateway.
    - This is the primary mode for connecting to remote or pre-existing MT5 environments.

2.  **`MANAGED_TERMINAL`**:
    - The adapter is responsible for the full lifecycle of the terminal environment.
    - This includes starting the terminal, performing health checks, and ensuring a clean shutdown.
    - *Note: In the current phase, the managed runtime may not be fully implemented. If called when unimplemented, it must fail with a controlled and explicit `RuntimeError`.*

## Internal Backend Strategies

- **`DOCKERIZED`**:
    - This is **not** a top-level public access mode.
    - It is an internal backend strategy for the `MANAGED_TERMINAL` mode.
    - It represents a future capability where the adapter manages a terminal running inside a Docker container.

## Configuration Validation Rules

To ensure architectural consistency, the following validation rules apply to adapter configurations:

- **Mode `EXTERNAL_RPYC`**:
    - Requires an `external_rpyc` configuration block.
    - Must **reject** any `managed_terminal` configuration block.
- **Mode `MANAGED_TERMINAL`**:
    - Requires a `managed_terminal` configuration block.
    - Must **reject** any `external_rpyc` configuration block.
- **Legacy Fields**:
    - Top-level `dockerized_gateway` fields are deprecated and must be rejected to prevent silent fallbacks to legacy behavior.

## Minimum Required RPC Surface

Any external gateway (used in `EXTERNAL_RPYC` mode) must expose at least the following MT5-native RPC endpoints:

### Session and Diagnostics
- `initialize`
- `login`
- `last_error`
- `version`
- `shutdown`
- `get_constant`

### Terminal and Account State
- `terminal_info`
- `account_info`

### Symbol Management
- `symbols_get`
- `symbol_info`
- `symbol_info_tick`
- `symbol_select`

### Market Data and History
- `copy_rates_from_pos`
- `copy_ticks_range`
- `copy_ticks_from`

### Execution and Operational History
- `order_send`
- `positions_get`
- `history_orders_total`
- `history_orders_get`
- `history_deals_total`
- `history_deals_get`

## Operational Behavior

- **Controlled Failures**: Operational failures (e.g., connection loss, missing RPC methods, unauthorized access) must be handled gracefully and raise explicit, informative errors.
- **Direct Mapping**: Public methods in the adapter wrapper should map directly to their `exposed_` counterparts on the RPyC gateway.

## References

For the complete technical and architectural specification, see:
- `docs/specs/spec_terminal_access_with_gateway.md`
