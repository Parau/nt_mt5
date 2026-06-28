# Homologation test tracker — `nt_mt5` adapter

Living checklist for manual homologation against **Tickmill-Demo** (real MT5 + RPyC bridge).  
Run closed-market suite: `homologation/run_closed_market.py`  
Run full suite (needs open market + WS for D02): `homologation/run_homologation.py`

| Run | Date | Report | Result |
|-----|------|--------|--------|
| Closed market | 2026-06-27 | `homologation/last_closed_market_report.json` | **10/10 PASS** (BTCUSD, session closed) |
| Open market (full) | 2026-06-27 ~21:10–21:26 server | `homologation/last_open_market_report.json` | **9/10 effective PASS** — see notes below |

References: [`res/tickmill_restrictions.md`](tickmill_restrictions.md), [`docs/data_capability_matrix.md`](../docs/data_capability_matrix.md), [`docs/execution_capability_matrix.md`](../docs/execution_capability_matrix.md)

---

## Legend

| Status | Meaning |
|--------|---------|
| **DONE** | Verified live on real bridge (date noted) |
| **OPEN** | Requires market open / live ticks / orders |
| **BLOCKED** | Adapter or bridge gap — not a homologation env issue |
| **SKIP** | Intentionally unsupported (Tickmill profile) |
| **TODO** | Not yet implemented in homologation harness |

---

## Closed market — DONE (2026-06-27)

Runnable anytime (session may be closed; historical data still available).

| ID | Scenario | Nautilus map | Result | Notes |
|----|----------|--------------|--------|-------|
| TC-HOM-PF | Bridge + account + `symbol_info` | Pre-req | **DONE** | Frozen bid/ask OK when session closed |
| TC-HOM-D01-CM | Instrument load via `DataClient._connect` | TC-D01 | **DONE** | BTCUSD CFD, calc_mode=2 |
| TC-HOM-D04a | Hist bars M1+M5 `copy_rates_from_pos` | TC-D40/D41 | **DONE** | Via `MetaTrader5Client` → real bridge |
| TC-HOM-D04c | Hist ticks `copy_ticks_from` (24h, n=500) | TC-D21 partial | **DONE** | last=0.0 confirms QuoteTick-only |
| TC-HOM-D02-CM | `SubscribeInstruments` → warning, no raise | TC-D02 | **DONE** | |
| TC-HOM-D08 | `SubscribeTradeTicks` gated by `VenueProfile` | TC-D30 | **DONE** | |
| TC-HOM-D08b | `RequestTradeTicks` gated by profile | TC-D31 | **DONE** | |
| TC-HOM-D10 | Order book subscribe → warning | TC-D10 | **DONE** | |
| TC-HOM-E-CONN | Exec connect + account validation | TC-E80 partial | **DONE** | login 25339175 |
| TC-HOM-E-EDGE1 | Wrong `account_id` → `ConnectionError` | Edge | **DONE** | |

**Harness:** `homologation/scenarios/closed_market_suite.py` + `homologation/run_closed_market.py`

---

## Open market — DONE (2026-06-27, BTCUSD session active)

Verified against MT5 trade journal (account 25339175) and harness JSON.  
Journal window: **21:10–21:26** server time (~18:10–18:26 BRT).

| ID | Scenario | Result | Journal / evidence |
|----|----------|--------|-------------------|
| TC-HOM-PF | Bridge pre-flight | **DONE** | login 25339175, Tickmill-Demo |
| TC-HOM-D01 | Quote tick burst (TradingNode) | **DONE** | WS + RPyC quotes |
| TC-HOM-D02 | WS sustained stream 60s | **DONE** | 203 ticks, max gap 4.3s, `transport=ws_feed` |
| TC-HOM-E01 | Market BUY → SELL round-trip | **DONE** | #264624623 @60049.50 → #264624624 @60039.50; also #264624528/#264624529 |
| TC-HOM-E02 | Stop pending + cleanup cancel | **DONE** | #264624648/#264624649 (and #264624547/#264624548) placed + cancelled |
| TC-HOM-D05 | Unsubscribe on stop (quotes) | **DONE** | Quote WS unsubscribe OK; bar leg **SKIP** (same gap as D03) |
| TC-HOM-E03 | Limit GTC + cancel | **DONE** | #264624916 @57056.52 → cancel OK; retry cancel `[Invalid request]` = expected (already gone) |
| TC-HOM-E04a | `cancel_on_stop` on pending | **DONE** | #264624917 limit placed → cancel on disconnect |
| TC-HOM-E04b | `close_on_stop` on position | **DONE** | #264624918 buy → #264624919 close; earlier failures at 21:16:37 were **`Unsupported filling mode`** (bug, fixed) |
| TC-HOM-E05 | `generate_mass_status` vs bridge | **DONE** | Positions reconciled; `positions_get(BTCUSD)=0` at end of journal |

