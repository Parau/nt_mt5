# Broker probes (ad-hoc, not deployed)

Self-contained MQL5 scripts for broker ground-truth. **Not** copied by `sync_to_mt5_data.bat`.

## Copy to terminal

Copy the entire `probe/` folder into the MT5 data directory, preserving layout:

```
Terminal\<hash>\MQL5\Scripts\probe\
  ProbeBroker.mqh
  probe_tickmill_market_off_hours.mq5
  ...
```

In MetaEditor: open any `.mq5`, compile (F7), run from Navigator → Scripts.

Reports are written to `MQL5/Files/probe_*_<server>_<login>.txt` when `InpWriteFile=true`.

## When to run

| Script | When |
|--------|------|
| `*_market_off_hours` | Any time — `SymbolInfo*`, sessions, DOM. No orders. |
| `*_market_live` | Trade session open — adds `SymbolInfoTick`, `OrderCheck` filling probe. **No `OrderSend`.** |

### Tickmill

- **USTEC** — Mon–Fri US cash session (server time in probe output).
- **BTCUSD** — ~24/7; off-hours may still return ticks.

### XP / B3

- Run `*_market_live` during B3 session for meaningful ticks and `OrderCheck`.
- Update contract names on rollover (e.g. `WDON26` → next month).

### AMP Global USA (AMPGlobalUSA-Demo)

- **EPU26, MESU26, ENQU26, MNQU26** — CME-style futures; server time in probe output.
- Run `*_market_live` during CME trade session (RTH or extended per symbol).
- Update contract suffix on rollover (e.g. `U26` → next expiry).
- Confirm exact symbol names in Market Watch before probing.

## Layout

| Path | Role |
|------|------|
| `ProbeBroker.mqh` | Shared probe logic |
| `probe_{broker}_market_*.mq5` | Multi-symbol runners |
| `tickmill/`, `xp/`, `amp/` | Thin per-instrument wrappers |

## Document results

- Tickmill → `res/tickmill_restrictions.md` (Declared vs Observed)
- XP → `res/xp_b3_restrictions.md`
- AMP → `res/amp_restrictions.md` (when created)
