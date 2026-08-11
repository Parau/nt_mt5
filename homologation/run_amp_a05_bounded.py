"""
AMP live probe for A05 bounded historical TradeTicks.

Purpose/Single Responsibility:
    Exercise RequestTradeTicks(start, end, limit=0) against a real AMP RPyC
    terminal and report empty/non-empty/failure semantics.

Data Flow & Dependencies:
    HomologationConfig → MetaTrader5DataClient → get_historical_trade_ticks_range
    → copy_ticks_range(COPY_TICKS_TRADE). Writes JSON under homologation/.

Premises & Limitations:
    Requires AMP container on MT5_PORT (default 18814). Does not certify
    live↔historical stream parity (use a05_trade_tick_parity with a longer
    open-market capture for that gate).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.data.messages import RequestTradeTicks
from nautilus_trader.model.identifiers import InstrumentId, Symbol, TraderId, Venue

from homologation.config import HomologationConfig
from homologation.support.clients import reset_mt5_client_cache
from nautilus_mt5.client.errors import MT5HistoricalDataError
from nautilus_mt5.client.types import MT5TerminalAccessMode
from nautilus_mt5.config import (
    ExternalRPyCTerminalConfig,
    MetaTrader5DataClientConfig,
    MetaTrader5InstrumentProviderConfig,
)
from nautilus_mt5.constants import MT5_VENUE
from nautilus_mt5.data_types import MT5Symbol
from nautilus_mt5.factories import MT5LiveDataClientFactory


_VENUE = Venue("METATRADER_5")


async def _make_client(cfg: HomologationConfig, symbol: str):
    clock = LiveClock()
    msgbus = MessageBus(TraderId("HOMOLOG-A05"), clock)
    cache = Cache()
    loop = asyncio.get_running_loop()
    data_client = MT5LiveDataClientFactory.create(
        loop=loop,
        name="MT5",
        config=MetaTrader5DataClientConfig(
            client_id=1,
            terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
            external_rpyc=ExternalRPyCTerminalConfig(host=cfg.host, port=cfg.port, keep_alive=True),
            venue_profile=cfg.venue_profile,
            instrument_provider=MetaTrader5InstrumentProviderConfig(
                load_symbols=frozenset({MT5Symbol(symbol=symbol, broker=cfg.broker)}),
            ),
        ),
        msgbus=msgbus,
        cache=cache,
        clock=clock,
    )
    await data_client._connect()
    iid = InstrumentId(Symbol(symbol), _VENUE)
    await data_client.instrument_provider.load_async(iid)
    instrument = data_client.instrument_provider.find(iid) or cache.instrument(iid)
    if instrument is not None and cache.instrument(iid) is None:
        cache.add_instrument(instrument)
    return data_client, clock, iid


async def _bounded_request(data_client, clock, iid, start, end, label: str) -> dict:
    delivered: list = []
    calls: list = []

    def _capture(instrument_id, ticks, correlation_id, start=None, end=None, params=None):
        delivered.extend(ticks)
        calls.append(
            {
                "correlation_id": str(correlation_id),
                "n": len(ticks),
                "start": str(start),
                "end": str(end),
                "params": params,
            },
        )

    data_client._handle_trade_ticks = _capture
    req_id = UUID4()
    req = RequestTradeTicks(
        instrument_id=iid,
        start=start,
        end=end,
        limit=0,
        client_id=data_client.id,
        venue=_VENUE,
        callback=None,
        request_id=req_id,
        ts_init=clock.timestamp_ns(),
        params={"a05_probe": label},
    )
    try:
        await data_client._request_trade_ticks(req)
        sample = None
        if delivered:
            t = delivered[0]
            sample = {
                "ts_event": int(t.ts_event),
                "price": float(t.price),
                "size": float(t.size),
                "aggressor": str(t.aggressor_side),
            }
        return {
            "label": label,
            "ok": True,
            "error": None,
            "n_ticks": len(delivered),
            "response_calls": calls,
            "request_id": str(req_id),
            "sample": sample,
        }
    except MT5HistoricalDataError as exc:
        return {
            "label": label,
            "ok": False,
            "error": f"MT5HistoricalDataError: {exc}",
            "n_ticks": 0,
            "response_calls": calls,
            "request_id": str(req_id),
            "sample": None,
        }


async def main() -> int:
    cfg = HomologationConfig.from_env()
    symbol = os.environ.get("HOMOLOG_TRADE_SYMBOLS", cfg.symbol).split(",")[0].strip()
    print("=" * 64)
    print("  A05 BOUNDED TradeTicks — AMP live probe")
    print(f"  Gateway : {cfg.host}:{cfg.port}")
    print(f"  Profile : {cfg.venue_profile.name}")
    print(f"  Symbol  : {symbol}")
    print("=" * 64)

    reset_mt5_client_cache()
    data_client, clock, iid = await _make_client(cfg, symbol)

    # Spy provider calls through the real client mt5 surface.
    mt5 = data_client._client._mt5_client["mt5"]
    provider_calls: list = []
    orig = mt5.copy_ticks_range

    def _spy_range(*args, **kwargs):
        provider_calls.append({"args": args, "kwargs": kwargs})
        return orig(*args, **kwargs)

    mt5.copy_ticks_range = _spy_range

    end = pd.Timestamp.utcnow()
    start_recent = end - timedelta(minutes=30)
    start_emptyish = end - timedelta(seconds=1)

    results = []
    results.append(
        await _bounded_request(
            data_client, clock, iid, start_recent, end, "recent_30m",
        ),
    )
    results.append(
        await _bounded_request(
            data_client, clock, iid, start_emptyish, end, "last_1s",
        ),
    )

    # Far-future empty success (valid interval, likely zero ticks).
    fut_start = end + timedelta(days=30)
    fut_end = fut_start + timedelta(minutes=1)
    results.append(
        await _bounded_request(
            data_client, clock, iid, fut_start, fut_end, "future_empty",
        ),
    )

    report = {
        "gateway": f"{cfg.host}:{cfg.port}",
        "profile": cfg.venue_profile.name,
        "symbol": symbol,
        "provider_calls": [
            {
                "symbol": c["args"][0] if c["args"] else None,
                "from": c["args"][1] if len(c["args"]) > 1 else None,
                "to": c["args"][2] if len(c["args"]) > 2 else None,
                "flags": c["args"][3] if len(c["args"]) > 3 else None,
            }
            for c in provider_calls
        ],
        "results": results,
    }

    out = Path("homologation/last_amp_a05_bounded_report.json")
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\nProvider copy_ticks_range calls:")
    for c in report["provider_calls"]:
        print(f"  {c}")

    failed = False
    for r in results:
        status = "PASS" if r["ok"] else "FAIL"
        if not r["ok"]:
            failed = True
        # future_empty must succeed with DataResponse([]) semantics (ok + response call)
        if r["label"] == "future_empty" and r["ok"] and not r["response_calls"]:
            status = "FAIL"
            failed = True
            r["error"] = "expected _handle_trade_ticks even for empty success"
        print(
            f"[{status}] {r['label']}: n={r['n_ticks']} "
            f"error={r['error']} sample={r['sample']}",
        )

    flags_ok = all(c.get("flags") == 2 for c in report["provider_calls"])
    print(f"[ {'PASS' if flags_ok else 'FAIL'} ] all provider flags == COPY_TICKS_TRADE (2)")
    if not flags_ok:
        failed = True

    print(f"\nJSON report: {out}")
    try:
        data_client.stop()
    except Exception:
        pass
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
