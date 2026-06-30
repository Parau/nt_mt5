## Homologação XP/B3 — status (2026-06-30)

### Coberto (live, pregão aberto)

| Área | Status | Relatório |
|------|--------|-----------|
| **Closed market** | **17/17** | `last_xp_closed_market_report.json` |
| **Feed open** | **7/7** — D01–D07, PF | `last_xp_open_market_feed_report.json` |
| **D06 gateway + D06-SVC + D21 open** | **2/2 + D21** | `last_xp_backlog_report.json`, `last_xp_d06_svc_report.json` |
| **Trade ticks D30/D31** | WINQ26 PASS | `last_xp_trade_ticks_report.json` |
| **Wave3** | **4/4** — D07, E10, E10b | `last_xp_wave3_report.json` |
| **Exec WDON26** | **21/21** | `last_xp_exec_report.json` |
| **Exec PETR4** | **21/21** | `last_xp_petr4_exec_report.json` |
| **Exec DI1F27** | **21/21** | `last_xp_di1f27_exec_report.json` |
| **PETR4 E01 smoke** | **3/3** | `last_xp_petr4_e01_report.json` |

**Conclusão:** baseline XP/B3 homologado — futuros (WDON26/WINQ26), equity (PETR4), DI (DI1F27), feed WS, exec core + hedging.

### Decisões de escopo

- **WIN$ / WDO$** excluídos dos runners live — série contínua, `TRADE_MODE=DISABLED`, sem bid/ask/exec. Homolog usa nominais (`WINQ26`, `WDON26`).
- **D06-SVC** (restart manual `NT5TickFeedService`) validado na XP (`run_d06_svc_homologation.py`, 2026-06-30) — mesmo código MQL5 Service que Tickmill.

### Pendências opcionais (não bloqueiam homologação)

| Item | Notas |
|------|-------|
| `run_xp_open_market.py` end-to-end | Redundante — peças já passaram isoladas |
| Tier 2 `@pytest.mark.live` XP | CI seletivo, se desejado |
| Parser WDON26 duplicado (FuturesContract + Cfd) | Cosmético nos logs |
| `trade_calc_mode` 32/33 no `venue_profile` | Alinhar constantes legadas |
| DI1F27 `price_semantics=yield_rate_percent` | Wiring closed; exec live OK |

### Runners XP (porta 18813)

```cmd
set MT5_HOST=127.0.0.1
set MT5_PORT=18813
set MT5_VENUE_PROFILE=xp_b3
set MT5_ACCOUNT_NUMBER=56822578
set MT5_BROKER=XPMT5-DEMO
set MT5_FEED_ENABLED=1
set MT5_ENABLE_LIVE_EXECUTION=1
set HOMOLOG_MULTI_SYMBOLS=WDON26,PETR4,DI1F27,WINQ26
```

| Runner | Cenários |
|--------|----------|
| `run_xp_closed_market.py` | Off-hours |
| `run_xp_open_market_feed.py` | Feed D01–D07 |
| `run_xp_backlog_homologation.py` | D06 gateway + D21 open |
| `run_d06_svc_homologation.py` | D06-SVC manual Service restart |
| `run_xp_exec_homologation.py` | Exec 21 cenários (`MT5_SYMBOL=`) |
| `run_xp_trade_ticks_homologation.py` | D30/D31 |
| `run_wave3_homologation.py` | D07 + E10/E10b |
| `run_d01_e01_smoke.py` | Smoke E01 por símbolo |
