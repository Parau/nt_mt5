# XPMT5-DEMO — broker profile (XP / B3 capabilities and restrictions)

Empirical profile for the `nt_mt5` adapter. Documents what **XP Investimentos** exposes on **XPMT5-DEMO** through the **native MT5 terminal** (ground truth), independent of RPyC or the Python bridge.

Covers **account capabilities** (hedging, leverage, demo mode) and **symbol capabilities** (ticks, DOM, sessions, execution). Use when planning `XP_B3_PROFILE`, homologation on B3, or deciding broker-limited vs adapter-limited behaviour.

---

## Provenance

| Field | Value |
|-------|-------|
| Server | `XPMT5-DEMO` |
| Company | XP Investimentos CCTVM S/A |
| Login | 56822578 |
| Terminal build | 5833 |
| Probe date | 2026-06-26 19:30:00 (server time) |
| Method | One-shot MQL5 script in the MT5 terminal |
| Script | [`MQL5/refactoring/scripts/teste_intrumento_infos_xp.mq5`](../MQL5/refactoring/scripts/teste_intrumento_infos_xp.mq5) |
| Output file | `MQL5/Files/probe_xp_XPMT5-DEMO_56822578.txt` |
| Symbols probed | `WIN$`, `WDO$`, **`WINQ26`**, **`WDON26`**, `PETR4`, `DI1F27` |

The script dumps **account** `AccountInfo*` / `TerminalInfo*`, per-symbol `SymbolInfo*`, **Quote/Trade sessions** by weekday, `MarketBookAdd`, and a `CopyTicks` sample (n=20).

### How to re-run

1. Compile `teste_intrumento_infos_xp.mq5` in MetaEditor.
2. Attach the script to any chart while logged into the XP account.
3. Recommended inputs: `WIN$,WDO$,WINQ26,WDON26,PETR4,DI1F27` (update contract codes on rollover).
4. Prefer **B3 regular session** (≈ 09:00–18:00 BRT) for live bid/ask, DOM, and tick samples.
5. Compare output with this document and update if the broker profile changes.

### Time zone note

Session hours and `TimeCurrent()` in the probe are **server time**. On XPMT5-DEMO this run aligns with **BRT (UTC−3)**. Probe at **19:30** = after regular cash close; futures evening session may still apply — treat post-close tick anomalies (especially `WINQ26` bid/ask) as **timing-dependent**.

XP session metadata (`Q[00:00-00:00]` on all weekdays) is **not reliable** for scheduling — use the official B3 calendar for homologation windows.

### `trade_calc_mode` integer values (build 5833)

This terminal reports **`32` = EXCH_STOCKS** and **`33` = EXCH_FUTURES**, not the legacy `6` / `7` still listed in `docs/venue_profile.md` and `nautilus_mt5/venue_profile.py`. Any `XP_B3_PROFILE` must use the values observed on the live terminal (aligned with `MetaTrader5.py` constants 32/33).

### Current front-month contracts (confirmed 2026-06-26)

| Continuous (data) | Nominal (execution) | Underlying in description |
|-------------------|---------------------|---------------------------|
| `WIN$` | **WINQ26** | Ibovespa mini, Aug 2026 expiry |
| `WDO$` | **WDON26** | Dollar mini, Jun 2026 expiry |

---

## Account capabilities (login 56822578)

| Property | Value | Adapter implication |
|----------|-------|---------------------|
| `ACCOUNT_MARGIN_MODE` | **2 — RETAIL_HEDGING** | Multiple positions per symbol; **close orders must use `position=<ticket>`** |
| `ACCOUNT_TRADE_MODE` | **0 — DEMO** | Paper account; not live funds |
| `ACCOUNT_TRADE_ALLOWED` | 1 | Trading enabled |
| `ACCOUNT_TRADE_EXPERT` | 1 | EAs / Services allowed |
| `ACCOUNT_LEVERAGE` | **1** | Typical B3 margin-by-contract (not FX-style leverage) |
| `ACCOUNT_LIMIT_ORDERS` | 0 | No explicit cap reported |
| `ACCOUNT_MARGIN_SO_MODE` | 0 | |
| `ACCOUNT_CURRENCY` | **BRL** | All probed symbols settle in BRL |
| `TERMINAL_CONNECTED` | 1 | |
| `TERMINAL_TRADE_ALLOWED` | 1 | |

