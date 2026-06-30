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
| Probe date (off_hours) | **2026-06-29 11:18:34** (server time ≈ BRT) |
| Probe date (live OrderCheck) | **2026-06-29 11:19:06** (server time ≈ BRT) |
| Method | MQL5 scripts in the MT5 terminal (ad-hoc, not deployed) |
| Scripts | [`probe_xp_market_off_hours.mq5`](../MQL5/refactoring/scripts/probe/probe_xp_market_off_hours.mq5), [`probe_xp_market_live.mq5`](../MQL5/refactoring/scripts/probe/probe_xp_market_live.mq5) |
| Output files | `MQL5/Files/probe_xp_off_XPMT5-DEMO_56822578.txt`, `MQL5/Files/probe_xp_live_XPMT5-DEMO_56822578.txt` |
| Symbols probed | `WIN$`, `WDO$`, **`WINQ26`**, **`WDON26`**, `PETR4`, `DI1F27` |

Legacy probe (2026-06-26 19:30): [`teste_intrumento_infos_xp.mq5`](../MQL5/refactoring/scripts/teste_intrumento_infos_xp.mq5) → `probe_xp_XPMT5-DEMO_56822578.txt` (same **declared** symbol fields; no `OrderCheck`; **WINQ26 bid/ask off-hours artifact** — superseded by 2026-06-29 in-session probe).

The off_hours script dumps **account** `AccountInfo*` / `TerminalInfo*`, per-symbol `SymbolInfo*`, **Quote/Trade sessions** by weekday, `MarketBookAdd` / `MarketBookGet`, and a `CopyTicks` sample (n=20). The live script adds `SymbolInfoTick` and **`OrderCheck`** filling probes (no `OrderSend`).

### How to re-run

