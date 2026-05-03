# Terminal Access Contract

This document defines the stable contract for accessing the MetaTrader 5 (MT5) terminal within the `nt_mt5` adapter.

## Public Access Modes

The adapter supports three primary public modes for terminal access, represented by the `MT5TerminalAccessMode` enum:

1.  **`EXTERNAL_RPYC`**:
    - The adapter connects to an existing, externally managed RPyC gateway.
    - The adapter is **not** responsible for starting, supervising, or stopping the terminal or the gateway.
    - This is the primary mode for connecting to remote or pre-existing MT5 environments.

2.  **`LOCAL_PYTHON`**:
    - The adapter uses the official `MetaTrader5` Python package installed directly on the local machine.
    - Expected to work only on platforms where the `MetaTrader5` package is available (normally Windows).
    - The adapter is **not** responsible for launching an external gateway or RPyC bridge.
    - The only lifecycle it controls is the normal `MetaTrader5.initialize()` / `shutdown()` cycle.
    - If the `MetaTrader5` package is not installed or the platform is incompatible, the adapter must fail with a controlled, explicit error.
    - *Note: This mode is planned/in implementation. Full end-to-end test coverage is pending the tasks that follow the governance phase.*

3.  **`MANAGED_TERMINAL`**:
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
- **Mode `LOCAL_PYTHON`**:
    - Does not require an `external_rpyc` or `managed_terminal` configuration block.
    - May accept optional `local_python` configuration (e.g., `MT5_LOCAL_PATH`, `MT5_LOCAL_PORTABLE`).
    - Must **reject** any `external_rpyc` or `managed_terminal` configuration block.
- **Mode `MANAGED_TERMINAL`**:
    - Requires a `managed_terminal` configuration block.
    - Must **reject** any `external_rpyc` configuration block.
- **Legacy Fields**:
    - Top-level `dockerized_gateway` fields are deprecated and must be rejected to prevent silent fallbacks to legacy behavior.

## Migration and Deprecation Plan

To avoid concurrent public architectures, the following legacy fields are being phased out in favor of the modern `terminal_access` model.

| Legacy Field | Status | Recommended Substitute | Transition Behavior | Future Disposal |
|---|---|---|---|---|
| `mode` | deprecated/transitional | `terminal_access` | accepted only if still necessary for communication type (IPC/EA) | remove as access indicator in future version |
| `rpyc_config` | deprecated/transitional | `external_rpyc` | rejected in `EXTERNAL_RPYC` mode; do not use in new examples | remove from public API |
| `dockerized_gateway` | legacy top-level | `managed_terminal.dockerized` | rejected as fallback for `MANAGED_TERMINAL` mode | remove from public API |

The primary recommended configuration path is `terminal_access=EXTERNAL_RPYC` combined with an `external_rpyc` block.

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

## LOCAL_PYTHON Direct API Surface

In `LOCAL_PYTHON` mode, the adapter calls the following MT5-native functions directly on the locally installed `MetaTrader5` module (no RPyC layer):

### Session and Diagnostics
- `initialize`
- `login`
- `last_error`
- `version`
- `shutdown`

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
- `docs/terminal_access_capability_audit.md`