**Not netting:** hedging account semantics (same pattern as Tickmill-Demo). Do not assume net position merge on close.

---

## Summary (adapter-facing)

| Capability | WIN$ | WDO$ | WINQ26 | WDON26 | PETR4 | DI1F27 | Adapter status (planned) |
|------------|------|------|--------|--------|-------|--------|--------------------------|
| Quote ticks (bid/ask) | **No** | **No** | **Unreliable** (see below) | **Yes** | **Yes** | **Yes** | Profile-dependent |
| Trade ticks (`last` / volume) | **Yes** | **Yes** | **Yes** | **Yes** | **Partial** | **Yes** | **`XP_B3_PROFILE` — not yet implemented** |
| Depth of market | Empty | Empty | Empty | Empty | Empty | Empty | **Unsupported** until live book confirmed |
| Execution | **No** | **No** | **Yes** | **Yes** | **Yes** | **Yes** | `$` = data only; nominals = exec |
| Historical bars / ticks | Assumed | Assumed | Assumed | Assumed | Assumed | Assumed | RPyC path (not XP-validated yet) |
| Filling (market) | FOK+IOC | FOK+IOC | FOK+IOC | FOK+IOC | FOK+IOC | FOK+IOC | `SYMBOL_FILLING_MODE=3` |

**Tick semantics split (critical):** XP B3 has **four distinct shapes**:

1. **Continuous futures** (`WIN$`, `WDO$`) — trade tape only; **no execution**.
2. **Nominal WIN** (`WINQ26`) — tradable; trade ticks OK; **bid/ask suspect off-hours**.
3. **Nominal WDO / DI** (`WDON26`, `DI1F27`) — tradable; quote + trade ticks in `CopyTicks`.
4. **Equities** (`PETR4`) — tradable; quote-dominated stream with occasional last.

**Do not reuse** continuous-series metadata (`tick_size`, `tick_value`, paths) for nominal contracts — values differ (see comparison table below).

---

## Continuous vs nominal metadata (WIN / WDO)

| Property | WIN$ | WINQ26 | WDO$ | WDON26 |
|----------|------|--------|------|--------|
| Path | `BMF\SERIES CONTINUAS\WIN$` | `BMF\WINQ26` | `BMF\SERIES CONTINUAS\WDO$` | `BMF\WDON26` |
| `TRADE_MODE` | DISABLED | **FULL** | DISABLED | **FULL** |
| Expiry | zero (continuous) | **2026-08-12 22:15** | zero | **2026-06-30 22:15** |
| Tick size | 1.0 | **5.0** | 0.001 | **0.5** |
| Tick value (BRL) | 0.20 | **1.00** | 0.01 | **5.00** |
| Parser | data symbol | **exec + parse target** | data symbol | **exec + parse target** |

---

## WIN$ (Ibovespa mini — continuous series)

**Path:** `BMF\SERIES CONTINUAS\WIN$`  
**Description:** IBOVESPA MINI - Por Liquidez (**WINQ26**) - Ajuste Proporcional  
**Calc mode:** `SYMBOL_TRADE_CALC_MODE=33` (EXCH_FUTURES)

### Symbol metadata

| Property | Value | Notes |
|----------|-------|-------|
| `SYMBOL_TRADE_MODE` | **DISABLED (0)** | **Data-only — do not route orders here** |
| `SYMBOL_BID` / `SYMBOL_ASK` | **0.0** | |
| `SYMBOL_LAST` | 176250 (snapshot); ~176290 in `CopyTicks` | |
| Volume | min 1, max 25000, step 1 | |
| Tick size / value | 1.0 / **0.20 BRL** | ≠ WINQ26 |

### Tick semantics (`CopyTicks`, n=20)

| Observation | Result |
|-------------|--------|
| `bid` / `ask` | **0.0** on all 20 |
| `last` / `volume` | **Non-zero** on all 20 |
| Tick flags | **1336** |

**Conclusion:** **`TradeTick` only**. Use for live index stream; route orders to **WINQ26**.

