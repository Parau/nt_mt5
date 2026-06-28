# Homologation test tracker — `nt_mt5` adapter

Living checklist for manual homologation against **Tickmill-Demo** (real MT5 + RPyC bridge).  
Run closed-market suite: `homologation/run_closed_market.py`  
Run full suite (needs open market + WS for D02): `homologation/run_homologation.py`

| Run | Date (UTC) | Report | Result |
|-----|------------|--------|--------|
| Closed market | 2026-06-28 01:28 | `homologation/last_closed_market_report.json` | **11/11 PASS** (BTCUSD, account 25339175) |
| Open market (full) | 2026-06-28 01:29–01:32 | `homologation/last_open_market_report.json` | **10/10 PASS** (BTCUSD, WS feed + live exec) |
| **D02 stream 120s** | 2026-06-28 | `homologation/run_feed_smoke.py` (console) | **PASS** — 488 ticks, max gap 5.1s, `transport=ws_feed` |
| **Wave 2** | 2026-06-28 01:51 | `homologation/last_wave2_report.json` | **7/7 PASS** — D06, D07, E06–E09 |
| **Wave 3 (E10)** | 2026-06-28 02:0x | `homologation/run_e10_smoke.py` (console) | **2/2 PASS** — E10, E10b (after production fixes) |
| **Wave 3 (full)** | 2026-06-28 02:13 | `homologation/last_wave3_report.json` | **3/4 PASS** — E10, E10b OK · **D07 FAIL** (USTEC WS=0) |
| **D06-SVC** | 2026-06-28 02:43 | `homologation/last_d06_svc_report.json` | **2/2 PASS** — baseline=53 dup=0 service_restart=manual |

Previous baseline: closed **10/10** and open **9/10 effective** on 2026-06-27 (pre-D04b; see journal notes below).

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

## Closed market — DONE (2026-06-28)

Runnable anytime (session may be closed; historical data still available).

| ID | Scenario | Nautilus map | Result | Notes |
|----|----------|--------------|--------|-------|
| TC-HOM-PF | Bridge + account + `symbol_info` | Pre-req | **DONE** | login 25339175; bid=60106.5 ask=60116.5 |
| TC-HOM-D04a | Hist bars M1+M5 `copy_rates_from_pos` | TC-D40/D41 | **DONE** | M1×5 M5×10; sample C=60089.5 |
| TC-HOM-D04b | `DataClient._request_bars` E2E | TC-D40 | **DONE** | **D04b refactor live** — 5 M1 bars, close=60137.5 |
| TC-HOM-D04c | Hist ticks `copy_ticks_from` (24h, n=500) | TC-D21 partial | **DONE** | 500 ticks; last=0.0 confirms QuoteTick-only |
| TC-HOM-D01-CM | Instrument load via `DataClient._connect` | TC-D01 | **DONE** | BTCUSD CFD, calc_mode=2 |
| TC-HOM-D02-CM | `SubscribeInstruments` → warning, no raise | TC-D02 | **DONE** | |
| TC-HOM-D08 | `SubscribeTradeTicks` gated by `VenueProfile` | TC-D30 | **DONE** | |
| TC-HOM-D08b | `RequestTradeTicks` gated by profile | TC-D31 | **DONE** | |
| TC-HOM-D10 | Order book subscribe → warning | TC-D10 | **DONE** | |
| TC-HOM-E-CONN | Exec connect + account validation | TC-E80 partial | **DONE** | login 25339175 |
| TC-HOM-E-EDGE1 | Wrong `account_id` → `ConnectionError` | Edge | **DONE** | |

**Harness:** `homologation/scenarios/closed_market_suite.py` + `homologation/run_closed_market.py`

**D04b change (2026-06-28):** on-demand `_request_bars` now uses MT5-native `copy_rates_from_pos` / `copy_rates_range` (IB `req_historical_data` removed). Tier 1: `test_tc_d40_*` + fake-bridge e2e in matrix tests.

---

## Open market — DONE (2026-06-28, BTCUSD session active)

Verified against harness JSON (account 25339175). Exec order IDs from this run below.

