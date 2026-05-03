# tests/test_data/

Static JSON fixtures representing real MT5 API payloads.

## Purpose

These files contain the field values returned by MT5's `symbol_info()` API call,
translated into the `MT5SymbolDetails` structure used internally by the adapter.
They enable direct unit testing of `parse_instrument()` and related parser functions
without going through the integration stack (fake bridge → provider → parser).

## Provenance

All fixtures in this directory are **real MT5 payloads** captured from a live
Tickmill-Demo terminal (server `Tickmill-Demo`, MT5 build 5833) on 2026-05-03T14:05:01Z
using `examples/capture_symbol_info_fixtures.py`.

Each JSON file contains a `_comment` field recording the exact broker server,
MT5 build number, and capture timestamp for full traceability.

Reference: MT5 API field semantics at
https://www.mql5.com/en/docs/constants/environment_state/marketinfoconstants

## Format

Each JSON file maps directly to `MT5SymbolDetails` fields.
The nested `"symbol"` key maps to an `MT5Symbol(symbol=..., broker=...)`.

Fields not listed default to the `MT5SymbolDetails` zero-value for their type.

## Files

| File | Symbol | Instrument type | trade_calc_mode | Broker path |
|---|---|---|---|---|
| `symbol_info_eurusd.json` | EURUSD | CurrencyPair (with TICKMILL_DEMO_PROFILE) | 0 (FOREX)    | `Forex\EURUSD`    |
| `symbol_info_ustec.json`  | USTEC  | Cfd / INDEX                               | 3 (CFDINDEX) | `CFD-2\USTEC`     |
| `symbol_info_btcusd.json` | BTCUSD | Cfd / CRYPTOCURRENCY                      | 2 (CFD)      | `Cryptos\BTCUSD`  |
| `symbol_info_xauusd.json` | XAUUSD | CurrencyPair / COMMODITY (Tickmill-Demo treats gold as Forex) | 0 (FOREX) | `Forex\XAUUSD` |

**Note on USTEC path**: Tickmill-Demo places USTEC under `CFD-2\`, not `Indexes\`.
`sec_type_to_asset_class` handles this via the `startswith("CFD")` rule → `INDEX`.

**Note on XAUUSD**: On Tickmill-Demo, XAUUSD is classified as `trade_calc_mode=0` (FOREX)
with `path='Forex\XAUUSD'`. The `under_sec_type` is set to `"FOREX"` in the fixture,
which maps to `AssetClass.FX`. This is broker-specific; other brokers may classify gold
under a metals/commodity path.

## Adding new fixtures

The canonical collection tool is `examples/capture_symbol_info_fixtures.py`.

1. Ensure the MT5 RPyC server is running (default: `127.0.0.1:18812`).
2. Set `MT5_HOST` / `MT5_PORT` env vars if needed.
3. Add or adjust symbol name candidates in `SYMBOL_CANDIDATES` for your broker.
4. Run: `python examples/capture_symbol_info_fixtures.py`
5. The script writes files directly to `tests/test_data/` with provenance metadata.
6. Update the table above with any new fixtures.
7. Add a corresponding test parametrize row in `tests/unit/test_parse_instruments.py`.