---

## WDO$ (Dollar mini — continuous series)

**Path:** `BMF\SERIES CONTINUAS\WDO$`  
**Description:** DOLAR MINI - Por Liquidez (**WDON26**) - Ajuste Proporcional  
**Calc mode:** `SYMBOL_TRADE_CALC_MODE=33` (EXCH_FUTURES)

### Symbol metadata

| Property | Value | Notes |
|----------|-------|-------|
| `SYMBOL_TRADE_MODE` | **DISABLED (0)** | **Data-only** |
| `SYMBOL_BID` / `SYMBOL_ASK` | **0.0** | |
| Volume | min 1, max 50000, step 1 | |
| Tick size / value | 0.001 / **0.01 BRL** | ≠ WDON26 |

### Tick semantics (`CopyTicks`, n=20)

| Observation | Result |
|-------------|--------|
| `bid` / `ask` | **0.0** |
| `last` / `volume` | **Non-zero** on all 20 (last ~5178.5–5179) |
| Tick flags | **1336** |

**Conclusion:** **`TradeTick` only**. Route orders to **WDON26**.

---

## WINQ26 (Ibovespa mini — nominal, current front month)

**Path:** `BMF\WINQ26`  
**Description:** IBOVESPA MINI  
**Calc mode:** `SYMBOL_TRADE_CALC_MODE=33` (EXCH_FUTURES)

### Symbol metadata

| Property | Value | Notes |
|----------|-------|-------|
| `SYMBOL_TRADE_MODE` | **FULL (4)** | **Tradable** |
| `SYMBOL_EXPIRATION_TIME` | **2026-08-12 22:15:00** | Real contract expiry |
| `SYMBOL_BID` / `SYMBOL_ASK` (snapshot) | **0.0** | |
| `SYMBOL_LAST` | **176250** | |
| `SYMBOL_TIME` | 2026-06-26 19:30 | Symbol active at probe |
| Volume | min 1, max 25000, step 1 | |
| Tick size / value | **5.0 / 1.00 BRL** | Differs from `WIN$` |

### Depth of market

`MarketBookAdd` OK, **0 levels** at snapshot.

### Tick semantics (`CopyTicks`, n=20, probe 19:30 post-close)

| Observation | Result |
|-------------|--------|
| `last` | **176290** on samples with last flag (16/20) |
| `bid` / `ask` | **192490 / 157495** — **invalid spread** vs last ~176290 |
| Flag mix | bid+ask=1, bid_only=1, ask_only=2, last=16, volume=16 |
| Tick flags | **1336** (same family as continuous) |

**Conclusion:**

- **Execution homologation:** use **WINQ26** (not `WIN$`).
- **Trade ticks:** **`TradeTick` supported** (last+volume reliable in sample).
- **Quote ticks:** **do not trust bid/ask off-hours** — re-probe during **09:00–18:00 BRT** before declaring `quote_ticks=SUPPORTED` for nominal WIN. Until then treat as **OBSERVED / conditional**.

---

## WDON26 (Dollar mini — nominal, current front month)

**Path:** `BMF\WDON26`  
**Description:** DOLAR MINI  
**Calc mode:** `SYMBOL_TRADE_CALC_MODE=33` (EXCH_FUTURES)

### Symbol metadata

| Property | Value | Notes |
|----------|-------|-------|
| `SYMBOL_TRADE_MODE` | **FULL (4)** | **Tradable** |
| `SYMBOL_EXPIRATION_TIME` | **2026-06-30 22:15:00** | Rolls soon — update on expiry |
| `SYMBOL_BID` / `SYMBOL_ASK` (snapshot) | **0.0** | Stale snapshot; ticks have live book |
| `SYMBOL_LAST` | 0.0 (snapshot) | Live in `CopyTicks` |
| Volume | min 1, max 50000, step 1 | |
| Tick size / value | **0.5 / 5.00 BRL** | Differs from `WDO$` |

### Depth of market

`MarketBookAdd` OK, **0 levels** at snapshot.

### Tick semantics (`CopyTicks`, n=20)

