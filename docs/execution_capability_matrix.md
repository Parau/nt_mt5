# Execution Capability Matrix

This document translates the NautilusTrader **Execution Testing Spec** into an internal capability matrix for `nt_mt5`.

## Source of truth

Official reference:
- Published docs: https://nautilustrader.io/docs/latest/developer_guide/spec_exec_testing/

Upstream source reference:
- GitHub source: https://github.com/nautechsystems/nautilus_trader/blob/develop/docs/developer_guide/spec_exec_testing.md

If this file conflicts with NautilusTrader's published execution testing spec, the upstream spec wins. Use this file as a project planning and review aid, not as a replacement for the official spec.

## How to use this matrix

- **Required baseline** means the capability should normally be implemented and tested for a useful MT5 execution adapter.
- **Conditional** means it should be implemented and tested only if `nt_mt5` explicitly supports it.
- **Out of scope unless intentionally added** means it should normally be documented as unsupported for `nt_mt5`, unless the project intentionally adds support.
- Every supported capability should map to deterministic tests.
- Every unsupported capability should be denied or rejected safely and documented clearly.

The `Live coverage` column tracks Tier 2 live acceptance results. See `docs/testing_contract.md` — **Two-tier validation strategy** — for the selection criteria and rationale.

## Capability status definitions

Use these status values when tracking actual project support:

- **Supported**: production implementation exists, the Nautilus-level execution flow is exercised, deterministic tests exist, and docs/capability matrix are aligned.
- **Partial**: gateway/wrapper/wiring exists, but Nautilus-level flow, reports, reconciliation, ExecTester coverage, or documentation is incomplete.
- **Unsupported**: not implemented and should be denied, rejected, or documented as unavailable.
- **Planned**: intentionally future work.

A gateway method being available, or `order_send` returning successfully, is not enough to mark a Nautilus execution capability as `Supported`.

## Upstream framing

The NautilusTrader Execution Testing Spec defines a grouped test matrix using `ExecTester`. Each adapter must pass the subset of tests matching its supported capabilities. Adapter-specific behavior such as market-order simulation, time-in-force handling, and order flags should be documented in the adapter guide together with a capability matrix.

## Matrix

| Group | Upstream scope | Representative cases | `nt_mt5` expectation | Notes |
|---|---|---|---|---|
| 1. Market orders | Market buy/sell, IOC/FOK market TIF, quote quantity, close-on-stop | TC-E01–TC-E06 | **Required baseline, except quote quantity unless intentionally supported** | Market order submit/fill and close-on-stop are core for a practical MT5 adapter. Quote-quantity support should only be claimed if intentionally mapped. |
| 2. Limit orders | GTC, IOC, FOK, GTD, DAY, paired limits | TC-E10–TC-E19 | **Required baseline for GTC; conditional for IOC/FOK/GTD/DAY** | At minimum, accepted/open limit orders should work. Extended TIF behavior should only be claimed where the MT5 mapping is real and tested. |
| 3. Stop and conditional orders | Stop-market, stop-limit, MIT, LIT | TC-E20–TC-E27 | **Conditional** | MT5-native stop semantics are relevant; MIT/LIT-style support should only be claimed if there is a real mapping and tests. |
| 4. Order modification | Amend, cancel-replace, modify stop trigger, modify rejected | TC-E30–TC-E36 | **Conditional but strongly preferred** | If the adapter supports amend/replace behavior through MT5 semantics, it should be tested here. If not, safe denial/rejection must be documented. |
| 5. Order cancellation | Single cancel, cancel-all-on-stop, individual cancel, batch cancel, cancel rejection | TC-E40–TC-E44 | **Required baseline for single cancel and stop cleanup** | Cancel behavior and invalid-cancel rejection are core execution behaviors. Batch cancel is conditional. |
| 6. Bracket orders | Entry + TP + SL bracket workflows | TC-E50–TC-E53 | **Out of scope unless intentionally added** | These are advanced contingent workflows and should not be implied unless explicitly implemented and tested. |
| 7. Order flags | Post-only, reduce-only, display quantity, custom order params | TC-E60–TC-E63 | **Conditional** | Only claim flags that are truly supported through MT5-native semantics or a documented adapter mapping. Custom order params are useful for explicit adapter extensions. |
| 8. Rejection handling | Post-only rejection, reduce-only rejection, unsupported order type, unsupported TIF | TC-E70–TC-E73 | **Required baseline for unsupported type/TIF; conditional for flag-specific rejection** | Every adapter should deny unsupported order type and unsupported TIF cleanly before venue submission when possible. |
| 9. Lifecycle / reconciliation | Open-on-start, cancel-on-stop, close-on-stop, unsubscribe-on-stop, reconcile orders/fills/positions | TC-E80–TC-E87 | **Required baseline** | Bootstrap, stop behavior, and reconciliation are central for live execution reliability. |
| 10. Options trading | Option limits, alt pricing, option rejects, option reconciliation | TC-E90–TC-E101 | **Out of scope unless intentionally added** | Only applicable if `nt_mt5` intentionally supports options trading through Nautilus-native execution semantics. |