| ID | Scenario | Result | Evidence |
|----|----------|--------|----------|
| TC-HOM-PF | Bridge pre-flight | **DONE** | bid=60100.0 ask=60110.0 |
| TC-HOM-D01 | Quote tick burst (TradingNode) | **DONE** | 3 ticks (last bid=60101.0 ask=60111.0) |
| TC-HOM-D02 | WS sustained stream | **DONE** | **60s:** 242 ticks, max gap 5.6s · **120s:** 488 ticks, max gap 5.1s (`run_feed_smoke.py`, 2026-06-28) |
| TC-HOM-D06 | WS gateway restart + dedup | **DONE** | Gateway restart, dup=0 post-restart (`feed_resilience.py`, 2026-06-28) |
| TC-HOM-D06-SVC | Full **Service** stop/start + dedup | **DONE** | Manual Service restart; quote resubscribe on `hello` replay fix (2026-06-28) |
| TC-HOM-D07 | Multi-symbol WS quotes | **PARTIAL** | RPyC quote OK for both; **WS stream:** BTCUSD=141 ticks, **USTEC=0** (2026-06-28 wave3) — adapter `subscribe` OK with empty `InpSymbols` |
| TC-HOM-D03 | Live bar subscribe M1 | **DONE** | 1 M1 bar via WS `subscribe_bars` → `op:bar` |
| TC-HOM-D05 | Unsubscribe on stop (quotes/bars) | **DONE** | Quotes + bars via WS when `MT5_FEED_ENABLED=1` |
| TC-HOM-E01 | Market BUY → SELL round-trip | **DONE** | BUY 0.01@60111.50 → SELL @60099.50 |
| TC-HOM-E02 | Stop pending + cleanup cancel | **DONE** | BUY STOP #264627035; SELL STOP #264627036 |
| TC-HOM-E03 | Limit GTC + cancel | **DONE** | BUY LIMIT @57109.72 #264627039; retry retcode=10013 (already gone) |
| TC-HOM-E04 | `cancel_on_stop` / `close_on_stop` | **DONE** | E04a limit #264627040 cancelled on stop; E04b position closed |
| TC-HOM-E05 | `generate_mass_status` vs bridge | **DONE** | positions=0; `positions_get(BTCUSD)=0` |
| TC-HOM-E06 | IOC fill vs passive limit | **DONE** | MARKET IOC (E06a) + LIMIT IOC mapping/cancel @ask (E06c) + passive (E06b) — Tickmill instant fill via MARKET only |
| TC-HOM-E07 | Modify pending volume | **DONE** | `TRADE_ACTION_MODIFY` + `exposed_orders_get`; Tickmill needs price nudge with volume |
| TC-HOM-E08 | Hedging same-side legs | **DONE** | Two BUY 0.01 → `positions_get` ≥ 2 (2026-06-28) |
| TC-HOM-E09 | Real retcodes | **DONE** | Invalid volume + invalid BUY STOP rejected (2026-06-28) |
| TC-HOM-E10 | Multi-leg `generate_mass_status` vs bridge | **DONE** | 2× BUY + 1× SELL → bridge=3 L=0.02 S=0.01 = reports (2026-06-28) |
| TC-HOM-E10b | `close_on_stop` with N>1 legs | **DONE** | 2 legs → 0 via disconnect (2026-06-28) |

### Prior run (2026-06-27, journal cross-check)

Journal window **21:10–21:26** server time (~18:10–18:26 BRT). Same scenarios passed; sample tickets: E01 #264624623/#264624624, E03 #264624916, E04b #264624918/#264624919. No orphaned BTCUSD positions at **21:26:28**.

### Production bug fixed during homologation (2026-06-27)

**`close_on_stop`** sent `type_filling=2` (RETURN). Tickmill BTCUSD requires **IOC (`type_filling=1`)**.  
Journal proof: `21:16:37 failed market sell … [Unsupported filling mode]` on position #264624652; after fix, closes succeed.

Fix: `nautilus_mt5/execution.py` — `type_filling: 1` in `_close_all_positions_on_stop`.

### Production bugs fixed during wave 3 / E10 (2026-06-28)

1. **`get_positions` empty book** — `account.py` called `positions_get(group="*{login}*")`; MT5 `group` filters **symbol groups**, not account login → always empty → `generate_mass_status: 0 position(s)` while bridge had legs. Fix: unfiltered `positions_get()`.
2. **SELL hedge routing** — every SELL attached the first BUY ticket, preventing a third SHORT leg on hedging accounts with 2+ longs. Fix: attach `position_ticket` only when **exactly one** open long exists (round-trip flatten).
3. **Homologation cleanup** — `_close_symbol_positions` used `pos.get("type") or -1`, treating BUY (`type=0`) as falsy → sent BUY to close BUY (retcode 10013). Fix: explicit `None` check for `type`.
4. **E05/E10 report counting** — `mass.position_reports` is a `dict[InstrumentId, list[…]]`, not a flat list; `len(dict)` under-counted legs.
5. **WS reconnect quote gap** — after Service/gateway restart, adapter replayed bar subs on `hello` but not quote `subscribe` → 0 ticks post-restart (D06-SVC fail). Fix: `_replay_pending_quote_subscriptions()` in `data.py`.
6. **`_modify_order` used `place_order`** — pending modify sent wrong action; fix: `MetaTrader5ClientOrderMixin.modify_order()` with `TRADE_ACTION_MODIFY`. Tickmill BTCUSD applies price changes but not volume-only modify (broker retcode 10025).

Fix: `nautilus_mt5/client/account.py`, `nautilus_mt5/client/order.py`, `nautilus_mt5/execution.py`, `nautilus_mt5/data.py`, `homologation/scenarios/mt5_edges.py`, `homologation/scenarios/position_reconcile_suite.py`, `homologation/support/bridge_probe.py`.

### Harness notes (not adapter bugs)