| Observation | Result |
|-------------|--------|
| `bid` / `ask` | **5178.5 / 5179.0** — coherent with last |
| `last` / `volume` | Non-zero on 14/20 |
| Flag mix | bid+ask=1, bid_only=2, ask_only=3, last=14, volume=14 |
| Sample flags | **1368**, **1336**, **1026**, **1028** |

**Conclusion:** **best first candidate** for XP exec + live data homologation. Both **`QuoteTick`** and **`TradeTick`** are meaningful. Prefer **WDON26** over `WDO$` for any strategy that submits orders.

---

## PETR4 (Petrobras PN — B3 equity)

**Path:** `BOVESPA\A VISTA\PETR4`  
**Description:** PETROBRAS PN N2  
**Calc mode:** `SYMBOL_TRADE_CALC_MODE=32` (EXCH_STOCKS)

### Symbol metadata

| Property | Value | Notes |
|----------|-------|-------|
| `SYMBOL_BID` / `SYMBOL_ASK` / `SYMBOL_LAST` | **37.90 / 38.13 / 38.06** | Live snapshot |
| `SYMBOL_TRADE_MODE` | **FULL (4)** | |
| `SYMBOL_ORDER_GTC_MODE` | **0** | Differs from futures (2) |
| Volume | min **100**, step **100** | B3 standard lot |

### Tick semantics (`CopyTicks`, n=20)

| Observation | Result |
|-------------|--------|
| `bid` / `ask` | Non-zero on all samples |
| `last` / `volume` | 6 / 20 |
| Flag mix | bid+ask=3, bid_only=8, ask_only=3 |

**Conclusion:** **`QuoteTick` primary**; **`TradeTick`** when `TICK_FLAG_LAST` present.

---

## DI1F27 (DI 1-day — nominal interest-rate future)

**Path:** `BMF\DI1F27`  
**Description:** DI DE 1 DIA  
**Calc mode:** `SYMBOL_TRADE_CALC_MODE=33` (EXCH_FUTURES)

### Symbol metadata

| Property | Value | Notes |
|----------|-------|-------|
| `SYMBOL_TRADE_MODE` | **FULL (4)** | Tradable |
| `SYMBOL_EXPIRATION_TIME` | **2026-12-30 21:10:59** | |
| `SYMBOL_LAST` | **14.055** | **Yield rate**, not BRL price |
| Tick size / value | **0.005 / 0.005** | |

### Tick semantics (`CopyTicks`, n=20)

| Observation | Result |
|-------------|--------|
| `bid` / `ask` | **14.055 / 14.060** |
| `last` / `volume` | 8 / 20 |
| Flag mix | bid+ask=1, bid_only=5, ask_only=6 |

**Conclusion:** **`QuoteTick` + `TradeTick`**. Parser must treat price as **interest rate**, not equity/FX notional.

---

## Restrictions and open questions

1. **Continuous vs nominal** — `WIN$` / `WDO$` are **DISABLED**; all execution targets **WINQ26**, **WDON26**, **DI1F27**, etc.

2. **WINQ26 bid/ask off-hours** — `CopyTicks` showed bid=192490 / ask=157495 vs last≈176290 at 19:30. **Do not emit `QuoteTick` from raw bid/ask without validation** (spread check or session gate). Re-probe in regular session.

3. **Quote ticks on continuous futures** — bid/ask always zero → **`quote_ticks=UNSUPPORTED`** for `WIN$` / `WDO$`; **`trade_ticks=OBSERVED`**.

4. **Metadata isolation** — instrument parser must load **per-symbol** `tick_size`, `tick_value`, expiry from nominal contracts; never inherit from `$` continuous symbols.

5. **Order book / DOM** — `ticks_bookdepth=32`, `MarketBookAdd` OK, **0 levels** on all symbols at probe. DOM remains **Unsupported** until in-session probe shows depth.

6. **Session metadata** — useless (`00:00-00:00`); use B3 calendar externally.

7. **XP_B3_PROFILE not yet in code** — ground truth only; `TICKMILL_DEMO_PROFILE` unchanged.

8. **WDON26 rollover** — expiry **2026-06-30**; update symbol after roll.

---

## Design decisions suggested for `XP_B3_PROFILE`

