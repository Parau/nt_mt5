# Tickmill-Demo — broker capability restrictions

Empirical broker profile for the `nt_mt5` adapter. Documents what Tickmill-Demo exposes through the **native MT5 terminal** (ground truth), independent of RPyC or the Python bridge.

Use this file when configuring `TICKMILL_DEMO_PROFILE`, updating capability matrices, or deciding whether a data feature is broker-limited vs adapter-limited.

---

## Provenance

| Field | Value |
|-------|-------|
| Server | `Tickmill-Demo` |
| Company | Tickmill Ltd |
| Login | XXXXXX |
| Terminal build | 5833 |
| Probe date | 2026-06-28 01:59:59 (terminal time) |
| Method | One-shot MQL5 script in the MT5 terminal |
| Script | [`MQL5/refactoring/scripts/teste_intrumento_infos.mq5`](../MQL5/refactoring/scripts/teste_intrumento_infos.mq5) |

The script dumps `SymbolInfoInteger` / `SymbolInfoDouble` / `SymbolInfoString`, attempts `MarketBookAdd` / `MarketBookGet`, and samples recent ticks via `CopyTicks`. Output is written to the Experts log and optionally to `MQL5/Files/probe_broker_*.txt`.

### How to re-run

1. Compile `teste_intrumento_infos.mq5` in MetaEditor.
2. Attach the script to any chart while logged into the target account.
3. Default inputs probe `USTEC,BTCUSD`; edit `InpSymbols` for other symbols.
4. Compare output with this document and update if the broker profile changes.

Earlier Python/RPyC probes (`homologation/tools/probe_tick_semantics*.py`) reached the same conclusions for tick semantics; this MQL5 run removes any doubt about the bridge layer.

---

## Summary (adapter-facing)

| Capability | USTEC | BTCUSD | Adapter status |
|------------|-------|--------|----------------|
| Quote ticks (bid/ask) | Yes | Yes | **Supported** (WS feed path + legacy RPyC snapshot) |
| Trade ticks (`last` / volume) | No | No | **Unsupported** (`TICKMILL_DEMO_PROFILE`) |
| Depth of market / order book | No | No | **Unsupported** |
| Execution (market, pending, etc.) | Yes | Yes | **Supported** (separate execution matrix) |
| Historical bars | Yes | Yes | **Supported** (RPyC path) |

---

## USTEC (US Tech 100 Index)

**Path:** `CFD-2\USTEC`  
**Calc mode:** `SYMBOL_TRADE_CALC_MODE=3` (CFDINDEX)

### Symbol metadata

| Property | Value | Notes |
|----------|-------|-------|
| `SYMBOL_TICKS_BOOKDEPTH` | **0** | Broker declares no market depth |
| `SYMBOL_LAST` | **0.0** | No last-trade price at symbol level |
| `SYMBOL_SPREAD` | 80 | Floating spread (`SYMBOL_SPREAD_FLOAT=1`); ~0.80 pts at 2 digits |
| `SYMBOL_TRADE_MODE` | FULL (4) | Trading allowed |
| `SYMBOL_FILLING_MODE` | 2 | IOC-capable (bitmask; verify per order type in exec tests) |
| `SYMBOL_ORDER_MODE` | 127 | Broad order-type support |
| Volume | min 0.01, max 250, step 0.01 | |

### Depth of market

```
MarketBookAdd(USTEC) => FALSE  err=4901  ticks_bookdepth=0
```

Error **4901** (`ERR_BOOKS_CANNOT_ADD`): the terminal refuses DOM subscription. This is a **broker/symbol limitation**, not an adapter or RPyC issue.

### Tick semantics (`CopyTicks`, n=20)

| Observation | Result |
|-------------|--------|
| `last` field | Always **0.0** |
| `volume` field | Always **0** |
| Tick flags | **134** on all samples (bid + ask + bit 128) |
| `TICK_FLAG_LAST` (8) | **0** ticks |
| `TICK_FLAG_VOLUME` (16) | **0** ticks |

