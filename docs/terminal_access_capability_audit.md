# Terminal Access Capability Audit

## Objetivo da auditoria

Esta auditoria tem como objetivo verificar a coerência entre o modo `EXTERNAL_RPYC` (Terminal Access), a superfície RPC disponível no gateway e as capabilities efetivamente suportadas pelo adapter `nt_mt5`.

A auditoria separa explicitamente:
1.  **Superfície RPC disponível no gateway**: Métodos expostos pelo gateway RPyC externo.
2.  **Wiring terminal_access funcional**: Se o adapter está corretamente conectado e roteando para esses métodos.
3.  **Capability Nautilus efetivamente suportada**: Se o fluxo completo de dados ou execução do NautilusTrader está implementado e funcional.
4.  **Capability documentada como unsupported/conditional**: Estado oficial da capability perante o usuário.

---

## Definições de status

Para evitar que a disponibilidade de um método RPC seja confundida com suporte funcional completo no NautilusTrader, esta auditoria usa os seguintes status:

- **Supported**: existe implementação produtiva, o fluxo Nautilus-level é exercitado, há teste determinístico cobrindo o comportamento e a documentação/matriz de capability está alinhada.
- **Partial**: a superfície RPC, o wrapper ou o wiring existe, mas ainda falta cobertura completa do fluxo Nautilus-level, DataTester/ExecTester, geração de reports, reconciliação ou documentação rastreável.
- **Unsupported**: não implementado no adapter Nautilus e deve falhar de forma segura ou ser documentado como indisponível.
- **Planned**: trabalho futuro intencional, ainda não suportado operacionalmente.

Uma capability não deve ser marcada como **Supported** apenas porque o gateway externo expõe um método, ou porque o wrapper consegue roteá-lo.

---

## Data Capabilities

Auditado contra `docs/data_capability_matrix.md`.

| Capability | Gateway RPC disponível | Adapter suporta hoje | Teste determinístico existe | Status/documentação |
|---|---|---|---|---|
| **Instruments** | `symbols_get`, `symbol_info`, `symbol_select` | Sim, parcial/indireto via provider | ✅ TC-D01, TC-D03 em `test_data_tester_matrix_external_rpyc.py`; validado live em `test_external_rpyc_data_tester.py` (USTEC, Tickmill-Demo) | **Partial** |
| **Quotes/ticks** | `symbol_info_tick` | Sim, via polling/background path | ✅ TC-D20 em `test_data_tester_matrix_external_rpyc.py`; bid/ask live confirmados em `test_external_rpyc_data_tester.py` | **Partial** |
| **Historical ticks** | `copy_ticks_range`, `copy_ticks_from` | Sim, por superfície RPC/wrapper | ✅ TC-D21 em `test_data_tester_matrix_external_rpyc.py`. **Atenção**: gateway RPyC rejeita `datetime` com `(-2, Invalid arguments)` — passar Unix timestamp `int` como `date_from` | **Partial** |
| **Trade ticks** | `copy_ticks_*` expõe campo `last`, mas `last=0.0` sempre para CFD indexes (USTEC/Tickmill) | Decisão documentada: `copy_ticks_*` tem semântica QuoteTick, não TradeTick | ✅ TC-D30 XFAIL em `test_external_rpyc_data_tester.py` confirma `last=0.0` live. TC-D30 documentado em `test_data_tester_matrix_external_rpyc.py` | **Partial** — não promover para Supported sem mapeamento MT5-native de TradeTick |
| **Bars** | `copy_rates_from_pos`, `copy_rates_range` | Sim, por superfície RPC/wrapper | ✅ TC-D40, TC-D41 em `test_data_tester_matrix_external_rpyc.py`; M1 e M5 validados live em `test_external_rpyc_data_tester.py` (USTEC) | **Partial** |
| **Order book** | `market_book_get` (disponível no wrapper) | Não — rejeição segura implementada | ✅ TC-D10 em `test_data_tester_matrix_external_rpyc.py` valida log de warning ao tentar subscribe | **Unsupported** |
| **Instrument status** | N/A | Não | Não | **Unsupported** |
| **Lifecycle** | `shutdown` | Sim, parcial para stop/unsubscribe | Parcial; lifecycle de cada subscription/request suportado ainda deve ter cobertura explícita | **Partial** |

---

## Execution Capabilities

Auditado contra `docs/execution_capability_matrix.md`.

