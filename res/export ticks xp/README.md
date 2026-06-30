# XP tick export — flag validation (2026-06-30)

MT5 terminal CSV export vs RPyC API (`copy_ticks_from` / `symbol_info_tick`).

## Files

| File | Window | Rows | Trades (`last>0`) |
|------|--------|------|-------------------|
| `WINQ26_202606301200_202606301209.csv` | 12:00–12:09 | 39 237 | 37 401 |
| `PETR4_202606301006_202606301014.csv` | 10:06–10:14 | 599 | 458 |
| `DI1F27_202606300855_202606300929.csv` | 08:55–09:29 | 994 | 817 |

## UI export vs API offset

Terminal CSV flags match API flags with a fixed **`+1024`** offset on the low 8 bits:

| UI (CSV) | API (bridge) | Meaning |
|----------|--------------|---------|
| 2 | 1026 | BID only (quote) |
| 4 | 1028 | ASK only (quote) |
| 6 | 1030 | BID+ASK (quote) |
| **56** | **1080** | LAST+VOL+**BUY** → aggressor **BUYER** |
| **88** | **1112** | LAST+VOL+**SELL** → aggressor **SELLER** |
| **120** | **1144** | LAST+VOL+**BUY+SELL** → **NO_AGGRESSOR** (ambiguous) |

Bit **1024** on API ticks is the UI/API encoding offset — ignore for semantics; test `flags & 0x7F` or check BUY/SELL/LAST directly.

## Aggressor rule (validated on export)

On rows with `last > 0` (trade-like):

```
if flags & LAST:
    if flags & BUY and not (flags & SELL):  → BUYER
    elif flags & SELL and not (flags & BUY): → SELLER
    else: → NO_AGGRESSOR   # includes flags 120 / API 1144
else:
    → NO_AGGRESSOR (quote-only rows: 2, 4, 6)
```

Gate: **XP `VenueProfile` only** (`map_tick_flags_to_aggressor`).

## Coverage (export)

| Symbol | BUY (56) | SELL (88) | Both (120) | Side-hint coverage* |
|--------|----------|-----------|------------|---------------------|
| WINQ26 | 49.8% | 43.8% | 1.7% | **98.2%** |
| PETR4 | 22.9% | 38.9% | 14.7% | **80.8%** |
| DI1F27 | 55.4% | 16.8% | 10.0% | **87.9%** |

\* `(BUY-only + SELL-only) / trades(last>0)` — excludes ambiguous `120`.

100% of trade rows in export carry `TICK_FLAG_LAST`.

## Price direction sanity (WINQ26 / PETR4)

| Flag | WINQ26 last↑ / last↓ | PETR4 last↑ / last↓ |
|------|----------------------|---------------------|
| 56 BUY | 7070 / 1955 | 82 / 3 |
| 88 SELL | 1608 / 6617 | 11 / 112 |

BUY correlates with upticks; SELL with downticks — consistent with MT5 “last Buy/Sell changed” hint (not certified B3 tape aggressor).

## Adapter implication

- Map using **API flags** from bridge/WS (`WireTick.flags`).
- Historical `copy_ticks_*`: parse `row["flags"]` (not yet wired).
- Poll path `process_tick_by_tick_all_last`: no flags → keep `NO_AGGRESSOR`.
- Tickmill: unchanged (`trade_ticks=UNSUPPORTED`).
