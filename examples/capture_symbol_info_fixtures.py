"""
Capture real MT5 symbol_info() payloads and write them as JSON fixtures.

Usage
-----
Set optional env vars before running:

    MT5_HOST   — RPyC gateway host  (default: 127.0.0.1)
    MT5_PORT   — RPyC gateway port  (default: 18812)

Then run:

    python examples/capture_symbol_info_fixtures.py

Output files (written to tests/test_data/):
    symbol_info_eurusd.json
    symbol_info_ustec.json    (or the broker-specific index name)
    symbol_info_btcusd.json   (or the broker-specific crypto name)
    symbol_info_xauusd.json   (gold/commodity, bonus fixture)

The script replaces any existing files with real MT5 payloads.
Each file includes a ``_comment`` field with capture timestamp, broker
server name, and MT5 build number so provenance is always traceable.

Prerequisites
-------------
- MT5 terminal must be running and the RPyC server must be listening.
- On Windows with the native MetaTrader5 package, start the RPyC server:
      python -m mt5linux <path/to/python.exe>
- On Linux/Mac, the RPyC server must already be running on the Windows side.
"""

import json
import os
import sys
import datetime
import pathlib

# Ensure the project root is on the path when running from any directory.
PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from nautilus_mt5.metatrader5.MetaTrader5 import MetaTrader5  # raw RPyC client

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
HOST = os.environ.get("MT5_HOST", "127.0.0.1")
PORT = int(os.environ.get("MT5_PORT", 18812))

OUTPUT_DIR = PROJECT_ROOT / "tests" / "test_data"

# Candidate symbol names per fixture slot.
# The script tries each name in order and uses the first one that returns data.
# Add broker-specific aliases here if needed.
SYMBOL_CANDIDATES = {
    "eurusd": ["EURUSD"],
    "ustec":  ["USTEC", "US100", "NAS100", "NASDAQ", "USTEC100", "NDX", "NQ100", "US Tech 100"],
    "btcusd": ["BTCUSD", "BTCUSD.", "XBTUSD", "BTC/USD", "Bitcoin"],
    "xauusd": ["XAUUSD", "GOLD", "XAU/USD", "XAUUSD.", "GOLDm"],
}

# Human-readable description for log output
SYMBOL_DESCRIPTIONS = {
    "eurusd": "Forex pair (SYMBOL_CALC_MODE_FOREX=0)",
    "ustec":  "CFD Index (SYMBOL_CALC_MODE_CFDINDEX=3)",
    "btcusd": "Crypto CFD (SYMBOL_CALC_MODE_CFD=2 or CFDLEVERAGE=4)",
    "xauusd": "Metal/Commodity CFD (SYMBOL_CALC_MODE_CFD=2)",
}