| Capability | Gateway RPC disponível | Adapter suporta hoje | Teste determinístico existe | Status/documentação |
|---|---|---|---|---|
| **Market orders** | `order_send` | Sim, por wiring/submit path | Sim (`tests/integration/test_external_rpyc_execution_flow.py`), mas ainda deve provar lifecycle Nautilus completo, como submitted/accepted/filled ou reports equivalentes | **Partial** |
| **Limit orders** | `order_send` | Sim, parcial por wiring `order_send` | Parcial; precisa validar lifecycle, status e TIFs suportados | **Partial** |
| **Cancel orders** | `order_send` (`TRADE_ACTION_REMOVE`) | Sim, parcial por ticket/cancel path | Parcial; precisa cobrir cancel lifecycle, invalid cancel, stop cleanup e/ou batch behavior quando suportado | **Partial** |
| **Modify orders** | `order_send` (`TRADE_ACTION_MODIFY`) | Não no nível Nautilus operacional | Não | **Unsupported** |
| **Positions reconciliation** | `positions_get` | Sim, parcial por consulta/wrapper | Sim (`tests/integration/test_external_rpyc_execution_flow.py`), mas reconciliação Nautilus-level ainda deve ser explicitamente validada | **Partial** |
| **Orders history** | `history_orders_get` | Sim, parcial por consulta/wrapper | Sim (`tests/integration/test_external_rpyc_execution_flow.py`), mas geração de `OrderStatusReport`/reconciliação completa precisa cobertura explícita | **Partial** |
| **Deals history** | `history_deals_get` | Sim, parcial por consulta/wrapper | Sim (`tests/integration/test_external_rpyc_execution_flow.py`), mas `FillReport` ainda precisa implementação/cobertura completa | **Partial** |
| **Unsupported TIF/type** | N/A (lógica interna do adapter) | Planejado/necessário como comportamento de rejeição segura | Cobertura específica ainda deve validar rejeição antes do envio ao venue | **Planned** |

---

## Gaps Identificados

Os seguintes itens representam lacunas conhecidas entre a superfície RPC e o suporte efetivo do adapter, mapeados para planejamento futuro:

- **Order Book**: Embora o wrapper `MetaTrader5.py` exponha `market_book_get`, o adapter Nautilus não possui o componente de Order Book provider/subscriber implementado para MT5. Permanece como **Unsupported**.
- **Trade ticks**: **Decisão documentada (Step 06)**: para CFD indexes como USTEC no Tickmill-Demo, o campo `last` de `copy_ticks_*` é sempre `0.0`. Portanto `copy_ticks_*` fornece semântica de QuoteTick, não TradeTick. A capability permanece **Partial** até que um mapeamento MT5-native de TradeTick seja explicitamente definido e testado.
- **Bars em nível Nautilus**: TC-D40/D41 validados live (M1: 5 bars, M5: 10 bars do USTEC). Falta cobertura do fluxo Nautilus-level completo: parsing → `Bar` → handler. **Nota operacional**: gateway RPyC retorna `np.void` (numpy structured array) — usar indexação por nome (`bar["open"]`) em vez de `getattr`.
- **Modify Orders**: O gateway pode suportar modificação via `order_send`, mas o fluxo Nautilus operacional de modificação ainda não está suportado. Permanece como **Unsupported**.
- **Cancelamento em nível Nautilus**: O cancelamento unitário via ticket está funcional em nível parcial, mas o cancelamento em massa (`cancel_all_orders`), cancel-on-stop e rejeições de cancelamento ainda requerem cobertura mais robusta.
- **Lifecycle de market/limit orders**: `order_send` funcionando não prova, sozinho, o ciclo Nautilus completo de ordem submetida, aceita, preenchida, cancelada ou rejeitada.
- **Fill reports**: `history_deals_get` disponível não implica suporte completo a `FillReport`. É necessário converter deals MT5 em reports Nautilus, cobrir a reconciliação e atualizar a matriz de execução.
- **Instrument Status**: O MT5 não fornece streaming nativo de status de instrumento (Open/Closed) via API Python simples de forma eficiente; requer mapeamento customizado ou polling.
- **Unsupported TIF/type**: A rejeição de tipo de ordem ou TIF não suportado deve ser testada explicitamente, preferencialmente antes do envio ao venue.

---

## Regras de Interpretação

1.  **Existência de método != Capability**: A existência de um método `exposed_` no gateway RPyC ou no wrapper `MetaTrader5` não implica, por si só, que a capability NautilusTrader correspondente está suportada.
2.  **Critério de Suporte**: Uma capability só é declarada **Supported** quando houver comportamento produtivo implementado, fluxo Nautilus-level exercitado, documentação coerente e teste determinístico validando o comportamento.
3.  **Status parcial é esperado durante evolução**: Quando há superfície RPC e wiring funcional, mas ainda falta DataTester, ExecTester, reports, reconciliação ou fluxo Nautilus completo, use **Partial**.
4.  **Segurança em Falhas**: O modo `EXTERNAL_RPYC` deve lançar `RuntimeError` informativo se o gateway não expuser um método RPC obrigatório para uma capability declarada como **Supported**.
5.  **Matrizes são fonte operacional de status**: `docs/data_capability_matrix.md` e `docs/execution_capability_matrix.md` devem refletir o mesmo status desta auditoria. Se uma capability mudar de estado, atualize ambos os documentos.
6.  **Validação live é suplementar**: Testes com MT5 real/gateway RPyC real são úteis para validação operacional, mas não substituem cobertura determinística com fake bridge e fluxo Nautilus-level.

---

## Referências
- `docs/adapter_contract.md`
- `docs/terminal_access_contract.md`
- `docs/testing_contract.md`
- `docs/data_capability_matrix.md`
- `docs/execution_capability_matrix.md`
- `docs/decisions.md`
- `docs/remote_mt5_test_gateway.md`
- `docs/specs/spec_terminal_access_with_gateway.md`