## Operational traceability matrix

This section tracks the current implementation status. It should be updated whenever a task changes execution behavior, reports, tests, or documented support.

| Capability | Status | Official test IDs | Deterministic coverage | Live coverage | Validated by | Notes |
|---|---|---|---|---|---|---|
| Market orders | **Supported** | TC-E01–TC-E06 | **TC-EL-02**: `test_lifecycle_submit_order_calls_order_send` — `order_send` chamado com parâmetros corretos. **TC-EL-03**: `test_lifecycle_submit_order_generates_submitted_and_accepted` — `OrderSubmitted` + `OrderAccepted` com `venue_order_id` gerados. **TC-EL-07**: `test_lifecycle_submit_order_rejected_on_error_retcode` — retcode de erro → `OrderRejected`. **TC-EL-20**: `test_lifecycle_market_order_fill_end_to_end` (parametrizado BUY/SELL) — cadeia completa `OrderSubmitted → OrderAccepted → OrderFilled` via stub bridge; valida `trade_id`, `venue_order_id`, `last_qty`, `last_px`, `liquidity_side=TAKER`. | **Validado** em Tickmill-Demo USTEC (hedging, IOC fill, 2026-05-01): BUY `retcode=10009`, CLOSE com `position=<ticket>` `retcode=10009`, posições=0. **Validado** em Tickmill-Demo BTCUSD via `TradingNode` (2026-05-03): QuoteTick recebido via polling RPyC → BUY MARKET IOC 0.01 preenchido a 78636.50, SELL MARKET IOC 0.01 preenchido a 78626.50, round-trip completo sem erros — via `examples/exec_smoke_trading_node.py`. | `test_execution_lifecycle_external_rpyc.py` + `test_execution_client_external_rpyc.py` | Fill end-to-end determinístico coberto via stub (TC-EL-20). |
| Limit orders | **Partial** | TC-E10–TC-E19 | **TC-EL-18/19**: `test_lifecycle_submit_gtc_limit_order` (parametrizado BUY/SELL) — `order_send` chamado com `action=5` (TRADE_ACTION_PENDING), `type=2` (ORDER_TYPE_BUY_LIMIT) ou `type=3` (ORDER_TYPE_SELL_LIMIT), `type_time=0` (GTC), preço correto → `OrderSubmitted` + `OrderAccepted` com `venue_order_id`. Retcode 10008 (PLACED) tratado corretamente — sem fill imediato. | Pending | `test_execution_lifecycle_external_rpyc.py` | GTC BUY/SELL LIMIT cobertos. IOC/FOK/DAY limit behavior pendente. Modify/cancel de limit open (TC-E30–E36, TC-E40–E44) tem cobertura parcial. |
| Stop and conditional orders | **Partial** | TC-E20–TC-E27 | **TC-EL-21/22**: `test_lifecycle_submit_gtc_stop_market_order` (parametrizado BUY/SELL) — `order_send` chamado com `action=5` (TRADE_ACTION_PENDING), `type=4` (ORDER_TYPE_BUY_STOP) ou `type=5` (ORDER_TYPE_SELL_STOP), `price`=trigger_price → `OrderSubmitted` + `OrderAccepted` (retcode 10008). Sem fill imediato. Instrumento: BTCUSD. **TC-EL-23/24**: `test_lifecycle_submit_gtc_stop_limit_order` (parametrizado BUY/SELL) — `action=5`, `type=6` (ORDER_TYPE_BUY_STOP_LIMIT) ou `type=7` (ORDER_TYPE_SELL_STOP_LIMIT), `price`=trigger, `stoplimit`=limit_price → `OrderSubmitted` + `OrderAccepted`. Sem fill imediato. | **TC-LIVE-STOP-01..04** (`test_live_stop_orders.py`, 2026-05-03): BUY_STOP (type=4), SELL_STOP (type=5), BUY_STOP_LIMIT (type=6), SELL_STOP_LIMIT (type=7) — todos aceitos como pending no Tickmill-Demo BTCUSD, retcode=10009, ordens canceladas após teste. Revelou bug `stpx`→`stoplimit` (campo correto da API MT5). | `test_execution_lifecycle_external_rpyc.py` | STOP_MARKET e STOP_LIMIT cobertos (BUY+SELL). Tier 2 validado via `test_live_stop_orders.py`. MIT/LIT não mapeados → fora do escopo. Modify/cancel de ordens stop pendentes (TC-E30–E36) não cobertos.
| Order modification | Partial | TC-E30–TC-E36 | **TC-EL-11**: `test_modify_order_calls_place_order` — `_modify_order` chama `place_order` com volume atualizado via `MT5LiveExecClientFactory`. | Pending | `test_execution_order_commands_external_rpyc.py` | Somente volume coberto. Amend de price, stop trigger, modify rejected (TC-E33–E36) ainda sem cobertura. |
| Order cancellation | Partial | TC-E40–TC-E44 | **TC-EL-10**: `test_cancel_order_sends_action_8` — `_cancel_order` envia `order_send` com `action=8` (TRADE_ACTION_REMOVE). **TC-EL-12**: `test_cancel_all_orders_cancels_each_open_order` — `_cancel_all_orders` cancela cada ordem aberta no cache Nautilus. | Pending | `test_execution_order_commands_external_rpyc.py` | Cancel rejection (TC-E43) e cancel-on-stop (TC-E41) ainda sem cobertura. |
| Bracket orders | Unsupported | TC-E50–TC-E53 | N/A | N/A | N/A | Out of scope unless intentionally implemented and tested. |
| Order flags | Unsupported | TC-E60–TC-E63 | N/A | N/A | N/A | Post-only, reduce-only, display quantity, and custom params must not be implied without real mapping. |
| Unsupported order type | **Supported** | TC-E72 | **TC-EL-07**: `test_lifecycle_submit_order_rejected_on_error_retcode` — retcode de erro do bridge → `OrderRejected` (pós-venue). **TC-EL-13**: `test_lifecycle_submit_order_rejected_for_unsupported_order_type` (parametrizado × 5 tipos) — `validate_order_pre_venue()` rejeitada antes de `order_send` para `MARKET_TO_LIMIT`, `MARKET_IF_TOUCHED`, `LIMIT_IF_TOUCHED`, `TRAILING_STOP_MARKET`, `TRAILING_STOP_LIMIT`. `place_order` não chamado; `OrderRejected` gerado com reason contendo o nome do tipo. | N/A | `test_execution_lifecycle_external_rpyc.py` + `test_mt5_mappings.py` | Guard pré-venue implementado via `validate_order_pre_venue()` em `parsing/execution.py`; chamado no topo de `_submit_order` antes de qualquer chamada ao bridge. |
| Unsupported TIF | **Supported** | TC-E73 | **TC-EL-14**: `test_lifecycle_submit_order_rejected_for_unsupported_tif` (parametrizado × 3 TIFs) — `validate_order_pre_venue()` rejeitada antes de `order_send` para `GTD`, `AT_THE_OPEN`, `AT_THE_CLOSE`. `place_order` não chamado; `OrderRejected` gerado com reason contendo o nome do TIF. **TC-E73-UNIT**: `test_validate_order_pre_venue_rejects_unsupported_tif` em `test_mt5_mappings.py`. | N/A | `test_execution_lifecycle_external_rpyc.py` + `test_mt5_mappings.py` | Guard pré-venue implementado. TIFs suportados: GTC, DAY, FOK, IOC. |
| Position reports / reconciliation | Partial | TC-E80, TC-E86, TC-E87 | **TC-EL-06**: `test_lifecycle_generate_position_status_reports` — `generate_position_status_reports` retorna `PositionStatusReport` para USTEC com qty, price, side corretos via factory. **TC-EL-01**: `test_lifecycle_connect_validates_account` — `_connect()` valida `config.account_id` contra bridge (TC-E80). Rejeição de account errada coberta em `test_exec_client_connect_rejects_wrong_account`. | Pending | `test_execution_lifecycle_external_rpyc.py` + `test_execution_client_external_rpyc.py` | Fixed `find_with_symbol_id(str)` bug; raw-dict positions do EXTERNAL_RPYC corretamente convertidas. |
| Order reports / reconciliation | Partial | TC-E84, TC-E85 | **TC-EL-08**: `test_generate_order_status_reports_from_positions` — `generate_order_status_reports` infere `OrderStatusReport` a partir de posições abertas. **TC-EL-09**: `test_generate_order_status_report_singular_not_found` — singular retorna `None` quando order não está em ordens abertas. | Pending | `test_execution_order_commands_external_rpyc.py` | Inferência de status a partir de posições é proxy; ordens históricas (MT5 orders_get) não cobertas. |
| Fill reports | Partial | TC-E85 | **TC-EL-04**: `test_lifecycle_generate_fill_reports_ustec` — `generate_fill_reports` para USTEC retorna `FillReport` com trade_id, venue_order_id, side, qty, px, commission, LiquiditySide.TAKER. **TC-EL-05**: `test_lifecycle_generate_fill_reports_all_symbols` — todos os símbolos via `instrument_id=None`. | `history_deals_get` retorna `None` imediatamente após fill no Tickmill-Demo (consistência eventual); smoke documenta como esperado. FillReport contra dados live ainda não validado. | `test_execution_lifecycle_external_rpyc.py` | `history_deals_get` → FillReport: todos campos mapeados. Delay de histórico no Tickmill confirmado. |
| Lifecycle / stop behavior | **Supported** | TC-E81, TC-E82, TC-E83 | **TC-EL-15**: `test_disconnect_cancel_on_stop_cancels_open_orders` — `cancel_on_stop=True` (default) → `_disconnect()` calls `order_send(action=8)` for each open order with a `venue_order_id` in the Nautilus cache. **TC-EL-16**: `test_disconnect_close_on_stop_closes_open_positions` — `close_on_stop=True` → `_disconnect()` sends `order_send(action=1, position=<ticket>)` for each position returned by `positions_get`. **TC-EL-17**: `test_disconnect_no_cancel_no_close_when_flags_false` — `cancel_on_stop=False, close_on_stop=False` → no `order_send` calls on disconnect. | Pending | `test_execution_lifecycle_external_rpyc.py` | `cancel_on_stop` and `close_on_stop` declared in `MetaTrader5ExecClientConfig` (default: `True` / `False`). `_disconnect()` implements the cancel and close loops. `close_on_stop` path uses `positions_get` + `order_send(position=ticket)` via `asyncio.to_thread`. |
| Options trading | Unsupported | TC-E90–TC-E101 | N/A | N/A | N/A | Out of scope unless intentionally added. |

## Recommended minimum target for `nt_mt5`

A practical minimum target for `nt_mt5` is:
- Group 1: Market orders, except quote-quantity unless explicitly supported
- Group 2: Core limit-order behavior, at least GTC, and any additional TIF that is genuinely mapped and tested
- Group 5: Cancellation behavior
- Group 8: Explicit denial/rejection for unsupported order types and unsupported TIF
- Group 9: Lifecycle, stop behavior, and reconciliation

Stop-order support from Group 3 should be included if it is part of the adapter's real MT5-native execution model.

## Project review checklist

For each supported execution capability, confirm all of the following:
- the behavior exists in production code using MT5-native semantics;
- the public docs list the capability and any caveats;
- deterministic tests cover the supported path;
- reconciliation/report generation is coherent where applicable;
- the flow is exercised at Nautilus adapter level, not only through wrapper/RPyC calls;
- the `Operational traceability matrix` above is updated.

For each unsupported capability, confirm:
- it is documented as unsupported;
- the adapter denies or rejects the request safely;
- tests verify the unsupported-path behavior where Nautilus expects that behavior.

For each partial capability, confirm:
- the missing piece is documented in `Notes`;
- future tests or implementation tasks can identify what must change before it becomes `Supported`.
