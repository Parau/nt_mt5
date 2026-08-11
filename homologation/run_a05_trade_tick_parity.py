"""
A05 live↔historical TradeTick stream-parity homologation (Tier 1.5).

Purpose/Single Responsibility:
    Capture the effective live TradeTick stream (MQL5 feed → adapter), wait for
    the interval to be historically queryable, request the same bounds via A05,
    and compare ordered samples.

Data Flow & Dependencies:
    Live: TradingNode SubscribeTradeTicks with feed.enabled → Strategy.on_trade_tick.
    Historical: MetaTrader5DataClient bounded RequestTradeTicks / A05 helper.
    Compare via homologation.support.a05_trade_tick_parity.compare_trade_tick_streams.
    Writes JSON under homologation/.

Premises & Limitations:
    Requires AMP (or XP) open market, RPyC bridge, and NT5TickFeedService → host
    feed port. Tickmill is out of scope. Any unexplained mismatch is FAIL and
    blocks B07 warmup certification.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pandas as pd
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_trader.config import StrategyConfig
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.data.messages import RequestTradeTicks
from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.identifiers import InstrumentId, Symbol, TraderId, Venue
from nautilus_trader.trading.strategy import Strategy

from homologation.config import HomologationConfig, probe_symbol_tick
from homologation.node_factory import build_trading_node, instrument_id
from homologation.scenarios.node_runner import NodeStopGate, run_node_until
from homologation.support.a05_trade_tick_parity import compare_trade_tick_streams
from homologation.support.clients import reset_mt5_client_cache
from nautilus_mt5.client.types import MT5TerminalAccessMode
from nautilus_mt5.config import (
    ExternalRPyCTerminalConfig,
    MetaTrader5DataClientConfig,
    MetaTrader5InstrumentProviderConfig,
)
from nautilus_mt5.data_types import MT5Symbol
from nautilus_mt5.factories import MT5LiveDataClientFactory
from nautilus_mt5.metatrader5.MetaTrader5 import MetaTrader5

_VENUE = Venue("METATRADER_5")


class _ParityCaptureConfig(StrategyConfig, frozen=True):
    instrument_id: object
    duration_secs: float
    min_ticks: int


class _ParityCaptureStrategy(Strategy):
    """Records every live TradeTick delivered through the Nautilus actor path."""

    def __init__(
        self,
        config: _ParityCaptureConfig,
        done: threading.Event,
        outcome: dict[str, Any],
        stop_node: Callable[[], None],
    ) -> None:
        super().__init__(config)
        self._done = done
        self._outcome = outcome
        self._stop_node = stop_node
        self._timer: threading.Timer | None = None
        self.ticks: list[TradeTick] = []

    def on_start(self) -> None:
        if self.cache.instrument(self.config.instrument_id) is None:
            self._fail("Instrument not in cache")
            return
        self._outcome["capture_wall_start"] = time.time()
        self.subscribe_trade_ticks(instrument_id=self.config.instrument_id)
        self._timer = threading.Timer(self.config.duration_secs, self._finish)
        self._timer.daemon = True
        self._timer.start()

    def on_trade_tick(self, tick: TradeTick) -> None:
        self.ticks.append(tick)
        n = len(self.ticks)
        if n <= 3 or n % 25 == 0:
            self.log.info(
                f"live TradeTick #{n}: ts_event={tick.ts_event} "
                f"price={tick.price} size={tick.size} aggressor={tick.aggressor_side}",
            )

    def on_stop(self) -> None:
        if self._timer is not None:
            self._timer.cancel()

    def _finish(self) -> None:
        self._outcome["capture_wall_end"] = time.time()
        self._outcome["ticks"] = list(self.ticks)
        n = len(self.ticks)
        min_ticks = self.config.min_ticks
        if n >= min_ticks:
            self._outcome["ok"] = True
            self._outcome["detail"] = f"captured {n} live TradeTick(s)"
        else:
            self._outcome["ok"] = False
            self._outcome["detail"] = (
                f"only {n} live TradeTick(s) in {self.config.duration_secs:.0f}s "
                f"(min={min_ticks})"
            )
        self._done.set()
        self._stop_node()
        self.stop()

    def _fail(self, detail: str) -> None:
        self._outcome["ok"] = False
        self._outcome["detail"] = detail
        self._done.set()
        self.stop()


def _git_commit() -> str:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=_ROOT,
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
        )
    except Exception:
        return "unknown"


def _provider_meta(cfg: HomologationConfig) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "metatrader5_package": "unknown",
        "terminal_build": None,
        "broker_server": None,
        "account_login": None,
    }
    try:
        import MetaTrader5 as official  # type: ignore

        meta["metatrader5_package"] = getattr(official, "__version__", "installed")
    except Exception:
        meta["metatrader5_package"] = "n/a (EXTERNAL_RPYC host)"

    try:
        mt5 = MetaTrader5(cfg.host, cfg.port)
        mt5.initialize()
        ver = mt5.version()
        info = mt5.account_info()
        term = mt5.terminal_info()
        meta["terminal_build"] = ver[1] if isinstance(ver, (list, tuple)) and len(ver) > 1 else ver
        if info is not None:
            meta["account_login"] = info.get("login") if isinstance(info, dict) else getattr(info, "login", None)
            meta["broker_server"] = (
                info.get("server") if isinstance(info, dict) else getattr(info, "server", None)
            )
        if term is not None and meta["terminal_build"] is None:
            meta["terminal_build"] = (
                term.get("build") if isinstance(term, dict) else getattr(term, "build", None)
            )
    except Exception as exc:
        meta["probe_error"] = str(exc)
    return meta


async def _capture_live(
    cfg: HomologationConfig,
    symbol: str,
    *,
    duration_secs: float,
    min_ticks: int,
) -> dict[str, Any]:
    done = threading.Event()
    outcome: dict[str, Any] = {"ok": False, "detail": "", "ticks": []}
    stop_gate_holder: list[NodeStopGate | None] = [None]
    strategy_holder: list[_ParityCaptureStrategy | None] = [None]

    def _build():
        node = build_trading_node(cfg, trader_id="HOMOLOG-A05-PARITY", symbols=[symbol])
        strat = _ParityCaptureStrategy(
            config=_ParityCaptureConfig(
                strategy_id=f"A05-PARITY-{symbol}",
                instrument_id=instrument_id(symbol),
                duration_secs=duration_secs,
                min_ticks=min_ticks,
            ),
            done=done,
            outcome=outcome,
            stop_node=lambda: (
                stop_gate_holder[0].request_stop() if stop_gate_holder[0] else None
            ),
        )
        strategy_holder[0] = strat
        node.trader.add_strategy(strat)
        return node

    reset_mt5_client_cache()
    await run_node_until(_build, done, duration_secs + 120.0, stop_gate_holder)
    if strategy_holder[0] is not None and not outcome.get("ticks"):
        outcome["ticks"] = list(strategy_holder[0].ticks)
    return outcome


def _tick_sample(tick: TradeTick) -> dict[str, Any]:
    return {
        "ts_event": int(tick.ts_event),
        "price": float(tick.price),
        "price_raw": int(tick.price.raw),
        "size": float(tick.size),
        "size_raw": int(tick.size.raw),
        "aggressor_side": str(tick.aggressor_side),
    }


def _ts_overlap_diagnostics(
    live_ticks: list[TradeTick],
    hist_ticks: list[TradeTick],
) -> dict[str, Any]:
    """Compare timestamp sets to separate provider scarcity from adapter filtering."""
    live_ts = [int(t.ts_event) for t in live_ticks]
    hist_ts = [int(t.ts_event) for t in hist_ticks]
    live_set = set(live_ts)
    hist_set = set(hist_ts)
    only_live = sorted(live_set - hist_set)
    only_hist = sorted(hist_set - live_set)
    both = sorted(live_set & hist_set)

    def _mult(ts_list: list[int]) -> dict[str, int]:
        from collections import Counter

        counts = Counter(ts_list)
        multi = {str(k): v for k, v in counts.items() if v > 1}
        return {
            "unique_ts": len(counts),
            "rows": len(ts_list),
            "max_multiplicity": max(counts.values()) if counts else 0,
            "equal_ts_groups": len(multi),
        }

    return {
        "live_ts_stats": _mult(live_ts),
        "hist_ts_stats": _mult(hist_ts),
        "ts_in_both": len(both),
        "ts_only_live": len(only_live),
        "ts_only_hist": len(only_hist),
        "only_live_ts_head": only_live[:20],
        "only_hist_ts_head": only_hist[:20],
        "live_first_last": [live_ts[0], live_ts[-1]] if live_ts else None,
        "hist_first_last": [hist_ts[0], hist_ts[-1]] if hist_ts else None,
    }


def _probe_provider_raw_counts(
    cfg: HomologationConfig,
    symbol: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict[str, Any]:
    """
    Raw MT5 copy_ticks_range sizes for TRADE vs ALL over the same second window.

    Distinguishes 'history returns fewer rows' from A05 routing dropping rows.
    """
    import numpy as np

    start_ns = int(start.value)
    end_ns = int(end.value)
    fetch_start = start_ns // 1_000_000_000
    fetch_end = (end_ns + 1_000_000_000 - 1) // 1_000_000_000
    if fetch_end <= fetch_start:
        fetch_end = fetch_start + 1

    out: dict[str, Any] = {
        "fetch_start_seconds": fetch_start,
        "fetch_end_seconds": fetch_end,
    }
    try:
        mt5 = MetaTrader5(cfg.host, cfg.port)
        mt5.initialize()
        trade_flags = mt5.get_constant("COPY_TICKS_TRADE")
        all_flags = mt5.get_constant("COPY_TICKS_ALL")
        raw_trade = mt5.copy_ticks_range(symbol, fetch_start, fetch_end, trade_flags)
        raw_all = mt5.copy_ticks_range(symbol, fetch_start, fetch_end, all_flags)

        def _raw_info(raw: Any) -> dict[str, Any]:
            if raw is None:
                return {"is_none": True, "len": None, "exact_local_ndarray": False}
            return {
                "is_none": False,
                "exact_local_ndarray": type(raw) is np.ndarray,
                "len": int(len(raw)),
                "dtype_names": list(raw.dtype.names) if raw.dtype.names is not None else None,
            }

        def _in_bound_count(raw: Any) -> int | None:
            if raw is None:
                return None
            if len(raw) == 0:
                return 0
            if raw.dtype.names is None or "time_msc" not in raw.dtype.names:
                return None
            n = 0
            for row in raw:
                ts = int(row["time_msc"]) * 1_000_000
                if start_ns <= ts <= end_ns:
                    n += 1
            return n

        out["COPY_TICKS_TRADE"] = trade_flags
        out["COPY_TICKS_ALL"] = all_flags
        out["raw_trade"] = _raw_info(raw_trade)
        out["raw_all"] = _raw_info(raw_all)
        out["raw_trade_in_bound_ns"] = _in_bound_count(raw_trade)
        out["raw_all_in_bound_ns"] = _in_bound_count(raw_all)
        out["last_error"] = mt5.last_error()
    except Exception as exc:
        out["error"] = str(exc)
    return out


async def _request_a05_history(
    cfg: HomologationConfig,
    symbol: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> list[TradeTick]:
    reset_mt5_client_cache()
    clock = LiveClock()
    msgbus = MessageBus(TraderId("HOMOLOG-A05-HIST"), clock)
    cache = Cache()
    loop = asyncio.get_running_loop()
    data_client = MT5LiveDataClientFactory.create(
        loop=loop,
        name="MT5",
        config=MetaTrader5DataClientConfig(
            client_id=1,
            terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
            external_rpyc=ExternalRPyCTerminalConfig(
                host=cfg.host, port=cfg.port, keep_alive=True,
            ),
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

    delivered: list[TradeTick] = []

    def _capture(instrument_id, ticks, correlation_id, start=None, end=None, params=None):
        delivered.extend(ticks)

    data_client._handle_trade_ticks = _capture
    req = RequestTradeTicks(
        instrument_id=iid,
        start=start,
        end=end,
        limit=0,
        client_id=data_client.id,
        venue=_VENUE,
        callback=None,
        request_id=UUID4(),
        ts_init=clock.timestamp_ns(),
        params={"a05_parity": True},
    )
    try:
        await data_client._request_trade_ticks(req)
    finally:
        try:
            data_client.stop()
        except Exception:
            pass
        reset_mt5_client_cache()
    return delivered


async def main() -> int:
    if os.environ.get("MT5_FEED_ENABLED", "").strip() != "1":
        os.environ["MT5_FEED_ENABLED"] = "1"

    cfg = HomologationConfig.from_env()
    symbol = os.environ.get("HOMOLOG_TRADE_SYMBOLS", cfg.symbol).split(",")[0].strip()
    duration = float(os.environ.get("HOMOLOG_A05_PARITY_SECS", "60"))
    min_ticks = int(os.environ.get("HOMOLOG_A05_PARITY_MIN_TICKS", "5"))
    settle = float(os.environ.get("HOMOLOG_A05_PARITY_SETTLE_SECS", "8"))
    report_path = Path(
        os.environ.get(
            "HOMOLOG_REPORT_JSON",
            "homologation/last_a05_trade_tick_parity_report.json",
        ),
    )

    print("=" * 64)
    print("  A05 live↔historical TradeTick PARITY")
    print(f"  Gateway : {cfg.host}:{cfg.port}")
    print(f"  Feed    : ws://{cfg.feed_host}:{cfg.feed_port}{cfg.feed_path}")
    print(f"  Profile : {cfg.venue_profile.name}")
    print(f"  Symbol  : {symbol}")
    print(f"  Capture : {duration:.0f}s (min_ticks={min_ticks}, settle={settle:.0f}s)")
    print("=" * 64)

    meta = _provider_meta(cfg)
    tick = probe_symbol_tick(cfg.host, cfg.port, symbol)
    if tick is None:
        report = {
            "result": "FAIL",
            "reason": f"{symbol}: no live bid/ask (market closed?)",
            "adapter_commit": _git_commit(),
            "venue_profile": cfg.venue_profile.name,
            "instrument": symbol,
            **meta,
        }
        report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"[FAIL] {report['reason']}")
        print(f"JSON report: {report_path}")
        return 1

    print("\n--- Phase 1: live capture (feed → adapter TradeTicks) ---")
    try:
        live_outcome = await _capture_live(
            cfg, symbol, duration_secs=duration, min_ticks=min_ticks,
        )
    except TimeoutError:
        print(f"[FAIL] live capture timed out after {duration + 120:.0f}s")
        return 1
    except Exception as exc:
        print(f"[FAIL] live capture error: {exc}")
        return 1

    live_ticks: list[TradeTick] = list(live_outcome.get("ticks") or [])
    print(f"  {live_outcome.get('detail')}")
    if not live_outcome.get("ok") or not live_ticks:
        report = {
            "result": "FAIL",
            "reason": live_outcome.get("detail", "no live ticks"),
            "adapter_commit": _git_commit(),
            "venue_profile": cfg.venue_profile.name,
            "instrument": symbol,
            "live_count": len(live_ticks),
            **meta,
        }
        report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"[FAIL] {report['reason']}")
        print(f"JSON report: {report_path}")
        return 1

    start_ns = min(int(t.ts_event) for t in live_ticks)
    end_ns = max(int(t.ts_event) for t in live_ticks)
    start = pd.Timestamp(start_ns, unit="ns", tz="UTC")
    end = pd.Timestamp(end_ns, unit="ns", tz="UTC")
    print(f"  Logical interval: {start} → {end}")
    print(f"  Live count: {len(live_ticks)}")

    print(f"\n--- Phase 2: settle {settle:.0f}s for historical queryability ---")
    await asyncio.sleep(settle)

    print("\n--- Phase 3: A05 bounded historical request ---")
    try:
        hist_ticks = await _request_a05_history(cfg, symbol, start, end)
    except Exception as exc:
        report = {
            "result": "FAIL",
            "reason": f"A05 historical request failed: {exc}",
            "adapter_commit": _git_commit(),
            "venue_profile": cfg.venue_profile.name,
            "instrument": symbol,
            "capture_start": str(start),
            "capture_end": str(end),
            "live_count": len(live_ticks),
            **meta,
        }
        report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"[FAIL] {report['reason']}")
        print(f"JSON report: {report_path}")
        return 1

    print(f"  Historical count: {len(hist_ticks)}")

    print("\n--- Phase 3b: raw provider counts (TRADE vs ALL) ---")
    provider_raw = _probe_provider_raw_counts(cfg, symbol, start, end)
    print(f"  raw TRADE len={provider_raw.get('raw_trade', {}).get('len')} "
          f"in_bound={provider_raw.get('raw_trade_in_bound_ns')}")
    print(f"  raw ALL   len={provider_raw.get('raw_all', {}).get('len')} "
          f"in_bound={provider_raw.get('raw_all_in_bound_ns')}")
    print(f"  A05 emitted historical TradeTicks={len(hist_ticks)}")

    print("\n--- Phase 4: compare ordered streams ---")
    mismatches = compare_trade_tick_streams(live_ticks, hist_ticks)
    passed = len(mismatches) == 0
    result = "PASS" if passed else "FAIL"
    overlap = _ts_overlap_diagnostics(live_ticks, hist_ticks)

    # Interpretation aids for offline analysis.
    trade_in_bound = provider_raw.get("raw_trade_in_bound_ns")
    interpretation = {
        "a05_emitted_vs_raw_trade_in_bound": (
            None
            if trade_in_bound is None
            else {
                "raw_trade_in_bound": trade_in_bound,
                "a05_emitted": len(hist_ticks),
                "dropped_by_routing_or_conversion": int(trade_in_bound) - len(hist_ticks),
            }
        ),
        "live_vs_raw_trade_in_bound": (
            None
            if trade_in_bound is None
            else {
                "live_emitted": len(live_ticks),
                "raw_trade_in_bound": trade_in_bound,
                "live_minus_raw_trade": len(live_ticks) - int(trade_in_bound),
            }
        ),
        "hypothesis": (
            "provider_returns_fewer_TRADE_rows_than_live_feed"
            if trade_in_bound is not None and int(trade_in_bound) < len(live_ticks)
            else (
                "a05_routing_drops_rows"
                if trade_in_bound is not None and int(trade_in_bound) > len(hist_ticks)
                else "streams_aligned_or_inconclusive"
            )
        ),
    }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = Path(
        os.environ.get(
            "HOMOLOG_REPORT_JSON",
            f"homologation/last_a05_trade_tick_parity_report_{stamp}.json",
        ),
    )
    streams_path = report_path.with_name(report_path.stem + "_streams.json")

    streams_payload = {
        "live_ticks": [_tick_sample(t) for t in live_ticks],
        "historical_ticks": [_tick_sample(t) for t in hist_ticks],
    }
    streams_path.write_text(json.dumps(streams_payload, indent=2), encoding="utf-8")

    report = {
        "result": result,
        "adapter_commit": _git_commit(),
        "metatrader5_package_version": meta.get("metatrader5_package"),
        "terminal_build": meta.get("terminal_build"),
        "broker_server": meta.get("broker_server"),
        "account_login": meta.get("account_login"),
        "venue_profile": cfg.venue_profile.name,
        "instrument": symbol,
        "gateway": f"{cfg.host}:{cfg.port}",
        "feed": f"ws://{cfg.feed_host}:{cfg.feed_port}{cfg.feed_path}",
        "capture_start": str(start),
        "capture_end": str(end),
        "capture_wall_start": live_outcome.get("capture_wall_start"),
        "capture_wall_end": live_outcome.get("capture_wall_end"),
        "live_count": len(live_ticks),
        "historical_count": len(hist_ticks),
        "provider_raw": provider_raw,
        "ts_overlap": overlap,
        "interpretation": interpretation,
        "live_sample_head": [_tick_sample(t) for t in live_ticks[:5]],
        "live_sample_tail": [_tick_sample(t) for t in live_ticks[-5:]],
        "hist_sample_head": [_tick_sample(t) for t in hist_ticks[:5]],
        "hist_sample_tail": [_tick_sample(t) for t in hist_ticks[-5:]],
        "streams_file": str(streams_path).replace("\\", "/"),
        "first_mismatch": mismatches[0] if mismatches else None,
        "mismatch_count": len(mismatches),
        "mismatches_head": mismatches[:30],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    # Keep a stable pointer for the latest run.
    latest = Path("homologation/last_a05_trade_tick_parity_report.json")
    latest.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    if passed:
        print(f"[ PASS ] live={len(live_ticks)} historical={len(hist_ticks)} — streams match")
    else:
        print(f"[ FAIL ] {len(mismatches)} mismatch(es); first: {mismatches[0]}")
        for line in mismatches[:10]:
            print(f"    - {line}")
        print(f"  hypothesis: {interpretation['hypothesis']}")
    print(f"JSON report : {report_path}")
    print(f"Streams file: {streams_path}")
    print(f"Latest alias: {latest}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
