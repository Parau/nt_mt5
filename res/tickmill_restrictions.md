# Tickmill-Demo — broker profile (capabilities and restrictions)

Empirical profile for the `nt_mt5` adapter. Documents what Tickmill-Demo exposes through the **native MT5 terminal** (ground truth), independent of RPyC or the Python bridge.

Covers **account capabilities** (hedging, leverage, demo mode) and **symbol capabilities** (ticks, DOM, sessions, execution). Use when configuring `TICKMILL_DEMO_PROFILE`, planning homologation windows, or deciding broker-limited vs adapter-limited behaviour.

---

## Provenance

| Field | Value |
|-------|-------|
| Server | `Tickmill-Demo` |
| Company | Tickmill Ltd |
| Login | 25339175 |
| Terminal build | 5833 |
| Probe date (declared) | 2026-06-28 03:04:44 (server time) |
| Probe date (live OrderCheck) | **2026-06-29 16:58–16:59** (server time, Mon session open) |
| Method | MQL5 scripts in the MT5 terminal (ad-hoc, not deployed) |
| Scripts | [`probe_tickmill_market_off_hours.mq5`](../MQL5/refactoring/scripts/probe/probe_tickmill_market_off_hours.mq5), [`probe_tickmill_market_live.mq5`](../MQL5/refactoring/scripts/probe/probe_tickmill_market_live.mq5) |
| Output files | `MQL5/Files/probe_tickmill_off_Tickmill-Demo_25339175.txt`, `MQL5/Files/probe_tickmill_live_Tickmill-Demo_25339175.txt` |

Legacy probe (2026-06-28): [`teste_intrumento_infos_tickmill.mq5`](../MQL5/refactoring/scripts/teste_intrumento_infos_tickmill.mq5) → `probe_broker_Tickmill-Demo_25339175.txt` (same **declared** symbol fields; no `OrderCheck`).

Earlier Python/RPyC probes (`homologation/tools/probe_tick_semantics*.py`) reached the same tick-semantics conclusions.

### How to re-run