1. Copy `MQL5/refactoring/scripts/probe/` to `Terminal\<hash>\MQL5\Scripts\probe\`.
2. Compile `probe_xp_market_off_hours.mq5` and/or `probe_xp_market_live.mq5` in MetaEditor.
3. Attach to any chart while logged into the XP account.
4. Default inputs probe `WIN$,WDO$,WINQ26,WDON26,PETR4,DI1F27` (update contract codes on rollover).
5. Run **`market_live`** during **B3 regular session** (≈ 09:00–18:00 BRT) for live bid/ask, `OrderCheck` filling ground truth, and tick samples.
6. Compare output with this document and update if the broker profile changes.

### Time zone note

Session hours and `TimeCurrent()` in the probe are **server time**. On XPMT5-DEMO this run aligns with **BRT (UTC−3)**.

XP session metadata (`Q[00:00-00:00]` / `T[00:00-00:00]` on weekdays) is **not reliable** for scheduling — the probe scripts infer **Trade session OPEN now** from live quotes and `SYMBOL_TIME`. Use the official B3 calendar for homologation windows.

**WINQ26 off-hours correction:** the 2026-06-26 19:30 probe showed bid=192490 / ask=157495 vs last≈176290 — an **off-hours artifact**. The 2026-06-29 11:18–11:19 in-session probe shows coherent bid/ask (~175710/175715, spread 5).

### `trade_calc_mode` integer values (build 5833)

This terminal reports **`32` = EXCH_STOCKS** and **`33` = EXCH_FUTURES**, not the legacy `6` / `7` still listed in `docs/venue_profile.md` and `nautilus_mt5/venue_profile.py`. Any `XP_B3_PROFILE` must use the values observed on the live terminal (aligned with `MetaTrader5.py` constants 32/33).

### Current front-month contracts (confirmed 2026-06-29)

| Continuous (data) | Nominal (execution) | Underlying in description |
|-------------------|---------------------|---------------------------|
| `WIN$` | **WINQ26** | Ibovespa mini, Aug 2026 expiry |
| `WDO$` | **WDON26** | Dollar mini, **Jun 2026 expiry (rolls 2026-06-30)** |

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
| Quote ticks (bid/ask) | **No** | **No** | **Yes** (in session) | **Yes** | **Yes** | **Yes** | Profile-dependent |
| Trade ticks (`last` / volume) | **Yes** | **Yes** | **Yes** | **Yes** | **Partial** | **Yes** | **`XP_B3_PROFILE` — not yet implemented** |
| Depth of market | Empty | Empty | Empty | Empty | Empty | Empty | **Unsupported** until live book confirmed |
| Execution | **No** | **No** | **Yes** | **Yes** | **Yes** | **Yes** | `$` = data only; nominals = exec |
| Historical bars / ticks | Assumed | Assumed | Assumed | Assumed | Assumed | Assumed | RPyC path (not XP-validated yet) |
| Filling (market) | FOK+IOC | FOK+IOC | FOK+IOC | FOK+IOC | FOK+IOC | FOK+IOC | `SYMBOL_FILLING_MODE=3`; FOK/IOC **OrderCheck OK** |

**Tick semantics split (critical):** XP B3 has **four distinct shapes**:

1. **Continuous futures** (`WIN$`, `WDO$`) — trade tape only; **no execution**; **no bid/ask**.
2. **Nominal WIN** (`WINQ26`) — tradable; **quote + trade ticks** in regular session.
3. **Nominal WDO / DI** (`WDON26`, `DI1F27`) — tradable; quote + trade ticks in `CopyTicks`.
4. **Equities** (`PETR4`) — tradable; quote-dominated stream with occasional last.

**Do not reuse** continuous-series metadata (`tick_size`, `tick_value`, paths) for nominal contracts — values differ (see comparison table below).

### Filling — declared vs observed (2026-06-29 live probe)

| Symbol | Declared (`SymbolInfo`) | Observed (`OrderCheck` market deal) |
|--------|-------------------------|-------------------------------------|
| WINQ26 | bitmask **3** → FOK + IOC | FOK **OK**; IOC **OK**; RETURN **OK** |
| WDON26 | bitmask **3** → FOK + IOC | FOK **OK**; IOC **OK**; RETURN **OK** |
| PETR4 | bitmask **3** → FOK + IOC | FOK **OK**; IOC **OK**; RETURN **OK** |
| DI1F27 | bitmask **3** → FOK + IOC | FOK **OK**; IOC **OK**; RETURN **OK** |

**Conclusion:** All four tradable symbols are **identical** for filling at `OrderCheck` time. Declared bitmask is **FOK + IOC** (`SYMBOL_FILLING_MODE=3`). **RETURN also passes `OrderCheck`** despite not being in the declared bitmask — **validate with `OrderSend` before claiming RETURN support** for market orders.

**Contrast with Tickmill-Demo:** Tickmill declares bitmask **2** (IOC only) and rejects FOK/RETURN at `OrderCheck` (`10030 INVALID_FILL`). XP accepts FOK and IOC per declared bitmask; RETURN acceptance is an open question until live `OrderSend`.

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
| `SYMBOL_LAST` | 175715 (snapshot); ~175715 in `CopyTicks` | |
| Volume | min 1, max 25000, step 1 | |
| Tick size / value | 1.0 / **0.20 BRL** | ≠ WINQ26 |

### Depth of market

`MarketBookAdd` OK (`ticks_bookdepth=32`), **0 levels** at snapshot.

### Tick semantics (`CopyTicks`, n=20, probe 2026-06-29)

| Observation | Result |
|-------------|--------|
| `bid` / `ask` | **0.0** on all 20 |
| `last` / `volume` | **Non-zero** on all 20 |
| Tick flags | **1080** |

**Live probe note:** `probe_xp_market_live` **SKIPs** `WIN$` when trade session is closed (DISABLED, no bid/ask) — correct behaviour.

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

### Depth of market

`MarketBookAdd` OK (`ticks_bookdepth=32`), **0 levels** at snapshot.

### Tick semantics (`CopyTicks`, n=20, probe 2026-06-29)

| Observation | Result |
|-------------|--------|
| `bid` / `ask` | **0.0** |
| `last` / `volume` | **Non-zero** on all 20 (last ~5185.0–5185.5) |
| Tick flags | **1080** |

**Live probe note:** `probe_xp_market_live` **SKIPs** `WDO$` when trade session is closed — correct behaviour.

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
| `SYMBOL_BID` / `SYMBOL_ASK` (snapshot) | **175750 / 175755** | Spread 5 (1 tick) |
| `SYMBOL_LAST` | **175755** | |
| `SYMBOL_TIME` | 2026-06-29 11:19 | Live at probe |
| Volume | min 1, max 25000, step 1 | |
| Tick size / value | **5.0 / 1.00 BRL** | Differs from `WIN$` |

### Depth of market

`MarketBookAdd` OK (`ticks_bookdepth=32`), **0 levels** at snapshot.

### Tick semantics (`CopyTicks`, n=20, probe 2026-06-29 in-session)

| Observation | Result |
|-------------|--------|
| `last` | **175745–175755** on all samples |
| `bid` / `ask` | **175745 / 175750** — coherent with last (~175750) |
| Flag mix | bid_only=1, ask_only=1, last=18, volume=18 |
| Tick flags | **1080**, **1112** |

**Off-hours artifact (superseded):** 2026-06-26 19:30 probe showed bid=192490 / ask=157495 vs last≈176290 — **invalid spread, post-close artifact**. Do not use for adapter decisions.

**Conclusion:**

- **Execution homologation:** use **WINQ26** (not `WIN$`).
- **Quote ticks:** **`OBSERVED`** in regular B3 session — bid/ask valid, spread coherent.
- **Trade ticks:** **`TradeTick` supported** (last+volume reliable in sample).

---

## WDON26 (Dollar mini — nominal, current front month)

**Path:** `BMF\WDON26`  
**Description:** DOLAR MINI  
**Calc mode:** `SYMBOL_TRADE_CALC_MODE=33` (EXCH_FUTURES)

### Symbol metadata

| Property | Value | Notes |
|----------|-------|-------|
| `SYMBOL_TRADE_MODE` | **FULL (4)** | **Tradable** |
| `SYMBOL_EXPIRATION_TIME` | **2026-06-30 22:15:00** | **Expires today — roll to next month after expiry** |
| `SYMBOL_BID` / `SYMBOL_ASK` (snapshot) | **5183.5 / 5184.0** | Spread 0.5 (1 tick) |
| `SYMBOL_LAST` | **5184.0** | Live in `CopyTicks` |
| Volume | min 1, max 50000, step 1 | |
| Tick size / value | **0.5 / 5.00 BRL** | Differs from `WDO$` |

### Depth of market

`MarketBookAdd` OK (`ticks_bookdepth=32`), **0 levels** at snapshot.

### Tick semantics (`CopyTicks`, n=20, probe 2026-06-29 in-session)

| Observation | Result |
|-------------|--------|
| `bid` / `ask` | **5183.5 / 5184.0** — coherent with last |
| `last` / `volume` | Non-zero on all 20 |
| Flag mix | last=20, volume=20 |
| Tick flags | **1080**, **1112** |

**Conclusion:** **best first candidate** for XP exec + live data homologation. Both **`QuoteTick`** and **`TradeTick`** are meaningful. Prefer **WDON26** over `WDO$` for any strategy that submits orders. **Rollover imminent** — update symbol after 2026-06-30 expiry.

---

## PETR4 (Petrobras PN — B3 equity)

**Path:** `BOVESPA\A VISTA\PETR4`  
**Description:** PETROBRAS PN N2  
**Calc mode:** `SYMBOL_TRADE_CALC_MODE=32` (EXCH_STOCKS)

### Symbol metadata

| Property | Value | Notes |
|----------|-------|-------|
| `SYMBOL_BID` / `SYMBOL_ASK` / `SYMBOL_LAST` | **38.06 / 38.07 / 38.05** | Live snapshot (2026-06-29) |
| `SYMBOL_TRADE_MODE` | **FULL (4)** | |
| `SYMBOL_ORDER_GTC_MODE` | **0** | Differs from futures (2) |
| Volume | min **100**, step **100** | B3 standard lot |

### Depth of market

`MarketBookAdd` OK (`ticks_bookdepth=32`), **0 levels** at snapshot.

### Tick semantics (`CopyTicks`, n=20, probe 2026-06-29 in-session)

| Observation | Result |
|-------------|--------|
| `bid` / `ask` | Non-zero on all samples |
| `last` / `volume` | 13 / 20 |
| Flag mix | bid_only=3, ask_only=4, last=13, volume=13 |
| Tick flags | **1026**, **1028**, **1080** |

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
| `SYMBOL_LAST` | **14.040** | **Yield rate**, not BRL price |
| Tick size / value | **0.005 / 0.005** | |

### Depth of market

`MarketBookAdd` OK (`ticks_bookdepth=32`), **0 levels** at snapshot.

### Tick semantics (`CopyTicks`, n=20, probe 2026-06-29 in-session)

| Observation | Result |
|-------------|--------|
| `bid` / `ask` | **14.035 / 14.040** |
| `last` / `volume` | 11 / 20 |
| Flag mix | bid_only=4, ask_only=5, last=11, volume=11 |
| Tick flags | **1026**, **1028**, **1080**, **1144** |

**Conclusion:** **`QuoteTick` + `TradeTick`**. Parser must treat price as **interest rate**, not equity/FX notional.

---

## Restrictions and open questions

1. **Continuous vs nominal** — `WIN$` / `WDO$` are **DISABLED**; all execution targets **WINQ26**, **WDON26**, **DI1F27**, etc.

2. **Quote ticks on continuous futures** — bid/ask always zero → **`quote_ticks=UNSUPPORTED`** for `WIN$` / `WDO$`; **`trade_ticks=OBSERVED`**.

3. **Metadata isolation** — instrument parser must load **per-symbol** `tick_size`, `tick_value`, expiry from nominal contracts; never inherit from `$` continuous symbols.

4. **Order book / DOM** — `ticks_bookdepth=32`, `MarketBookAdd` OK on all symbols, **0 levels** at probe. DOM remains **Unsupported** until in-session probe shows depth.

5. **Session metadata** — `Q[00:00-00:00]` / `T[00:00-00:00]` placeholders on all weekdays; probe infers **Trade session OPEN now** from live quotes. Use B3 calendar externally.

6. **Market filling RETURN** — passes `OrderCheck` on all tradables despite bitmask=3 (FOK+IOC only). Confirm with `OrderSend` before adapter claims RETURN for market orders.

7. **XP_B3_PROFILE not yet in code** — ground truth only; `TICKMILL_DEMO_PROFILE` unchanged.

8. **WDON26 rollover** — expiry **2026-06-30 22:15**; update symbol after roll.

---

## Design decisions suggested for `XP_B3_PROFILE`

| Symbol class | `calc_mode` | Instrument type (planned) | quote_ticks | trade_ticks | exec |
|--------------|-------------|---------------------------|-------------|-------------|------|
| Continuous (`WIN$`, `WDO$`) | 33 | `FuturesContract` | **UNSUPPORTED** | **OBSERVED** | **No** |
| Nominal WIN (`WINQ26`) | 33 | `FuturesContract` | **OBSERVED** | **OBSERVED** | **Yes** |
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
2. **Market orders:** FOK + IOC per declared bitmask (`SYMBOL_FILLING_MODE=3`); `OrderCheck` confirms both. RETURN accepted at `OrderCheck` — validate on first live `OrderSend`.
3. **DI parser:** price field = yield; do not map to BRL `Price` semantics without explicit convention.

---

## Homologation priority (XP)

| Priority | Symbol | Why |
|----------|--------|-----|
| 1 | **WDON26** | Clean bid/ask + last; FULL; best exec+data smoke (**roll after 2026-06-30**) |
| 2 | **WINQ26** | Exec + quotes validated in-session |
| 3 | **DI1F27** | Nominal futures with expiry; yield semantics test |
| 4 | **PETR4** | Equity parser + lot=100 |
| 5 | **WIN$** / **WDO$** | WS trade-tick stream only (no orders) |

---

## Comparison with Tickmill-Demo

| Aspect | Tickmill-Demo | XPMT5-DEMO (this probe) |
|--------|---------------|-------------------------|
| Market type | OTC FX/CFD | B3 exchange |
| Account currency | USD | BRL |
| Leverage | 30 | 1 |
| Quote ticks | Yes (OTC bid/ask) | Yes (all tradables in session); **No** (`$`) |
| Trade ticks | **No** (`last=0`) | **Yes** (all futures); partial (PETR4) |
| Exec symbols | Same as data | **Split:** `$` data-only, nominals for orders |
| DOM | err 4901 | Subscribe OK (`bookdepth=32`), book empty |
| Filling (market) | **IOC only** (bitmask 2) | **FOK + IOC** (bitmask 3); RETURN `OrderCheck` OK (unconfirmed) |
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
| [`MQL5/refactoring/scripts/probe/`](../MQL5/refactoring/scripts/probe/) | Ad-hoc broker probes (off_hours + live OrderCheck) |

---

## When to update

Re-run `probe_xp_market_off_hours.mq5` and (in session) `probe_xp_market_live.mq5` when any of these change:

- Account margin mode, demo/live, or server name
- Contract rollover (`WINQ26` → next month, `WDON26` expired 2026-06-30, new `DI1*`)
- `SYMBOL_TRADE_MODE` on continuous vs nominal futures
- Tick semantics or bid/ask coherence in-session
- `MarketBookGet` levels during market hours
- **`SYMBOL_FILLING_MODE` or `OrderCheck` / `OrderSend` acceptance** (FOK/IOC/RETURN)
- Terminal build with known MT5 API changes
- Before XP exec homologation: confirm **WDON26** / **WINQ26** still front month in Market Watch