- Post-cancel verification retry → `[Invalid request]` / retcode **10013** in journal is **expected** (order already cancelled).
- Do not call raw `exposed_order_send` on bridge for cancel probes — use `MetaTrader5.order_send` wrapper (bridge debug print crashes on some paths).
- Disconnect teardown `CancelledError` in `MetaTrader5Client._on_task_completed` — **fixed** (2026-06-28); guard `task.cancelled()` before `task.exception()`.

---

### Wave 3 — exec reconciliation — DONE (2026-06-28)

Harness: `homologation/scenarios/position_reconcile_suite.py`, runners `run_e10_smoke.py` / `run_wave3_homologation.py`.

| ID | Result | Notes |
|----|--------|-------|
| TC-HOM-E10 | **DONE** | Controlled 2× BUY + 1× SELL; bridge vs `mass_status.position_reports[BTCUSD…]` |
| TC-HOM-E10b | **DONE** | `close_on_stop` flattens 2-leg book |

---

## OPEN — next homologation waves

| Priority | ID | Scenario | When |
|----------|-----|----------|------|
| Média | TC-HOM-D07 | Re-run multi-symbol WS | US session + USTEC live ticks; empty `InpSymbols` OK (adapter subscribes) |

**Done (2026-06-28):** D06-SVC, E06c SELL LIMIT IOC @bid, E07 + bridge v0.7 `exposed_orders_get`, Service v1.04 bar-sub cleanup on WS disconnect.

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
| `closed_market_suite.py` | Closed-market gate (+ D04b) | **DONE** |
| `run_closed_market.py` | Runner + JSON report | **DONE** |
| `data_tester_suite.py` | D03, D05 | **DONE** |
| `feed_resilience.py` | D06 gateway restart dedup | **DONE** |
| `multi_symbol.py` | D07 multi-symbol WS | **DONE** |
| `run_wave2_homologation.py` | D06–D07, E06–E09 only | **DONE** |
| `exec_tester_suite.py` | E03, E06–E08 | **DONE** |
| `mt5_edges.py` | E04, E05, E09 | **DONE** |
| `position_reconcile_suite.py` | E10, E10b | **DONE** |
| `run_wave3_homologation.py` | D06-SVC, D07, E10, E10b | **DONE** |
| `run_e10_smoke.py` | E10 + E10b only | **DONE** |
| `run_d06_svc_homologation.py` | D06 with manual Service restart | **DONE** |
| `run_e06_e07_homologation.py` | E06 (incl. E06c) + E07 low-priority | **DONE** |

---

## How to run

**Closed market:**
```cmd
set MT5_HOST=127.0.0.1
set MT5_PORT=18812
set MT5_SYMBOL=BTCUSD
set HOMOLOG_REPORT_JSON=homologation/last_closed_market_report.json
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

Start `NT5TickFeedService` in MT5 before D02/D03/D05.

**Wave 2 only (D06–D07, E06–E09):**
```cmd
set MT5_HOST=127.0.0.1
set MT5_PORT=18812
set MT5_SYMBOL=BTCUSD
set MT5_FEED_ENABLED=1
set MT5_ENABLE_LIVE_EXECUTION=1
set HOMOLOG_MULTI_SYMBOLS=BTCUSD,USTEC
set HOMOLOG_REPORT_JSON=homologation/last_wave2_report.json
E:\miniconda\envs\trading\python.exe homologation\run_wave2_homologation.py
```

Optional D06 full Service restart: add `set HOMOLOG_D06_REQUIRE_SERVICE_RESTART=1` and stop/start `NT5TickFeedService` when prompted.

**Wave 3 (OPEN pendencies + E10):**
```cmd
set MT5_HOST=127.0.0.1
set MT5_PORT=18812
set MT5_SYMBOL=BTCUSD
set MT5_FEED_ENABLED=1
set MT5_ENABLE_LIVE_EXECUTION=1
set HOMOLOG_MULTI_SYMBOLS=BTCUSD,USTEC
set HOMOLOG_REPORT_JSON=homologation/last_wave3_report.json
E:\miniconda\envs\trading\python.exe homologation\run_wave3_homologation.py
```

**E10 only:**
```cmd
set MT5_ENABLE_LIVE_EXECUTION=1
E:\miniconda\envs\trading\python.exe homologation\run_e10_smoke.py
```

**D02 stream only (120s):**
```cmd
set MT5_HOST=127.0.0.1
set MT5_PORT=18812
set MT5_SYMBOL=BTCUSD
set MT5_FEED_ENABLED=1
set HOMOLOG_STREAM_SECS=120
E:\miniconda\envs\trading\python.exe homologation\run_feed_smoke.py
```

**PowerShell** (same vars): `$env:MT5_HOST='127.0.0.1'; $env:MT5_PORT='18812'; …`

### Tickmill BTCUSD session (server ≈ EET, UTC+2)

Convert: **BRT ≈ server − 5h**. See [`res/tickmill_restrictions.md`](tickmill_restrictions.md).