1. Copy `MQL5/refactoring/scripts/probe/` to `Terminal\<hash>\MQL5\Scripts\probe\`.
2. Compile `probe_tickmill_market_off_hours.mq5` and/or `probe_tickmill_market_live.mq5` in MetaEditor.
3. Attach to any chart while logged into the target account.
4. Default inputs probe `USTEC,BTCUSD`; edit `InpSymbols` for other symbols.
5. Run **`market_live`** during trade session for `OrderCheck` filling ground truth.
6. Compare output with this document and update if the broker profile changes.

### Time zone note

Session hours and `TimeCurrent()` in the probe are **server time** (Tickmill-Demo ≈ **EET, UTC+2** in this run).  
Approximate conversion to **BRT (UTC−3):** `BRT ≈ server_time − 5 hours`. Do not treat MT5 Specification UI times as UTC.

---

## Account capabilities (login 25339175)

| Property | Value | Adapter implication |
|----------|-------|---------------------|
| `ACCOUNT_MARGIN_MODE` | **2 — RETAIL_HEDGING** | Multiple positions per symbol; **close orders must use `position=<ticket>`** |
| `ACCOUNT_TRADE_MODE` | **0 — DEMO** | Paper account; not live funds |
| `ACCOUNT_TRADE_ALLOWED` | 1 | Trading enabled |
| `ACCOUNT_TRADE_EXPERT` | 1 | EAs / Services allowed |
| `ACCOUNT_LEVERAGE` | **30** | |
| `ACCOUNT_LIMIT_ORDERS` | 200 | Max pending orders |
| `ACCOUNT_MARGIN_SO_MODE` | 0 | |
| `ACCOUNT_CURRENCY` | USD | |
| `TERMINAL_CONNECTED` | 1 | |
| `TERMINAL_TRADE_ALLOWED` | 1 | |

**Not netting:** this is **hedging** account semantics. Confirmed live in `tests/acceptance/test_live_hedging.py` and exec smoke tests. Do not assume net position merge on close.

---

## Summary (adapter-facing)

| Capability | USTEC | BTCUSD | Adapter status |
|------------|-------|--------|----------------|
| Quote ticks (bid/ask) | Yes (in session) | Yes (in session) | **Supported** (WS feed + legacy RPyC snapshot) |
| Trade ticks (`last` / volume) | No | No | **Unsupported** (`TICKMILL_DEMO_PROFILE`) |
| Depth of market / order book | No | No | **Unsupported** |
| Execution (market, pending, etc.) | Yes (in session) | Yes (in session) | **Supported** |
| Historical bars / ticks | Yes | Yes | **Supported** (RPyC / `copy_rates_*`, `copy_ticks_*`) |
| Hedging account | — | — | **Supported** (position-ticket close path) |
| Filling (market) | IOC only | IOC only | **IOC** (`SYMBOL_FILLING_MODE=2`; FOK/RETURN rejected) |

### Filling — declared vs observed (2026-06-29 live probe)

| Symbol | Declared (`SymbolInfo`) | Observed (`OrderCheck` market deal) |
|--------|-------------------------|-------------------------------------|
| USTEC | bitmask **2** → IOC only | FOK **FAIL** `10030 INVALID_FILL`; IOC **OK**; RETURN **FAIL** `10030` |
| BTCUSD | bitmask **2** → IOC only | FOK **FAIL** `10030 INVALID_FILL`; IOC **OK**; RETURN **FAIL** `10030` |

**Conclusion:** USTEC and BTCUSD are **identical** on Tickmill-Demo for filling. The adapter `validate_filling_mode()` correctly rejects explicit **FOK** when bitmask lacks bit 0. **DAY** limit orders use `ORDER_FILLING_RETURN` via `map_filling_type(GTC/DAY)` and remain valid.

**Homologation note:** TC-HOM-E06d (passive FOK limit) must **not** expect MT5 accept on Tickmill IOC-only symbols — expect adapter pre-venue reject or broker `INVALID_FILL` on market FOK. E06e (DAY limit) remains valid.

---

## USTEC (US Tech 100 Index)

**Path:** `CFD-2\USTEC`  
**Calc mode:** `SYMBOL_TRADE_CALC_MODE=3` (CFDINDEX)

### Symbol metadata

| Property | Value | Notes |
|----------|-------|-------|
| `SYMBOL_TICKS_BOOKDEPTH` | **0** | No DOM |
| `SYMBOL_LAST` | **0.0** | No last-trade price |
| `SYMBOL_SPREAD` | 80 | Floating; ~0.80 pts at 2 digits |
| `SYMBOL_TRADE_MODE` | FULL (4) | |
| `SYMBOL_FILLING_MODE` | 2 | **IOC only** (bitmask decode) |
| `SYMBOL_ORDER_MODE` | 127 | Broad order-type bitmask |
| Volume | min 0.01, max 250, step 0.01 | |

### Sessions (server time)

| Day | Quote | Trade |
|-----|-------|-------|
| SUN | closed | closed |
| MON–THU | 01:00–00:00 | 01:00–00:00 |
| FRI | 01:00–23:58 | 01:00–23:58 |
| SAT | closed | closed |

`00:00` end time = midnight wrap (session runs from 01:00 through end of calendar day). **No US index stream on Sat/Sun server time.** Plan USTEC homologation **Mon–Fri** only.

**BRT hint (Mon open):** server Mon 01:00 ≈ **Sun 20:00 BRT**.

### Depth of market

```
MarketBookAdd(USTEC) => FALSE  err=4901  ticks_bookdepth=0
```

### Tick semantics (`CopyTicks`, n=20, Mon 16:58 server — session open)

| Observation | Result |
|-------------|--------|
| `last` | **0.0** |
| Tick flags | **6** (bid+ask only) |
| `TICK_FLAG_LAST` / volume | **0** (20/20 ticks bid+ask) |

Live prices advancing; `SYMBOL_TIME` current at probe.

---

## BTCUSD (Bitcoin CFD)

**Path:** `Cryptos\BTCUSD`  
**Calc mode:** `SYMBOL_TRADE_CALC_MODE=2` (CFD)

### Symbol metadata

| Property | Value | Notes |
|----------|-------|-------|
| `SYMBOL_TICKS_BOOKDEPTH` | **0** | No DOM |
| `SYMBOL_LAST` | **0.0** | |
| `SYMBOL_SPREAD` | 1000 | Floating; ~**$10.00** at 2 digits |
| `SYMBOL_TRADE_MODE` | FULL (4) | |
| `SYMBOL_FILLING_MODE` | 2 | **IOC only** |
| `SYMBOL_ORDER_MODE` | 127 | |
| Volume | min 0.01, max 30, step 0.01 | |

### Sessions (server time)

| Day | Quote | Trade |
|-----|-------|-------|
| SUN | 00:00–00:00 | 00:05–02:00, 03:00–00:00 |
| MON–FRI | 00:00–00:00 | 00:05–00:00 |
| SAT | 00:00–00:00 | 01:00–00:00 |

**Quote vs trade differ:** probe showed **live ticks** (`SYMBOL_TIME` advancing, `CopyTicks` at 03:04 server) while Quote session rows show `Q[00:00-00:00]` on several days — treat **Trade** sessions as authoritative for “can we stream/fill now”. Sunday trade window includes a **02:00–03:00 server gap**.

**BRT hint (Sun long window):** server Sun 03:00 ≈ **Sat 22:00 BRT** (start of post-gap session).

### Depth of market

```
MarketBookAdd(BTCUSD) => FALSE  err=4901  ticks_bookdepth=0
```

### Tick semantics (`CopyTicks`, n=20, live at probe)

| Observation | Result |
|-------------|--------|
| `last` | **0.0** |
| Tick flags | **6** (bid+ask only) |
| Sample spread | bid 59943 / ask 59953 (~$10) |

---

## Restrictions (unsupported broker features)

1. **Trade ticks** — `SYMBOL_LAST=0`, no `TICK_FLAG_LAST` / volume on samples → **`TradeTick` Unsupported** for all OTC calc modes in `TICKMILL_DEMO_PROFILE`.

2. **Order book / DOM** — `ticks_bookdepth=0`, `MarketBookAdd` err **4901** → adapter **Unsupported**.

3. **Exchange-style semantics** — dealer bid/ask quotes only; do not infer L2 book or last-trade stream.

---

## Design decisions enforced by this profile

1. **`TICKMILL_DEMO_PROFILE`:** `trade_ticks=UNSUPPORTED`; promote only with new probe evidence.

2. **Hedging account:** exec client must close by **position ticket** when multiple legs exist.

3. **Market orders:** **IOC only** (`SYMBOL_FILLING_MODE=2`; `type_filling=1`). FOK and RETURN rejected by broker (`OrderCheck` retcode 10030) and by adapter `validate_filling_mode()` for explicit FOK.

4. **Limit DAY/GTC:** use RETURN filling (`map_filling_type` default); distinct from market FOK TIF.

5. **Live quote path:** MQL5 WS feed → `QuoteTick` only (same bid/ask semantics as `CopyTicks`).

6. **Homologation scheduling:** respect **session tables** above; failures outside session are expected, not adapter bugs.

---

## Related project docs

| Document | Relevance |
|----------|-----------|
| [`docs/venue_profile.md`](../docs/venue_profile.md) | `TICKMILL_DEMO_PROFILE` |
| [`docs/data_capability_matrix.md`](../docs/data_capability_matrix.md) | Data capabilities |
| [`docs/execution_capability_matrix.md`](../docs/execution_capability_matrix.md) | Exec + hedging |
| [`res/proximos testes adaptador.md`](proximos%20testes%20adaptador.md) | Homologation tracker |
| [`MQL5/refactoring/scripts/probe/`](../MQL5/refactoring/scripts/probe/) | Ad-hoc broker probes (off_hours + live OrderCheck) |
| [`homologation/tools/probe_tick_semantics_fast.py`](../homologation/tools/probe_tick_semantics_fast.py) | Python tick probe |

---

## When to update

Re-run `probe_tickmill_market_off_hours.mq5` and (in session) `probe_tickmill_market_live.mq5` when any of these change:

- Account margin mode (netting ↔ hedging), leverage, demo/live
- Symbol sessions or spread behaviour
- `SYMBOL_TICKS_BOOKDEPTH`, `MarketBookAdd`, or tick `last`/flags
- **`SYMBOL_FILLING_MODE` or `OrderCheck` acceptance** (FOK/IOC/RETURN)
- Broker server / entity / terminal build
