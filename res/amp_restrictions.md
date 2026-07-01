# AMPGlobalUSA-Demo — broker profile (AMP Global / CME futures)

Empirical profile for the `nt_mt5` adapter. Documents what **AMP Global Clearing** exposes on **AMPGlobalUSA-Demo** through the **native MT5 terminal** (ground truth), independent of RPyC or the Python bridge.

Covers **account capabilities** (netting, leverage, demo mode) and **symbol capabilities** (ticks, DOM, sessions, execution) for **CME-listed US futures**. Use when planning `AMP_US_PROFILE`, homologation on AMP Docker (`MT5_PORT=18814`), or deciding broker-limited vs adapter-limited behaviour.

---

## Provenance

| Field | Value |
|-------|-------|
| Server | `AMPGlobalUSA-Demo` |
| Company | AMP Global Clearing LLC |
| Login | 1588658 |
| Terminal build | 5833 |
| Probe date (off_hours) | **2026-07-01 12:50:52** (server time) |
| Probe date (live OrderCheck) | **2026-07-01 12:50:40** (server time) |
| Method | MQL5 scripts in the MT5 terminal (ad-hoc, not deployed) |
| Scripts | [`probe_amp_market_off_hours.mq5`](../MQL5/refactoring/scripts/probe/probe_amp_market_off_hours.mq5), [`probe_amp_market_live.mq5`](../MQL5/refactoring/scripts/probe/probe_amp_market_live.mq5) |
| Output files | `MQL5/Files/probe_amp_off_AMPGlobalUSA-Demo_1588658.txt`, `MQL5/Files/probe_amp_live_AMPGlobalUSA-Demo_1588658.txt` |
| Symbols probed | **EPU26**, **MESU26**, **ENQU26**, **MNQU26** |

The off_hours script dumps **account** `AccountInfo*` / `TerminalInfo*`, per-symbol `SymbolInfo*`, **Quote/Trade sessions** by weekday, `MarketBookAdd` / `MarketBookGet`, and a `CopyTicks` sample (n=20). The live script adds `SymbolInfoTick` and **`OrderCheck`** filling probes (no `OrderSend`).

### How to re-run