**Conclusion:** ticks are **bid/ask quote updates only**. Map to Nautilus `QuoteTick`, not `TradeTick`.

Flag **134** = API flags 2 (bid) + 4 (ask) + 128 (spread/wide-quote marker). MT5 UI export flags often differ by subtracting 128 (UI would show **6**).

---

## BTCUSD (Bitcoin CFD)

**Path:** `Cryptos\BTCUSD`  
**Calc mode:** `SYMBOL_TRADE_CALC_MODE=2` (CFD)

### Symbol metadata

| Property | Value | Notes |
|----------|-------|-------|
| `SYMBOL_TICKS_BOOKDEPTH` | **0** | No market depth |
| `SYMBOL_LAST` | **0.0** | No last-trade price |
| `SYMBOL_SPREAD` | 1000 | Floating; ~**$10.00** at 2 digits (e.g. bid 60129 / ask 60139) |
| `SYMBOL_TRADE_MODE` | FULL (4) | Trading allowed |
| `SYMBOL_FILLING_MODE` | 2 | IOC used successfully in exec smoke tests |
| `SYMBOL_ORDER_MODE` | 127 | Broad order-type support |
| Volume | min 0.01, max 30, step 0.01 | Lower max lot than USTEC |

### Depth of market

```
MarketBookAdd(BTCUSD) => FALSE  err=4901  ticks_bookdepth=0
```

Same verdict as USTEC: **DOM not available** on Tickmill-Demo for this symbol.

### Tick semantics (`CopyTicks`, n=20)

| Observation | Result |
|-------------|--------|
| `last` field | Always **0.0** |
| `volume` field | Always **0** |
| Tick flags | **6** on all samples (bid + ask only; no bit 128) |
| `TICK_FLAG_LAST` (8) | **0** ticks |
| `TICK_FLAG_VOLUME` (16) | **0** ticks |

**Conclusion:** same as USTEC — **QuoteTick-only** feed from the broker.

---

## Design decisions enforced by this profile

1. **`TICKMILL_DEMO_PROFILE`** declares `trade_ticks=UNSUPPORTED` for all OTC calc modes (FOREX, CFD, CFDINDEX, etc.). Do not promote `TradeTick` without new broker evidence (`SYMBOL_LAST > 0` and/or `TICK_FLAG_LAST` on live/historical ticks).

2. **Order book** remains **Unsupported** in the adapter. `market_book_*` exists in the MT5 Python wrapper, but Tickmill-Demo returns `ticks_bookdepth=0` and `MarketBookAdd` fails with 4901 for USTEC and BTCUSD.

3. **Live quote path:** use the MQL5 WebSocket feed (`NT5TickFeedService` → `InboundFeedGateway`). The service reads the same bid/ask-only ticks; the adapter should continue mapping to `QuoteTick` only.

4. **Do not infer exchange-style semantics** (last trade, DOM, L2 book) from symbol names or paths. Tickmill OTC CFD symbols behave as **dealer quotes**, not exchange order books.

---

## Related project docs

| Document | Relevance |
|----------|-----------|
| [`docs/venue_profile.md`](../docs/venue_profile.md) | `TICKMILL_DEMO_PROFILE` definition |
| [`docs/data_capability_matrix.md`](../docs/data_capability_matrix.md) | Quote ticks, trade ticks, order book rows |
| [`docs/terminal_access_capability_audit.md`](../docs/terminal_access_capability_audit.md) | Bridge vs adapter capability audit |
| [`homologation/tools/probe_tick_semantics_fast.py`](../homologation/tools/probe_tick_semantics_fast.py) | Python/RPyC tick-semantics probe (consistent results) |

---

## When to update this file

Re-run `teste_intrumento_infos.mq5` and update this document if any of the following change:

- Broker server name or account type (demo → live, different entity)
- Symbol list or broker symbol naming
- Observed `SYMBOL_TICKS_BOOKDEPTH`, `MarketBookAdd` success, or non-zero `last`/volume ticks
- Terminal build with known MT5 API changes affecting tick flags or book APIs
