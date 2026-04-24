# Terminal Access Capability Audit

## Objetivo da auditoria

Esta auditoria tem como objetivo verificar a coerência entre o modo `EXTERNAL_RPYC` (Terminal Access), a superfície RPC disponível no gateway e as capabilities efetivamente suportadas pelo adapter `nt_mt5`.

A auditoria separa explicitamente:
1.  **Superfície RPC disponível no gateway**: Métodos expostos pelo gateway RPyC externo.
2.  **Wiring terminal_access funcional**: Se o adapter está corretamente conectado e roteando para esses métodos.
3.  **Capability Nautilus efetivamente suportada**: Se o fluxo completo de dados ou execução do NautilusTrader está implementado e funcional.
4.  **Capability documentada como unsupported/conditional**: Estado oficial da capability perante o usuário.

---

## Data Capabilities

Auditado contra `docs/data_capability_matrix.md`.

| Capability | Gateway RPC disponível | Adapter suporta hoje | Teste determinístico existe | Status/documentação |
|---|---|---|---|---|
| **Instruments** | `symbols_get`, `symbol_info`, `symbol_select` | Sim (parcial/indireto via provider) | Sim (`tests/integration/test_external_rpyc_data_flow.py`) | **Supported** |
| **Quotes/ticks** | `symbol_info_tick` | Sim (via polling no background) | Sim (`tests/integration/test_external_rpyc_data_flow.py`) | **Supported** |
| **Historical ticks** | `copy_ticks_range`, `copy_ticks_from` | Sim | Sim (`tests/integration/test_external_rpyc_data_flow.py`) | **Supported** |
| **Bars** | `copy_rates_from_pos`, `copy_rates_range` | Sim | Sim (`tests/integration/test_external_rpyc_data_flow.py`) | **Supported** |
| **Order book** | `market_book_get` (disponível no wrapper) | Não | Não | **Unsupported** |
| **Instrument status** | N/A | Não | Não | **Conditional** (Indisponível via RPC simples) |
| **Lifecycle** | `shutdown` | Sim (unsubscribe/stop) | Sim | **Supported** |

---

## Execution Capabilities

Auditado contra `docs/execution_capability_matrix.md`.

| Capability | Gateway RPC disponível | Adapter suporta hoje | Teste determinístico existe | Status/documentação |
|---|---|---|---|---|
| **Market orders** | `order_send` | Sim | Sim (`tests/integration/test_external_rpyc_execution_flow.py`) | **Supported** |
| **Limit orders** | `order_send` | Sim | Sim (parcial - via wiring `order_send`) | **Supported** |
| **Cancel orders** | `order_send` (`TRADE_ACTION_REMOVE`) | Sim | Parcial (wiring validado em testes unitários) | **Supported** |
| **Modify orders** | `order_send` (`TRADE_ACTION_MODIFY`) | Não | Não | **Unsupported** |
| **Positions reconciliation**| `positions_get` | Sim | Sim (`tests/integration/test_external_rpyc_execution_flow.py`) | **Supported** |
| **Orders history** | `history_orders_get` | Sim | Sim (`tests/integration/test_external_rpyc_execution_flow.py`) | **Supported** |
| **Deals history** | `history_deals_get` | Sim | Sim (`tests/integration/test_external_rpyc_execution_flow.py`) | **Supported** |
| **Unsupported TIF/type** | N/A (Lógica interna do adapter) | Sim | Sim (validação de config) | **Supported** |

---

## Gaps Identificados

Os seguintes itens representam lacunas conhecidas entre a superfície RPC e o suporte efetivo do adapter, mapeados para planejamento futuro:

- **Order Book**: Embora o wrapper `MetaTrader5.py` exponha `market_book_get`, o adapter Nautilus não possui o componente de Order Book provider/subscriber implementado para MT5. Permanece como **Unsupported**.
- **Modify Orders**: O gateway suporta modificação via `order_send`, mas o `MetaTrader5ClientOrderMixin` não expõe método público para modificação de ordens Nautilus. Permanece como **Unsupported**.
- **Cancelamento em nível Nautilus**: O cancelamento unitário via ticket está funcional, mas o cancelamento em massa (`cancel_all_orders`) não é nativo do MT5 e requer iteração manual ainda não implementada de forma robusta.
- **Instrument Status**: O MT5 não fornece streaming nativo de status de instrumento (Open/Closed) via API Python simples de forma eficiente; requer mapeamento customizado ou polling.

---

## Regras de Interpretação

1.  **Existência de método != Capability**: A existência de um método `exposed_` no gateway RPyC ou no wrapper `MetaTrader5` não implica, por si só, que a capability NautilusTrader correspondente está suportada.
2.  **Critério de Suporte**: Uma capability só é declarada **Supported** quando houver comportamento produtivo implementado, documentação coerente e teste determinístico (unitário ou de integração com fake bridge) validando o fluxo.
3.  **Segurança em Falhas**: O modo `EXTERNAL_RPYC` deve lançar `RuntimeError` informativo se o gateway não expuser um método RPC obrigatório para uma capability declarada.

---

## Referências
- `docs/terminal_access_contract.md`
- `docs/data_capability_matrix.md`
- `docs/execution_capability_matrix.md`
- `docs/specs/spec_terminal_access_with_gateway.md`
