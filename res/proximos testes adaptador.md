A ideia de **várias strategies de homologação** faz sentido — mas o caminho certo não é inventar strategies ad‑hoc; é alinhar com o que o Nautilus já define: **`DataTester`** (dados) e **`ExecTester`** (execução), mais um **pequeno conjunto de cenários MT5‑específicos** que esses testers não cobrem.

Referências upstream:
- [Data Testing Spec](https://nautilustrader.io/docs/latest/developer_guide/spec_data_testing)
- [Execution Testing Spec](https://nautilustrader.io/docs/latest/developer_guide/spec_exec_testing)

Princípio Nautilus: **validar dados antes de execução**; `ExecTester` com `LiveRiskEngineConfig(bypass=True)` e `reconciliation=True`.

---

## O que já têm (homologação actual)

| ID | O quê | Cobertura Nautilus |
|---|---|---|
| TC-HOM-PF | Bridge + símbolo | Pré-requisito |
| TC-HOM-D01 | N ticks quote (burst) | TC-D20 parcial |
| TC-HOM-D02 | Stream WS sustentado + gap | TC-D20 live real (diferencial vs poll) |
| TC-HOM-E01 | Market BUY → SELL round-trip | TC-E01 + TC-E06 parcial |
| TC-HOM-E02 | Stop / stop-limit pending | TC-E20–E23 parcial |

Também existem `tests/live/test_external_rpyc_data_tester.py` (TC-D01/D03/D20/D40/D41 via RPyC) e `tests/acceptance/test_live_*.py` (Tier 2 pytest). A homologação (`homologation/`) é o **gate manual end-to-end** com `TradingNode` — complementar, não duplicar Tier 1.

---

## Lacunas importantes (surpresas prováveis em produção)

### Dados (via Strategy / DataTester)

| Prioridade | Cenário | Porquê |
|---|---|---|
| Alta | **TC-HOM-D03** — barras live M1 via subscribe | TC-D40/D41 só parcialmente live; estratégias reais usam bars |
| Alta | **TC-HOM-D04** — histórico barras + quote ticks via `_request_*` | RPyC path separado do WS; regressões aqui não aparecem no D02 |
| Alta | **TC-HOM-D05** — unsubscribe on stop | TC-D70; leak de subscrições WS/RPyC |
| Média | **TC-HOM-D06** — reconnect WS (parar/reiniciar Service) | cursor + dedup; risco real pós-deploy |
| Média | **TC-HOM-D07** — multi-símbolo (BTCUSD + USTEC) | stress no Service e gateway |
| Média | **TC-HOM-D08** — `VenueProfile` rejeita trade ticks | TC-D30 live; confirmar que strategy não recebe `TradeTick` |
| Baixa | Order book subscribe → warning | TC-D10; documentado unsupported, mas bom smoke |
| Skip | Trade ticks, DOM, derivados | [`res/tickmill_restrictions.md`](res/tickmill_restrictions.md) |

### Execução (via ExecTester ou strategies finas)

| Prioridade | Cenário | Porquê |
|---|---|---|
| Alta | **TC-HOM-E03** — limit GTC + cancel | TC-E10/E40; pending orders no MT5 |
| Alta | **TC-HOM-E04** — cancel-on-stop / close-on-stop via disconnect | TC-E81/E82; já implementado no client, **não homologado live** |
| Alta | **TC-HOM-E05** — reconciliação on connect | TC-E84/E86; posição/ordem deixada numa sessão anterior |
| Média | **TC-HOM-E06** — limit IOC agressivo (fill) vs passivo (cancel) | TC-E13/E14; filling_mode=2 no Tickmill |
| Média | **TC-HOM-E07** — modify volume ou cancel-replace | TC-E30/E32; MT5 `TRADE_ACTION_MODIFY` |
| Média | **TC-HOM-E08** — hedging: duas posições same side | já há `test_live_hedging.py`; falta no harness homologação |
| Média | **TC-HOM-E09** — retcodes reais (volume inválido, stops inválidos) | fake nunca cobre; 10014, 10016 |
| Baixa | Brackets, post-only, GTD, MIT/LIT | **Unsupported** no adaptador / Tickmill |

### Edge cases MT5‑específicos (custom strategies — valor alto)

Estes são onde **strategies dedicadas** valem a pena, porque o `ExecTester` genérico não cobre:

1. **Primeiro tick bid/ask=0** após subscribe (legacy poll; menos relevante com WS).
2. **`history_deals_get` eventual** — fill no cache Nautilus antes do deal aparecer no MT5.
3. **Spread flutuante** — BTCUSD ~$10; ordens stop/limit devem respeitar `trade_stops_level`.
4. **Sessão fechada** — USTEC fora do horário US; homologação deve falhar de forma clara, não hang.
5. **Conta errada** — `config.account_id` ≠ login MT5 → rejeição no connect.
6. **RPyC drop mid-session** — exec client recovery vs data WS independente.
7. **Volume min/step** — 0.01 vs 0.001 rejeitado pelo terminal.
8. **Dois transportes simultâneos** — WS quotes + RPyC exec no mesmo `TradingNode` (arquitectura Opção B).

---

## Arquitectura recomendada (não multiplicar strategies à toa)

```
homologation/
  run_homologation.py          # orquestrador
  scenarios/
    preflight.py               # TC-HOM-PF ✓
    tick_stream.py             # TC-HOM-D02 ✓
    trading_node_suite.py      # TC-HOM-D01 + E01 ✓
    stop_orders.py             # TC-HOM-E02 ✓
    data_tester_suite.py       # NEW: DataTester configs por grupo
    exec_tester_suite.py       # NEW: ExecTester configs por grupo
    mt5_edges.py               # NEW: cenários MT5-only (reconnect, reconcile, retcodes)
```

**Padrão por cenário:** um `TradingNode` + uma strategy (`DataTester`, `ExecTester`, ou strategy mínima custom) + cleanup garantido.

### Usar testers oficiais Nautilus

Em vez de reimplementar lógica de ordens:

```python
from nautilus_trader.test_kit.strategies.tester_exec import ExecTester, ExecTesterConfig
# DataTester actor — ver nautilus_trader.test_kit (equivalente data side)
```

Configurar por cenário, por exemplo:

- **Smoke exec** (spec upstream): market open + 2 limits passive + stop + cancel/close on stop.
- **Data smoke**: subscribe quotes + request bars + unsubscribe on stop.
- **Tickmill profile**: `subscribe_trades=False`, `subscribe_book=False` no ExecTester.

As vossas strategies custom (`_SuiteStrategy`, `_StreamStrategy`) ficam só onde o tester oficial não chega (gap watch D02, fases sequenciais D01→E01).

---

## Matriz de execução sugerida (paper Tickmill-Demo)

| Run | Símbolo | Quando | Cenários |
|---|---|---|---|
| **Nightly crypto** | BTCUSD | 24/7 | PF, D02, D01, E01, E02, E03, E06 |
| **Session US** | USTEC | mercado aberto | + D03/D04 bars, E08 hedging |
| **Weekly deep** | BTCUSD + USTEC | manual | D05–D07, E04–E05 reconcile, E09 retcodes, WS reconnect |
| **Pre-release gate** | ambos | antes de tag | `run_homologation.py` completo + weekly deep |

Variáveis: `MT5_FEED_ENABLED=1`, Service activo, `MT5_ENABLE_LIVE_EXECUTION=1` só para cenários E*.

---

## O que **não** vale homologar com strategy live

Alinhado com [`res/tickmill_restrictions.md`](res/tickmill_restrictions.md) e matrizes:

- `TradeTick` / histórico trade ticks
- Order book / DOM
- Brackets, post-only, reduce-only, GTD
- Options (TC-E90+)

Homologar estes como **Unsupported** (warning/`OrderDenied`) — um cenário curto basta, não investir em strategies de trading.

---

## Relação entre camadas (evitar duplicação)

| Camada | Papel |
|---|---|
| **Tier 1 pytest + fake bridge** | Regressão CI; autoridade para wiring |
| **`tests/live/` + `tests/acceptance/`** | Tier 2 pytest pontual (retcodes, stoplimit bug) |
| **`homologation/`** | Gate operacional pré-produção: **TradingNode completo**, WS+ RPyC, relatório JSON, múltiplos cenários numa corrida |

Não mover tudo para pytest live — a homologação é o sítio certo para **suites longas** (D02 120s, stream gaps, reconcile multi-sessão).

---

## Próximos passos concretos (ordem sugerida)

1. **`data_tester_suite.py`** — barras live + histórico + unsubscribe (D03–D05).
2. **`exec_tester_suite.py`** — limit GTC+cancel, cancel-on-stop live (E03–E04).
3. **`mt5_edges.py`** — reconcile session restart (E05), retcode inválido (E09), WS reconnect (D06).
4. Documentar mapa **TC-HOM-* → TC-D/E** em `homologation/README` ou spec §17.
5. Parametrizar símbolo/calc_mode: BTCUSD (CFD), USTEC (CFDINDEX), opcional EURUSD (FOREX).

---

**Resumo:** sim, devem ter **várias strategies** — mas organizadas como **cenários homologação** mapeados ao spec Nautilus (`DataTester` + `ExecTester`) + **~5 edge cases MT5**. Isso dá confiança de produção sem reinventar testes nem homologar capacidades que o Tickmill não oferece.

Se quiseres implementar isto, muda para Agent mode e posso começar por `data_tester_suite.py` + `exec_tester_suite.py` integrados no `run_homologation.py`.