# ---------------------------------------------------------------------------
# MT5SymbolDetails field names (controls which raw fields are kept in fixture)
# ---------------------------------------------------------------------------
SYMBOL_DETAILS_FIELDS = {
    "custom", "chart_mode", "select", "visible",
    "session_deals", "session_buy_orders", "session_sell_orders",
    "volume", "volumehigh", "volumelow",
    "time", "digits", "spread", "spread_float", "ticks_bookdepth",
    "trade_calc_mode", "trade_mode", "start_time", "expiration_time",
    "trade_stops_level", "trade_freeze_level", "trade_exemode",
    "swap_mode", "swap_rollover3days", "margin_hedged_use_leg",
    "expiration_mode", "filling_mode", "order_mode", "order_gtc_mode",
    "option_mode", "option_right",
    "bid", "bidhigh", "bidlow", "ask", "askhigh", "asklow",
    "last", "lasthigh", "lastlow",
    "volume_real", "volumehigh_real", "volumelow_real", "option_strike",
    "point", "trade_tick_value", "trade_tick_value_profit", "trade_tick_value_loss",
    "trade_tick_size", "trade_contract_size",
    "trade_accrued_interest", "trade_face_value", "trade_liquidity_rate",
    "volume_min", "volume_max", "volume_step", "volume_limit",
    "swap_long", "swap_short",
    "margin_initial", "margin_maintenance",
    "session_volume", "session_turnover", "session_interest",
    "session_buy_orders_volume", "session_sell_orders_volume",
    "session_open", "session_close", "session_aw",
    "session_price_settlement", "session_price_limit_min", "session_price_limit_max",
    "margin_hedged",
    "price_change", "price_volatility", "price_theoretical",
    "price_greeks_delta", "price_greeks_theta", "price_greeks_gamma",
    "price_greeks_vega", "price_greeks_rho", "price_greeks_omega",
    "price_sensitivity",
    "basis", "currency_base", "currency_profit", "currency_margin",
    "bank", "description", "exchange", "formula", "isin", "name", "page", "path",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def infer_under_sec_type(path: str | None, calc_mode: int) -> str:
    """Derive under_sec_type from path and trade_calc_mode.

    The path is broker-specific, so we inspect its first component then fall
    back to the calc_mode if the path is empty or unknown.
    """
    if path:
        first = path.replace("\\", "/").split("/")[0].upper()
        if "FOREX" in first or "FX" in first:
            return "FOREX"
        if "INDEX" in first or "INDICES" in first or "INDEXES" in first or "INDIC" in first:
            return "INDEXES"
        if "CRYPTO" in first or "DIGITAL" in first or "BITCOIN" in first:
            return "CRYPTO"
        if "METAL" in first or "PRECIOUS" in first or "GOLD" in first:
            return "METALS"
        if "COMMODITY" in first or "COMMODIT" in first or "ENERGY" in first:
            return "COMMODITY"
        if "EQUITY" in first or "STOCK" in first or "SHARE" in first:
            return "EQUITY"
        # Keep the raw first component for unknown paths — better than discarding it
        return first

    # Fallback from calc_mode
    fallback = {
        0: "FOREX",
        1: "FUTURES",
        2: "CFD",
        3: "INDEXES",
        4: "CRYPTO",
        5: "FOREX",
    }
    return fallback.get(calc_mode, "CFD")


def build_fixture(raw: dict, symbol_name: str, broker: str) -> dict:
    """Convert a raw symbol_info dict into the MT5SymbolDetails fixture format."""
    path = raw.get("path") or raw.get("name", symbol_name)
    calc_mode = raw.get("trade_calc_mode", 0)
    under_sec_type = infer_under_sec_type(path, calc_mode)

    fixture: dict = {}

    # Add only fields that MT5SymbolDetails accepts
    for field in SYMBOL_DETAILS_FIELDS:
        if field in raw:
            fixture[field] = raw[field]

    # Inject the two adapter-specific fields
    fixture["under_sec_type"] = under_sec_type
    fixture["symbol"] = {
        "symbol": symbol_name,
        "broker": broker,
        "sec_type": "",
    }

    return fixture


def try_symbol(mt5: MetaTrader5, candidates: list[str]) -> tuple[str, dict] | None:
    """Return (resolved_name, raw_dict) for the first candidate that returns data."""
    for name in candidates:
        info = mt5.symbol_info(name)
        if info is not None and isinstance(info, dict) and info.get("name"):
            return name, info
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"Connecting to MT5 RPyC gateway at {HOST}:{PORT} …")
    try:
        mt5 = MetaTrader5(host=HOST, port=PORT)
    except RuntimeError as exc:
        print(f"ERROR: could not connect — {exc}")
        sys.exit(1)

    print("Connected. Initializing MT5 terminal link …")
    if not mt5.initialize():
        err = mt5.last_error()
        print(f"ERROR: initialize() failed — {err}")
        sys.exit(1)

    # Provenance metadata
    version_info = mt5.version()           # (500, build, "DD Mon YYYY")
    account = mt5.account_info()           # dict after normalize_rpyc_return

    broker_server = "unknown"
    mt5_build = "unknown"
    if account and isinstance(account, dict):
        broker_server = account.get("server", "unknown")
    if version_info and isinstance(version_info, (list, tuple)) and len(version_info) >= 2:
        mt5_build = str(version_info[1])

    capture_ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"  Broker/server : {broker_server}")
    print(f"  MT5 build     : {mt5_build}")
    print(f"  Capture time  : {capture_ts}")
    print()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    captured: list[str] = []
    failed: list[str] = []

    for slot, candidates in SYMBOL_CANDIDATES.items():
        desc = SYMBOL_DESCRIPTIONS.get(slot, "")
        print(f"[{slot}]  {desc}")
        result = try_symbol(mt5, candidates)
        if result is None:
            print(f"  ✗ None of {candidates} returned data — skipping.")
            failed.append(slot)
            continue

        resolved_name, raw = result
        print(f"  ✓ Resolved to '{resolved_name}'  (trade_calc_mode={raw.get('trade_calc_mode')},"
              f"  path='{raw.get('path')}')")

        fixture = build_fixture(raw, resolved_name, broker_server)

        # Determine output filename: always use the slot name (e.g. ustec) so the
        # test fixtures keep stable names even if the broker calls it US100.
        out_file = OUTPUT_DIR / f"symbol_info_{slot}.json"

        comment = (
            f"{resolved_name} symbol_info payload captured from {broker_server} "
            f"(MT5 build {mt5_build}) on {capture_ts}. "
            f"trade_calc_mode={raw.get('trade_calc_mode')}."
        )

        output = {"_comment": comment}
        output.update(fixture)

        out_file.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  → Written: {out_file.relative_to(PROJECT_ROOT)}")
        captured.append(slot)

    mt5.shutdown()
    print()
    print(f"Done. Captured: {captured or 'none'}  |  Failed/skipped: {failed or 'none'}")

    if failed:
        print()
        print("For failed slots, manually add the broker-specific symbol names to")
        print("SYMBOL_CANDIDATES in examples/capture_symbol_info_fixtures.py and re-run.")

    if captured:
        print()
        print("Run the unit tests to confirm the new fixtures parse correctly:")
        print("  pytest tests/unit/test_parse_instruments.py -v")


if __name__ == "__main__":
    main()
