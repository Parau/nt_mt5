## O que já está coberto (XP/B3 live)

| Área | Status |
|------|--------|
| **Closed market** | **17/17** — histórico, instrumentos, D21/D21-T, exec off-hours |
| **Open market — dados (feed)** | **7/7** — D01, D02, D03, D05, D06, D07, PF (`last_xp_open_market_feed_report.json`) |
| **Infra Docker** | Container `18813`, feed `8766`, service MQL5 OK |

Ou seja: **pipeline de dados em pregão está homologado**. O backlog de open market na doc (`proximos testes adaptador.md` § XP) ainda marca D02–D07 como OPEN — **precisa atualizar** para refletir o feed run.

---

## O que ainda falta (prioridade)

### 1. Execução open market (maior lacuna)
Nada da **wave exec** foi validada live na XP com `MT5_ENABLE_LIVE_EXECUTION=1`:

- **E01** — round-trip market (WDON26)
- **E02** — stops
- **E05 / E05b** — mass status + fill reports (`history_deals_get` na XP)
- **E81** — reconcile on start
- **Wave 2–4 Tickmill** (E03, E04, E06–E10, E43, hedging) — **sem runner XP dedicado**; só existem `run_wave*_homologation.py` apontando porta **18812**

Conta XP é **hedging** — E08/E10/E10b são **mais relevantes** que na Tickmill, não menos.

### 2. Cenários de feed opcionais
- **D06-SVC** — restart manual do `NT5TickFeedService` (só gateway restart passou)
- **D21 live** — no runner feed-only; closed já passou; `run_xp_open_market.py` inclui mas não rodou completo

### 3. Trade ticks live (perfil XP)
Matrices ainda dizem **live WS OPEN** para TC-D30/D31. Closed + wiring Tier 1 existem; **stream live de TradeTick** (ex. WINQ26) não foi homologado.

### 4. Documentação / matrices
- `res/proximos testes adaptador.md` — secção XP open desatualizada
- `docs/data_capability_matrix.md` / `execution_capability_matrix.md` — coluna **Live coverage** XP ainda **Partial/OPEN** na exec
- `docs/terminal_access_capability_audit.md` — “XP execution homologation not started”

### 5. Desenvolvimento (não bloqueia feed, mas vale fechar)
- Parser **WDON26** duplicado (FuturesContract + Cfd) — visto nos logs
- **`trade_calc_mode` 32/33** vs constantes legadas no `venue_profile` (`xp_b3_restrictions.md`)
- **FOK** na XP (`filling_mode=3`) — E06d nunca rodou em símbolo B3
- **DI1F27** `price_semantics=yield_rate_percent` — só wiring closed
- Tier 2 **`@pytest.mark.live`** específico XP (se quiser CI seletivo além da homologação manual)

---

## Resumo

**Não falta desenvolvimento crítico de feed** — o caminho WS → QuoteTick/bar está validado na XP.

**Falta homologar execução em pregão** (E01+ e waves hedging/reconcile) e **atualizar docs/matrices**. Próximo passo natural: `run_xp_open_market.py` com `MT5_PORT=18813`, exec ON, conta **sem posição aberta**, ou adaptar os runners `run_wave4` / `run_hedging_wave` para perfil `xp_b3`.