1. Copy `MQL5/refactoring/scripts/probe/` to `Terminal\<hash>\MQL5\Scripts\probe\` (AMP Docker: VNC `127.0.0.1:5903`).
2. Compile `probe_amp_market_off_hours.mq5` and/or `probe_amp_market_live.mq5` in MetaEditor.
3. Run from Navigator → Scripts while logged into **AMPGlobalUSA-Demo**.
4. Default inputs probe `EPU26,MESU26,ENQU26,MNQU26` (update contract suffix on rollover, e.g. `U26` → next expiry).
5. Run **`market_live`** during **CME trade session** for live bid/ask, `OrderCheck` filling ground truth, and tick samples.
6. Compare output with this document and update if the broker profile changes.

### Time zone note

Session hours and `TimeCurrent()` in the probe are **server time** (not UTC/BRT). CME Globex-style windows appear as:

- **SUN** 22:00–00:00 (open from Sunday evening)
- **MON–THU** 00:00–21:00 and 22:00–00:00 (daily maintenance break ~21:00–22:00 server)
- **FRI** 00:00–17:00 (weekend close)
- **SAT** closed

Map to US/Eastern or Chicago exchange calendar externally for homologation scheduling. Do not assume server time = exchange local without cross-check.

### Docker / homolog

| Item | Value |
|------|-------|
| Compose profile | `amp` |
| RPyC (host) | `127.0.0.1:18814` (`MT5_PORT=18814`) |
| WS feed (host) | `8767` (`WS_PORT=8767`) |
| Default feed symbol (compose) | `ENQU26` |

---

## Account capabilities (login 1588658)

| Property | Value | Adapter implication |
|----------|-------|---------------------|
| `ACCOUNT_MARGIN_MODE` | **0 — RETAIL_NETTING** | **Netting** — not hedging; position merge on same symbol; **differs from Tickmill/XP** |
| `ACCOUNT_TRADE_MODE` | **0 — DEMO** | Paper account |
| `ACCOUNT_TRADE_ALLOWED` | 1 | Trading enabled |
| `ACCOUNT_TRADE_EXPERT` | 1 | EAs / Services allowed |
| `ACCOUNT_LEVERAGE` | **1** | Futures margin-by-contract style |
| `ACCOUNT_LIMIT_ORDERS` | 0 | No explicit cap reported |
| `ACCOUNT_MARGIN_SO_MODE` | 0 | |
| `ACCOUNT_CURRENCY` | **USD** | |
| `TERMINAL_CONNECTED` | 1 | |
| `TERMINAL_TRADE_ALLOWED` | 1 | |

**Critical:** AMP demo is **netting**, not **RETAIL_HEDGING**. Close-order and multi-leg homologation patterns validated on Tickmill/XP **do not transfer** without re-test.

---

## Summary (adapter-facing)

| Capability | EPU26 | MESU26 | ENQU26 | MNQU26 | Adapter status |
|------------|-------|--------|--------|--------|----------------|
| Quote ticks (bid/ask) | Yes (in session) | Yes | Yes | Yes | **CERTIFIED** — homolog `run_amp_open_market_feed.py` (2026-07-01) |
| Trade ticks (`last` / volume) | Yes | Yes | Yes | Yes | **CERTIFIED** — homolog `run_amp_trade_ticks_homologation.py` |
| Depth of market | Empty book | Empty | Empty | Empty | **Unsupported** (`bookdepth=32`, 0 levels) |
| Execution | Yes (in session) | Yes | Yes | Yes | **CERTIFIED** — `run_amp_exec_homologation.py` 18/18 (2026-07-01, netting) |
| Historical bars (M1/M5) | Yes | Yes | Yes | Yes | **CERTIFIED** — `run_amp_closed_market.py` D04a/b (2026-07-01) |
| Live bars M1 (WS) | Yes (in session) | Yes | Yes | Yes | **CERTIFIED** — `run_amp_open_market_feed.py` D03 (2026-07-01) |
| Filling (market) | FOK+IOC | FOK+IOC | FOK+IOC | FOK+IOC | `SYMBOL_FILLING_MODE=3`; FOK/IOC/RETURN **OrderCheck OK** |

All four symbols share the **same** account-level filling behaviour at `OrderCheck` time in this probe.

### Filling — declared vs observed (2026-07-01 live probe)

| Symbol | Declared (`SymbolInfo`) | Observed (`OrderCheck` market deal) |
|--------|-------------------------|-------------------------------------|
| EPU26 | bitmask **3** → FOK + IOC | FOK **OK**; IOC **OK**; RETURN **OK** |
| MESU26 | bitmask **3** → FOK + IOC | FOK **OK**; IOC **OK**; RETURN **OK** |
| ENQU26 | bitmask **3** → FOK + IOC | FOK **OK**; IOC **OK**; RETURN **OK** |
| MNQU26 | bitmask **3** → FOK + IOC | FOK **OK**; IOC **OK**; RETURN **OK** |

**Conclusion:** Declared bitmask is **FOK + IOC** (`SYMBOL_FILLING_MODE=3`). **RETURN also passes `OrderCheck`** on all four symbols despite not being in the declared bitmask — same pattern as **XP/B3**. **Validate with `OrderSend`** before claiming RETURN for market orders.

**Contrast with Tickmill-Demo:** Tickmill declares bitmask **2** (IOC only) and rejects FOK/RETURN at `OrderCheck` (`10030 INVALID_FILL`). AMP aligns with **XP** on filling acceptance at probe time, not Tickmill.

---

## Symbol comparison (nominal CME futures, Sep 2026)

| Property | EPU26 | MESU26 | ENQU26 | MNQU26 |
|----------|-------|--------|--------|--------|
| Description | E-Mini S&P 500 Sep 2026 | Micro E-mini S&P Sep 2026 | E-mini NASDAQ-100 Sep 2026 | Micro E-mini Nasdaq Sep 2026 |
| Path | `Exchange-Futures\CME\EPU26` | `...\MESU26` | `...\ENQU26` | `...\MNQU26` |
| Basis | EP | MES | ENQ | MNQ |
| `TRADE_CALC_MODE` | 33 (EXCH_FUTURES) | 33 | 33 | 33 |
| `TRADE_MODE` | FULL | FULL | FULL | FULL |
| Tick size | 0.25 | 0.25 | 0.25 | 0.25 |
| Tick value (USD) | **12.50** | **1.25** | **5.00** | **0.50** |
| Volume min / step | 1 / 1 | 1 / 1 | 1 / 1 | 1 / 1 |
| Spread (points, snapshot) | 25 | 25 | 175 | 50 |
| `ORDER_GTC_MODE` | 0 | 0 | 0 | 0 |

**Parser rule:** load **per-symbol** `tick_size`, `tick_value`, and contract metadata — do not assume micro/mini share economics beyond tick size.

---

## EPU26 (E-Mini S&P 500 — September 2026)

**Path:** `Exchange-Futures\CME\EPU26`

### Sessions (server time, shared pattern)

| Day | Quote | Trade |
|-----|-------|-------|
| SUN | 22:00–00:00 | 22:00–00:00 |
| MON–THU | 00:00–21:00, 22:00–00:00 | same |
| FRI | 00:00–17:00 | 00:00–17:00 |
| SAT | closed | closed |

`Trade session OPEN now: YES` at probe (2026-07-01 12:50).

### Depth of market

```
MarketBookAdd(EPU26) => TRUE  ticks_bookdepth=32
MarketBookGet(EPU26) => TRUE  levels=0
DOM verdict: subscription OK but book EMPTY
```

### Tick semantics (`CopyTicks`, n=20, in-session)

| Observation | Result |
|-------------|--------|
| `bid` / `ask` | Non-zero; live snapshot ~7529.50 / 7529.75 |
| `last` / `volume` | Present on samples |
| Flag mix (live) | bid+ask=3, last=17, volume=17 (of 20) |

**Conclusion:** **`QuoteTick` + `TradeTick`** in session. Primary homolog candidate for **full-size** S&P exposure.

---

## MESU26 (Micro E-mini S&P 500 — September 2026)

**Path:** `Exchange-Futures\CME\MESU26`

Same session table and DOM verdict as EPU26.

### Tick semantics (`CopyTicks`, n=20, in-session)

| Observation | Result |
|-------------|--------|
| `bid` / `ask` | Non-zero; tracks EPU26 index level (~7529.5) |
| `last` / `volume` | Present |
| Flag mix (live) | bid+ask=1, ask_only=4, last=15, volume=15 |

**Conclusion:** **`QuoteTick` + `TradeTick`**. Lower notional via `tick_value=1.25` vs EPU26 `12.50` — preferred for **smoke tests** and margin-friendly homolog.

---

## ENQU26 (E-mini NASDAQ-100 — September 2026)

**Path:** `Exchange-Futures\CME\ENQU26`

Same session table and DOM verdict.

### Tick semantics (`CopyTicks`, n=20, in-session)

| Observation | Result |
|-------------|--------|
| `bid` / `ask` | ~30263.75 / 30265.25 (live snapshot) |
| `last` / `volume` | Present |
| Flag mix (live) | bid+ask=6, bid_only=9, ask_only=1, last=4, volume=4 |

Wider declared spread (175 pts) vs ES complex — normal for NQ vs EP at probe time.

**Conclusion:** **`QuoteTick` + `TradeTick`**. Default symbol in MT5-Docker AMP compose (`NT5_WS_SYMBOLS=ENQU26`).

---

## MNQU26 (Micro E-mini Nasdaq-100 — September 2026)

**Path:** `Exchange-Futures\CME\MNQU26`

Same session table and DOM verdict.

### Tick semantics (`CopyTicks`, n=20, in-session)

| Observation | Result |
|-------------|--------|
| `bid` / `ask` | ~30264.25 / 30264.75 |
| `last` / `volume` | Present |
| Flag mix (live) | bid+ask=8, bid_only=1, ask_only=1, last=10, volume=10 |

**Conclusion:** **`QuoteTick` + `TradeTick`**. Micro NQ counterpart to MESU26 (`tick_value=0.50`).

---

## Restrictions and open questions

1. **Netting account** — `ACCOUNT_MARGIN_MODE=0`; do not apply Tickmill/XP hedging close-by-ticket assumptions without live validation.

2. **Order book / DOM** — `ticks_bookdepth=32`, `MarketBookAdd` OK, **0 levels** on all symbols → adapter **DOM Unsupported** (same empty-book pattern as XP).

3. **Market filling RETURN** — passes `OrderCheck` on all symbols despite bitmask=3 (FOK+IOC only). Confirm with **`OrderSend`** before adapter claims RETURN for market path.

4. **`AMP_US_PROFILE` in code** — `nautilus_mt5.venue_profile.AMP_US_PROFILE`; homolog runners `homologation/run_amp_*.py` (data, exec, closed-market bars).

5. **Contract rollover** — symbols use **Sep 2026** suffix (`U26`); update probes and compose defaults on roll.

6. **`SYMBOL_ORDER_GTC_MODE=0`** on all probed futures — GTC/limit behaviour validated on exec homolog (2026-07-01).

7. **Integer contract volume** — `volume_min=1`, `step=1` (whole contracts); adapter quantity mapping must respect futures lot semantics.

---

## `AMP_US_PROFILE` (implemented)

| Symbol class | `calc_mode` | Instrument type | quote_ticks | trade_ticks | bars |
|--------------|-------------|-----------------|-------------|-------------|------|
| CME nominal (`EPU26`, `MESU26`, `ENQU26`, `MNQU26`) | 33 | `FuturesContract` | **CERTIFIED** | **CERTIFIED** | **CERTIFIED** |

### Adapter routing rules (initial)

```
Data stream                 Execution
───────────                 ─────────
EPU26 / MESU26 / ENQU26 / MNQU26  →  same symbol (no continuous/$ split like XP)
```

Additional rules:

1. **Netting account:** close semantics differ from hedging brokers — test flat vs partial close explicitly.
2. **Market orders:** FOK + IOC per declared bitmask; `OrderCheck` confirms both; RETURN accepted at `OrderCheck` — validate on first live `OrderSend`.
3. **Live feed:** WS `NT5TickFeedService` on Docker AMP port **8767**; homolog `MT5_PORT=18814`.

---

## Homologation priority (AMP)

| Priority | Symbol | Why | Status (2026-07-01) |
|----------|--------|-----|---------------------|
| 1 | **MESU26** | Micro S&P — lower tick value; same filling/tick shape as EPU26 | **PASS** data + exec + bars |
| 2 | **MNQU26** | Micro NQ — pairs with MES for index diversity | **PASS** D02/D21/D30/D31 |
| 3 | **ENQU26** | Full-size NQ; default Docker WS symbol | **PASS** D02/D21/D30/D31 |
| 4 | **EPU26** | Full-size ES; highest tick value | **PASS** multi-symbol D07 + hist bars |

Run probes and homolog **only during CME trade session** (`InpSkipClosed=true` on live scripts).

---

## Comparison with other probed brokers

| Aspect | Tickmill-Demo | XPMT5-DEMO | AMPGlobalUSA-Demo (this probe) |
|--------|---------------|------------|--------------------------------|
| Market type | OTC FX/CFD | B3 exchange | **US CME futures** |
| Account mode | **Hedging** | **Hedging** | **Netting** |
| Currency | USD | BRL | USD |
| Leverage | 30 | 1 | 1 |
| Quote ticks | Yes (OTC) | Yes (nominals); No (`$`) | **Yes** (all four) |
| Trade ticks | **No** (`last=0`) | Yes (futures) | **Yes** (all four) |
| Exec vs data symbol | Same | Split (`$` vs nominal) | **Same symbol** |
| DOM | err 4901 | Subscribe OK, book empty | Subscribe OK, book empty |
| Filling (market) | **IOC only** (bitmask 2) | FOK+IOC (3); RETURN `OrderCheck` OK | **FOK+IOC (3)**; RETURN `OrderCheck` OK |
| `trade_calc_mode` | 0–5 (OTC) | 32, 33 | **33** (EXCH_FUTURES) |

---

## Related project docs

| Document | Relevance |
|----------|-----------|
| [`docs/venue_profile.md`](../docs/venue_profile.md) | `AMP_US_PROFILE` |
| [`res/tickmill_restrictions.md`](tickmill_restrictions.md) | OTC / IOC-only reference |
| [`res/xp_b3_restrictions.md`](xp_b3_restrictions.md) | Exchange / FOK+IOC reference |
| [`docs/data_capability_matrix.md`](../docs/data_capability_matrix.md) | AMP live coverage (bars, ticks, quotes) |
| [`docs/execution_capability_matrix.md`](../docs/execution_capability_matrix.md) | Exec homologation on AMP symbols |
| [`MQL5/refactoring/scripts/probe/`](../MQL5/refactoring/scripts/probe/) | Ad-hoc broker probes |
| [`MT5-Docker`](../MT5-Docker/docker-compose.yml) | `mt5-amp` service (VNC 5903, RPyC 18814, WS 8767) |

---

## When to update

Re-run `probe_amp_market_off_hours.mq5` and (in session) `probe_amp_market_live.mq5` when any of these change:

- Account margin mode (netting ↔ hedging), demo/live, or server name
- Contract rollover (`*U26` → next expiry month code)
- `SYMBOL_TRADE_MODE` or session tables
- Tick semantics or bid/ask coherence in-session
- `MarketBookGet` levels during market hours
- **`SYMBOL_FILLING_MODE` or `OrderCheck` / `OrderSend` acceptance** (FOK/IOC/RETURN)
- Terminal build with known MT5 API changes
- Before AMP exec homologation: confirm front-month symbols in Market Watch