### BLOCKED — adapter/bridge gap (not env failure)

| ID | Scenario | Result | Root cause |
|----|----------|--------|------------|
| TC-HOM-D03 | Live bar subscribe M1 | **BLOCKED** | Bridge lacks `exposed_req_real_time_bars`, `exposed_cancel_historical_data`. Native hist via `copy_rates_from_pos` works (D04a). |
| TC-HOM-D04b | `DataClient._request_bars` E2E | **BLOCKED** | Same IB-style path; needs MT5-native bar request refactor |

### Production bug fixed during homologation

**`close_on_stop`** sent `type_filling=2` (RETURN). Tickmill BTCUSD requires **IOC (`type_filling=1`)**.  
Journal proof: `21:16:37 failed market sell … [Unsupported filling mode]` on position #264624652; after fix, closes succeed (#264624919, #264624977).

Fix: `nautilus_mt5/execution.py` — `type_filling: 1` in `_close_all_positions_on_stop`.

### Harness notes (not adapter bugs)

- Post-cancel verification retry → `[Invalid request]` in journal is **expected** (order already cancelled).
- Do not call raw `exposed_order_send` on bridge for cancel probes — use `MetaTrader5.order_send` wrapper (bridge debug print crashes on some paths).

---

## OPEN — next homologation waves

| Priority | ID | Scenario | When |
|----------|-----|----------|------|
| Alta | TC-HOM-D02 | Re-run WS stream **120s** + gap watch | BTCUSD session |
| Média | TC-HOM-D06 | WS Service stop/start + cursor dedup | Service + open market |
| Média | TC-HOM-D07 | Multi-symbol BTCUSD + USTEC | USTEC US session |
| Média | TC-HOM-E06 | Limit IOC fill vs passive cancel | Market open |
| Média | TC-HOM-E07 | Modify volume / cancel-replace | Pending order |
| Média | TC-HOM-E08 | Hedging two positions same side | `test_live_hedging.py` parity |
| Média | TC-HOM-E09 | Real retcodes (bad volume/stops) | Market open |

### Tickmill BTCUSD session (server ≈ EET, UTC+2)

Convert: **BRT ≈ server − 5h**. See [`res/tickmill_restrictions.md`](tickmill_restrictions.md).

---

## SKIP — do not homologate as Supported

Per [`res/tickmill_restrictions.md`](tickmill_restrictions.md):

- Trade ticks live/historical (TC-D30/D31) — **Unsupported**
- Order book / DOM (TC-D10–D15) — **Unsupported**
- Brackets, post-only, GTD, MIT/LIT, options — **Unsupported**

---

## Implementation backlog (homologation harness)

| File | Purpose | Status |
|------|---------|--------|
| `closed_market_suite.py` | Closed-market gate | **DONE** |
| `run_closed_market.py` | Runner + JSON report | **DONE** |
| `data_tester_suite.py` | D03, D05 | **DONE** (D03 reports BLOCKED when bridge gap) |
| `exec_tester_suite.py` | E03 | **DONE** (E06–E09 TODO) |
| `mt5_edges.py` | E04, E05 | **DONE** (D06, E09 TODO) |

---

## How to run

**Closed market:**
```cmd
set MT5_HOST=127.0.0.1
set MT5_PORT=18812
set MT5_SYMBOL=BTCUSD
E:\miniconda\envs\trading\python.exe homologation\run_closed_market.py
```

**Full homologation (market open):**
```cmd
set MT5_HOST=127.0.0.1
set MT5_PORT=18812
set MT5_SYMBOL=BTCUSD
set MT5_FEED_ENABLED=1
set MT5_ENABLE_LIVE_EXECUTION=1
set HOMOLOG_REPORT_JSON=homologation/last_open_market_report.json
E:\miniconda\envs\trading\python.exe homologation\run_homologation.py
```

Start `NT5TickFeedService` in MT5 before D02/D05.

---

## Bridge / journal cross-check (2026-06-27)

MT5 journal confirms all exec scenarios; no orphaned BTCUSD positions at **21:26:28**.  
Pending limits from debug runs were cancelled. Double-cancel `[Invalid request]` lines match harness verification, not production failures.