| Symbol class | `calc_mode` | Instrument type (planned) | quote_ticks | trade_ticks | exec |
|--------------|-------------|---------------------------|-------------|-------------|------|
| Continuous (`WIN$`, `WDO$`) | 33 | `FuturesContract` | **UNSUPPORTED** | **OBSERVED** | **No** |
| Nominal WIN (`WINQ26`) | 33 | `FuturesContract` | **ASSUMED** (validate in session) | **OBSERVED** | **Yes** |
| Nominal WDO / others (`WDON26`, `DI1F27`) | 33 | `FuturesContract` | **OBSERVED** | **OBSERVED** | **Yes** |
| Equities (`PETR4`) | 32 | `Equity` | **OBSERVED** | **OBSERVED** | **Yes** |

### Adapter routing rules

```
Data stream (strategies)     Execution (orders)
────────────────────────     ──────────────────
WIN$  → TradeTick            WINQ26
WDO$  → TradeTick            WDON26
PETR4 → QuoteTick (+Trade)   PETR4
DI1F27 → Quote + Trade       DI1F27
```

Additional rules:

1. **Hedging account:** close by **position ticket** (same as Tickmill).
2. **Market orders:** FOK + IOC (`SYMBOL_FILLING_MODE=3`); validate accepted mode on first live exec probe.
3. **WINQ26 quotes:** gate `QuoteTick` emission with sanity check (e.g. reject if `ask - bid` > N × tick_size or vs last).
4. **DI parser:** price field = yield; do not map to BRL `Price` semantics without explicit convention.

---

## Homologation priority (XP)

| Priority | Symbol | Why |
|----------|--------|-----|
| 1 | **WDON26** | Clean bid/ask + last; FULL; best exec+data smoke |
| 2 | **DI1F27** | Nominal futures with expiry; yield semantics test |
| 3 | **PETR4** | Equity parser + lot=100 |
| 4 | **WINQ26** | Exec OK; validate quotes in-session first |
| 5 | **WIN$** / **WDO$** | WS trade-tick stream only (no orders) |

---

## Comparison with Tickmill-Demo

| Aspect | Tickmill-Demo | XPMT5-DEMO (this probe) |
|--------|---------------|-------------------------|
| Market type | OTC FX/CFD | B3 exchange |
| Account currency | USD | BRL |
| Leverage | 30 | 1 |
| Quote ticks | Yes (OTC bid/ask) | Yes (WDON26, PETR4, DI1F27); **No** (`$`); **doubt** (WINQ26 off-hours) |
| Trade ticks | **No** (`last=0`) | **Yes** (all futures); partial (PETR4) |
| Exec symbols | Same as data | **Split:** `$` data-only, nominals for orders |
| DOM | err 4901 | Subscribe OK, book empty |
| `trade_calc_mode` | 0–5 (OTC) | **32**, **33** (exchange) |

---

## Related project docs

| Document | Relevance |
|----------|-----------|
| [`docs/venue_profile.md`](../docs/venue_profile.md) | `XP_B3_PROFILE` (planned; legacy calc_mode 6/7) |
| [`res/tickmill_restrictions.md`](tickmill_restrictions.md) | OTC reference profile |
| [`res/pensando inclusao da XP/primeira analise.md`](pensando%20inclusao%20da%20XP/primeira%20analise.md) | Multi-broker roadmap |
| [`docs/data_capability_matrix.md`](../docs/data_capability_matrix.md) | Update when XP profile is implemented |
| [`docs/execution_capability_matrix.md`](../docs/execution_capability_matrix.md) | Exec homologation on nominal B3 symbols |

---

## When to update

Re-run `teste_intrumento_infos_xp.mq5` when any of these change:

- Account margin mode, demo/live, or server name
- Contract rollover (`WINQ26` → next month, `WDON26` expired 2026-06-30, new `DI1*`)
- `SYMBOL_TRADE_MODE` on continuous vs nominal futures
- Tick semantics — especially **WINQ26 bid/ask during regular session**
- `MarketBookGet` levels during market hours
- Terminal build with known MT5 API changes
- Before XP exec homologation: confirm **WDON26** / **WINQ26** still front month in Market Watch
