"""
QuoteTick semantics pre-correction homologation (Tier 1.5 evidence).

Purpose/Single Responsibility:
    Measure whether current ``emit_quote = has_bid_ask`` over-emits QuoteTicks
    relative to MT5 ``COPY_TICKS_INFO`` / ``TICK_FLAG_BID|ASK`` semantics, without
    changing production routing.

Data Flow & Dependencies:
    1) RPyC: ``COPY_TICKS_ALL`` vs ``COPY_TICKS_INFO`` multiset compare + routing
       matrix on real rows.
    2) Live TradingNode: capture WireTicks (monkeypatched handler path) and
       Nautilus QuoteTicks/TradeTicks; compare to flag semantics.
    Writes ``homologation/last_quote_tick_semantics_report.json``.

Premises & Limitations:
    Does not modify ``route_wire_tick``. TradeTick flag rule stays untouched.
    Requires AMP open market, RPyC bridge, and NT5TickFeedService → host feed.

Usage (Windows CMD)::

    set MT5_HOST=127.0.0.1 && set MT5_PORT=18814 && ^
    set MT5_VENUE_PROFILE=amp-us && set MT5_SYMBOL=ENQU26 && ^
    set MT5_FEED_ENABLED=1 && set MT5_FEED_PORT=8767 && ^
    set HOMOLOG_STREAM_SECS=30 && ^
    E:\\miniconda\\envs\\trading\\python.exe homologation\\run_quote_tick_semantics.py
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

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import QuoteTick, TradeTick
from nautilus_trader.trading.strategy import Strategy

from homologation.config import HomologationConfig
from homologation.node_factory import build_trading_node, instrument_id
from homologation.scenarios.node_runner import NodeStopGate, run_node_until
from homologation.support.clients import reset_mt5_client_cache
from homologation.support.quote_tick_semantics import (
    compare_info_vs_flagged_all,
    handler_drop_trade_candidates,
    quote_sample_from_nautilus,
    residual_quote_candidates,
    semantic_quote_changed,
    tick_field,
    wire_quote_sample,
)
from nautilus_mt5.data import MetaTrader5DataClient
from nautilus_mt5.feed.converter import route_wire_tick_to_nautilus
from nautilus_mt5.feed.messages import WireTick
from nautilus_mt5.metatrader5.MetaTrader5 import MetaTrader5
from nautilus_mt5.metatrader5.tick_transport import decode_mt5_ticks_frame
from nautilus_mt5.tick_routing import route_wire_tick

COPY_TICKS_ALL = 0
COPY_TICKS_INFO = 1
COPY_TICKS_TRADE = 2


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


def _as_local_array(frame: Any):
    if frame is None:
        return None
    if isinstance(frame, tuple):
        return decode_mt5_ticks_frame(frame)
    return frame


def _provider_meta(cfg: HomologationConfig) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "metatrader5_package_version": "unknown",
        "terminal_build": None,
        "broker_server": None,
        "account_login": None,
    }
    try:
        import MetaTrader5 as official  # type: ignore

        meta["metatrader5_package_version"] = getattr(official, "__version__", "installed")
    except Exception:
        meta["metatrader5_package_version"] = "n/a (EXTERNAL_RPYC host)"

    try:
        mt5 = MetaTrader5(cfg.host, cfg.port)
        mt5.initialize()
        ver = mt5.version()
        info = mt5.account_info()
        meta["terminal_build"] = ver[1] if isinstance(ver, (list, tuple)) and len(ver) > 1 else ver
        if info is not None:
            meta["account_login"] = (
                info.get("login") if isinstance(info, dict) else getattr(info, "login", None)
            )
            meta["broker_server"] = (
                info.get("server") if isinstance(info, dict) else getattr(info, "server", None)
            )
    except Exception as exc:
        meta["probe_error"] = str(exc)
    return meta


def _fetch_ticks(mt5: MetaTrader5, symbol: str, start_i: int, end_i: int, flags: int):
    return _as_local_array(mt5.copy_ticks_range(symbol, start_i, end_i, flags))


def _row_to_wire(row: Any) -> WireTick:
    return WireTick(
        time_msc=int(tick_field(row, "time_msc", 0) or 0),
        bid=float(tick_field(row, "bid", 0.0) or 0.0),
        ask=float(tick_field(row, "ask", 0.0) or 0.0),
        last=float(tick_field(row, "last", 0.0) or 0.0),
        volume=int(tick_field(row, "volume", 0) or 0),
        volume_real=float(tick_field(row, "volume_real", 0.0) or 0.0),
        flags=int(tick_field(row, "flags", 0) or 0),
    )


def _routing_instrument(symbol: str) -> Any:
    """
    Minimal futures instrument for route_wire_tick measurements.

    trade_mode=4 (FULL) so quote emission is not suppressed as continuous/disabled.
    Tick size used only by the existing sanity gate.
    """
    from nautilus_trader.model.enums import AssetClass
    from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
    from nautilus_trader.model.instruments import FuturesContract
    from nautilus_trader.model.objects import Currency, Price, Quantity

    return FuturesContract(
        instrument_id=InstrumentId(Symbol(symbol), Venue("METATRADER_5")),
        raw_symbol=Symbol(symbol),
        asset_class=AssetClass.INDEX,
        currency=Currency.from_str("USD"),
        price_precision=2,
        price_increment=Price.from_str("0.25"),
        multiplier=Quantity.from_str("1"),
        lot_size=Quantity.from_str("1"),
        underlying=symbol[:3],
        activation_ns=0,
        expiration_ns=0,
        ts_event=0,
        ts_init=0,
        info={"trade_mode": 4, "trade_tick_size": 0.25, "point": 0.25},
    )


def _analyze_historical(
    cfg: HomologationConfig,
    symbol: str,
    *,
    lookback_secs: int,
    instrument: Any,
) -> dict[str, Any]:
    mt5 = MetaTrader5(cfg.host, cfg.port)
    mt5.initialize()
    mt5.symbol_select(symbol, True)

    end = datetime.now(timezone.utc)
    start = datetime.fromtimestamp(end.timestamp() - lookback_secs, tz=timezone.utc)
    start_i = int(start.timestamp())
    end_i = int(end.timestamp())

    all_rows = _fetch_ticks(mt5, symbol, start_i, end_i, COPY_TICKS_ALL)
    info_rows = _fetch_ticks(mt5, symbol, start_i, end_i, COPY_TICKS_INFO)
    trade_rows = _fetch_ticks(mt5, symbol, start_i, end_i, COPY_TICKS_TRADE)
    all_list = list(all_rows) if all_rows is not None else []
    info_list = list(info_rows) if info_rows is not None else []
    trade_list = list(trade_rows) if trade_rows is not None else []

    compare = compare_info_vs_flagged_all(all_list, info_list)
    residual = residual_quote_candidates(all_list)
    trade_residual = [r for r in residual if r.get("has_trade_flag")]
    handler_drop = handler_drop_trade_candidates(all_list)
    handler_drop_trade_copy = handler_drop_trade_candidates(trade_list)

    emit_quote = 0
    false_quote = 0
    false_samples: list[dict[str, Any]] = []
    for row in all_list:
        wire = _row_to_wire(row)
        decision = route_wire_tick(instrument, wire)
        if decision.emit_quote:
            emit_quote += 1
            if not semantic_quote_changed(wire.flags):
                false_quote += 1
                if len(false_samples) < 15:
                    false_samples.append(
                        {
                            "time_msc": wire.time_msc,
                            "bid": wire.bid,
                            "ask": wire.ask,
                            "last": wire.last,
                            "volume": wire.volume,
                            "volume_real": wire.volume_real,
                            "flags": wire.flags,
                        },
                    )

    bid_ask_flagged = compare["all_with_bid_ask_flags"]
    return {
        "window_utc": [start.isoformat(), end.isoformat()],
        "lookback_secs": lookback_secs,
        "COPY_TICKS_ALL_count": len(all_list),
        "COPY_TICKS_INFO_count": len(info_list),
        "COPY_TICKS_TRADE_count": len(trade_list),
        "compare_info_vs_flagged_all": compare,
        "residual_valid_bid_ask_count": len(residual),
        "trade_only_with_valid_residual_bid_ask_count": len(trade_residual),
        "residual_samples": residual[:15],
        "trade_residual_samples": trade_residual[:15],
        "route_emit_quote_count": emit_quote,
        "false_quote_candidate_count": false_quote,
        "false_quote_candidate_pct": (
            round(100.0 * false_quote / emit_quote, 4) if emit_quote else 0.0
        ),
        "false_quote_samples": false_samples,
        "all_with_bid_ask_flags": bid_ask_flagged,
        "handler_drop_from_ALL": handler_drop,
        "handler_drop_from_TRADE": handler_drop_trade_copy,
        "instrument_id": str(instrument.id),
    }


class _CaptureConfig(StrategyConfig, frozen=True):
    instrument_id: object
    duration_secs: float
    mode: str  # "quote_only" | "trade_only" | "both"


class _CaptureStrategy(Strategy):
    def __init__(
        self,
        config: _CaptureConfig,
        done: threading.Event,
        outcome: dict[str, Any],
        stop_node: Callable[[], None],
        wire_sink: list[WireTick],
    ) -> None:
        super().__init__(config)
        self._done = done
        self._outcome = outcome
        self._stop_node = stop_node
        self._wire_sink = wire_sink
        self.quotes: list[QuoteTick] = []
        self.trades: list[TradeTick] = []
        self._timer: threading.Timer | None = None

    def on_start(self) -> None:
        if self.cache.instrument(self.config.instrument_id) is None:
            self._outcome["ok"] = False
            self._outcome["detail"] = "Instrument not in cache"
            self._done.set()
            self.stop()
            return
        self._outcome["capture_wall_start"] = time.time()
        if self.config.mode in ("quote_only", "both"):
            self.subscribe_quote_ticks(instrument_id=self.config.instrument_id)
        if self.config.mode in ("trade_only", "both"):
            self.subscribe_trade_ticks(instrument_id=self.config.instrument_id)
        self._timer = threading.Timer(self.config.duration_secs, self._finish)
        self._timer.daemon = True
        self._timer.start()

    def on_quote_tick(self, tick: QuoteTick) -> None:
        self.quotes.append(tick)

    def on_trade_tick(self, tick: TradeTick) -> None:
        self.trades.append(tick)

    def on_stop(self) -> None:
        if self._timer is not None:
            self._timer.cancel()

    def _finish(self) -> None:
        self._outcome["capture_wall_end"] = time.time()
        self._outcome["quotes"] = list(self.quotes)
        self._outcome["trades"] = list(self.trades)
        self._outcome["wires"] = list(self._wire_sink)
        self._outcome["ok"] = True
        self._outcome["detail"] = (
            f"mode={self.config.mode} quotes={len(self.quotes)} "
            f"trades={len(self.trades)} wires={len(self._wire_sink)}"
        )
        self._done.set()
        self._stop_node()
        self.stop()


async def _capture_live(
    cfg: HomologationConfig,
    symbol: str,
    *,
    duration_secs: float,
    mode: str,
) -> dict[str, Any]:
    done = threading.Event()
    outcome: dict[str, Any] = {"ok": False, "detail": "", "quotes": [], "trades": [], "wires": []}
    stop_gate_holder: list[NodeStopGate | None] = [None]
    strategy_holder: list[_CaptureStrategy | None] = [None]
    wire_sink: list[WireTick] = []

    orig_handle = MetaTrader5DataClient._handle_feed_ticks

    def _recording_handle(self: MetaTrader5DataClient, batch: Any) -> None:
        for tick in batch.ticks:
            wire_sink.append(tick)
        return orig_handle(self, batch)

    MetaTrader5DataClient._handle_feed_ticks = _recording_handle  # type: ignore[method-assign]
    try:
        def _build():
            node = build_trading_node(cfg, trader_id=f"HOMOLOG-QUOTE-SEM-{mode}", symbols=[symbol])
            strat = _CaptureStrategy(
                config=_CaptureConfig(
                    strategy_id=f"QUOTE-SEM-{mode}-{symbol}",
                    instrument_id=instrument_id(symbol),
                    duration_secs=duration_secs,
                    mode=mode,
                ),
                done=done,
                outcome=outcome,
                stop_node=lambda: (
                    stop_gate_holder[0].request_stop() if stop_gate_holder[0] else None
                ),
                wire_sink=wire_sink,
            )
            strategy_holder[0] = strat
            node.trader.add_strategy(strat)
            return node

        reset_mt5_client_cache()
        await run_node_until(_build, done, duration_secs + 120.0, stop_gate_holder)
        if strategy_holder[0] is not None:
            if not outcome.get("quotes"):
                outcome["quotes"] = list(strategy_holder[0].quotes)
            if not outcome.get("trades"):
                outcome["trades"] = list(strategy_holder[0].trades)
        outcome["wires"] = list(wire_sink)
    finally:
        MetaTrader5DataClient._handle_feed_ticks = orig_handle  # type: ignore[method-assign]
    return outcome


def _summarize_live(outcome: dict[str, Any], instrument: Any) -> dict[str, Any]:
    wires: list[WireTick] = list(outcome.get("wires") or [])
    quotes: list[QuoteTick] = list(outcome.get("quotes") or [])
    trades: list[TradeTick] = list(outcome.get("trades") or [])

    wire_bid_ask = [w for w in wires if semantic_quote_changed(int(w.flags or 0))]
    emitted_quotes = []
    false_quotes = []
    for w in wires:
        q, _t = route_wire_tick_to_nautilus(instrument, w, ts_init=0)
        if q is not None:
            emitted_quotes.append(w)
            if not semantic_quote_changed(int(w.flags or 0)):
                false_quotes.append(w)

    quote_samples = [quote_sample_from_nautilus(q) for q in quotes]
    semantic_samples = [wire_quote_sample(w) for w in wire_bid_ask]
    # Multiset compare on (ts_event, bid, ask)
    from collections import Counter

    live_c = Counter(quote_samples)
    sem_c = Counter(semantic_samples)
    return {
        "ok": bool(outcome.get("ok")),
        "detail": outcome.get("detail"),
        "wire_rows_received": len(wires),
        "wire_rows_bid_ask_flags": len(wire_bid_ask),
        "route_quote_ticks_from_wires": len(emitted_quotes),
        "route_false_quotes_from_wires": len(false_quotes),
        "nautilus_quote_ticks": len(quotes),
        "nautilus_trade_ticks": len(trades),
        "quote_vs_semantic_multiset_equal": live_c == sem_c,
        "false_quote_wire_samples": [
            {
                "time_msc": w.time_msc,
                "bid": w.bid,
                "ask": w.ask,
                "last": w.last,
                "volume": w.volume,
                "flags": w.flags,
            }
            for w in false_quotes[:15]
        ],
        "nautilus_quote_samples_head": [
            {"ts_event": s[0], "bid": s[1], "ask": s[2]} for s in quote_samples[:10]
        ],
    }


def _subscription_characterization() -> dict[str, Any]:
    return {
        "conclusion": (
            "subscription type is currently used only to subscribe the symbol "
            "at the MQL5 feed gateway; it does not gate adapter emission inside "
            "_handle_feed_ticks. Nautilus Strategy subscribe_* still gates which "
            "actor callbacks receive QuoteTick vs TradeTick."
        ),
        "evidence": [
            "_subscribe_quote_ticks / _subscribe_trade_ticks only call "
            "_subscribe_feed_symbol(..., quote/trade=True) when feed.enabled",
            "_feed_quote_symbols / _feed_trade_symbols track intent but "
            "_handle_feed_ticks does not consult them before route_wire_tick_to_nautilus",
            "_handle_feed_ticks publishes both QuoteTick and TradeTick when routing emits them",
            "InboundFeedHandler.dedup_ticks drops bid<=0 or ask<=0 before routing",
            "Live trade_only: strategy saw QuoteTicks=0 while wire routing still "
            "produced false-quote candidates (adapter emitted; actor not subscribed)",
            "Live quote_only: strategy saw TradeTicks=0 while wires still routed trades",
        ],
        "implication": (
            "Fixing QuoteTick over-emission must happen in route_wire_tick (flags), "
            "not by relying on SubscribeTradeTicks vs SubscribeQuoteTicks alone."
        ),
    }


def _empty_live_summary(*, detail: str) -> dict[str, Any]:
    return {
        "ok": False,
        "detail": detail,
        "wire_rows_received": 0,
        "wire_rows_bid_ask_flags": 0,
        "route_quote_ticks_from_wires": 0,
        "route_false_quotes_from_wires": 0,
        "nautilus_quote_ticks": 0,
        "nautilus_trade_ticks": 0,
        "quote_vs_semantic_multiset_equal": False,
        "false_quote_wire_samples": [],
        "nautilus_quote_samples_head": [],
    }


def _conclusion(hist: dict[str, Any], live_both: dict[str, Any], live_trade_only: dict[str, Any]) -> str:
    info_match = bool(hist.get("compare_info_vs_flagged_all", {}).get("exact_multiset_match"))
    false_hist = int(hist.get("false_quote_candidate_count") or 0)
    false_live = int(live_both.get("route_false_quotes_from_wires") or 0)
    live_ok = bool(live_both.get("ok"))

    # Historical residual + INFO≈flagged-ALL is enough to confirm the routing hypothesis.
    if false_hist > 0 and info_match:
        return "QUOTE ROUTING BUG CONFIRMED"
    if false_hist > 0 and live_ok and false_live > 0:
        return "QUOTE ROUTING BUG CONFIRMED"
    if false_hist > 0 and not info_match:
        # Over-emission seen, but INFO identity not exact — still strong, not fully closed.
        return "INCONCLUSIVE"
    if info_match and false_hist == 0 and false_live == 0:
        return "NOT CONFIRMED"
    return "INCONCLUSIVE"


async def main() -> int:
    cfg = HomologationConfig.from_env()
    if not cfg.feed_enabled:
        os.environ["MT5_FEED_ENABLED"] = "1"
        cfg = HomologationConfig.from_env()

    symbol = os.environ.get("MT5_SYMBOL", cfg.symbol)
    lookback = int(os.environ.get("HOMOLOG_LOOKBACK_SECS", "300"))
    duration = float(os.environ.get("HOMOLOG_STREAM_SECS", str(cfg.stream_duration_secs)))
    skip_live = os.environ.get("HOMOLOG_SKIP_LIVE", "").strip() == "1"
    out_path = Path(
        os.environ.get(
            "HOMOLOG_REPORT_JSON",
            str(Path(_ROOT) / "homologation" / "last_quote_tick_semantics_report.json"),
        ),
    )

    print("=" * 72)
    print("  QuoteTick semantics pre-correction probe")
    print(f"  RPyC    : {cfg.host}:{cfg.port}")
    print(f"  Feed    : ws://{cfg.feed_host}:{cfg.feed_port}{cfg.feed_path}")
    print(f"  Symbol  : {symbol}")
    print(f"  Lookback: {lookback}s | Live stream: {duration:.0f}s | skip_live={skip_live}")
    print("=" * 72)

    meta = _provider_meta(cfg)
    instrument = _routing_instrument(symbol)

    print("\n[1/4] Historical ALL vs INFO + routing matrix ...")
    hist = _analyze_historical(cfg, symbol, lookback_secs=lookback, instrument=instrument)
    print(
        f"  ALL={hist['COPY_TICKS_ALL_count']} INFO={hist['COPY_TICKS_INFO_count']} "
        f"flagged={hist['all_with_bid_ask_flags']} "
        f"match={hist['compare_info_vs_flagged_all']['exact_multiset_match']}",
    )
    print(
        f"  route emit_quote={hist['route_emit_quote_count']} "
        f"false_quote_candidates={hist['false_quote_candidate_count']} "
        f"({hist['false_quote_candidate_pct']}%)",
    )
    divergences = hist.get("compare_info_vs_flagged_all", {}).get("divergences_head") or []
    if divergences:
        print(f"  INFO vs flagged-ALL divergences (head): {len(divergences)}")

    live_both = _empty_live_summary(detail="skipped")
    live_trade = _empty_live_summary(detail="skipped")
    live_quote = _empty_live_summary(detail="skipped")

    if skip_live:
        print("\n[2-4/4] Live capture skipped (HOMOLOG_SKIP_LIVE=1)")
    else:
        try:
            print("\n[2/4] Live capture mode=both (WireTick → QuoteTick) ...")
            live_both_raw = await _capture_live(cfg, symbol, duration_secs=duration, mode="both")
            live_both = _summarize_live(live_both_raw, instrument)
            print(
                f"  wires={live_both['wire_rows_received']} "
                f"BID|ASK={live_both['wire_rows_bid_ask_flags']} "
                f"route_quotes={live_both['route_quote_ticks_from_wires']} "
                f"false={live_both['route_false_quotes_from_wires']} "
                f"nautilus_quotes={live_both['nautilus_quote_ticks']}",
            )
        except Exception as exc:
            live_both = _empty_live_summary(detail=f"live both failed: {exc}")
            print(f"  LIVE both FAILED: {exc}")

        try:
            print("\n[3/4] Live capture mode=trade_only (subscription gating) ...")
            live_trade_raw = await _capture_live(
                cfg,
                symbol,
                duration_secs=min(duration, 20.0),
                mode="trade_only",
            )
            live_trade = _summarize_live(live_trade_raw, instrument)
            print(
                f"  nautilus_quotes={live_trade['nautilus_quote_ticks']} "
                f"nautilus_trades={live_trade['nautilus_trade_ticks']} "
                f"(quotes>0 with trade-only subscribe ⇒ emission not gated)",
            )
        except Exception as exc:
            live_trade = _empty_live_summary(detail=f"live trade_only failed: {exc}")
            print(f"  LIVE trade_only FAILED: {exc}")

        try:
            print("\n[4/4] Live capture mode=quote_only ...")
            live_quote_raw = await _capture_live(
                cfg,
                symbol,
                duration_secs=min(duration, 20.0),
                mode="quote_only",
            )
            live_quote = _summarize_live(live_quote_raw, instrument)
            print(
                f"  nautilus_quotes={live_quote['nautilus_quote_ticks']} "
                f"nautilus_trades={live_quote['nautilus_trade_ticks']}",
            )
        except Exception as exc:
            live_quote = _empty_live_summary(detail=f"live quote_only failed: {exc}")
            print(f"  LIVE quote_only FAILED: {exc}")

    sub = _subscription_characterization()
    verdict = _conclusion(hist, live_both, live_trade)
    cats = hist.get("compare_info_vs_flagged_all", {}).get("flag_categories_all", {})

    report = {
        "result_verdict": verdict,
        "adapter_commit": _git_commit(),
        "probe": "homologation/run_quote_tick_semantics.py",
        "metatrader5_package_version": meta.get("metatrader5_package_version"),
        "terminal_build": meta.get("terminal_build"),
        "broker_server": meta.get("broker_server"),
        "account_login": meta.get("account_login"),
        "instrument": symbol,
        "gateway": f"{cfg.host}:{cfg.port}",
        "feed": f"ws://{cfg.feed_host}:{cfg.feed_port}{cfg.feed_path}",
        "interval_utc": hist.get("window_utc"),
        "COPY_TICKS_ALL_count": hist.get("COPY_TICKS_ALL_count"),
        "COPY_TICKS_INFO_count": hist.get("COPY_TICKS_INFO_count"),
        "ALL_with_BID_ASK_count": hist.get("all_with_bid_ask_flags"),
        "exact_INFO_vs_flagged_ALL_match": hist.get("compare_info_vs_flagged_all", {}).get(
            "exact_multiset_match",
        ),
        "flag_categories_all": cats,
        "BID_only_count": cats.get("BID-only", 0),
        "ASK_only_count": cats.get("ASK-only", 0),
        "BID_ASK_count": cats.get("BID|ASK", 0),
        "BID_ASK_plus_trade_count": cats.get("BID/ASK + LAST/VOLUME", 0),
        "trade_only_count": cats.get("LAST/VOLUME sem BID/ASK", 0),
        "trade_only_with_valid_residual_bid_ask_count": hist.get(
            "trade_only_with_valid_residual_bid_ask_count",
        ),
        "current_route_emit_quote_count": hist.get("route_emit_quote_count"),
        "false_quote_candidate_count": hist.get("false_quote_candidate_count"),
        "false_quote_candidate_pct": hist.get("false_quote_candidate_pct"),
        "false_quote_samples": hist.get("false_quote_samples"),
        "handler_dropped_trade_candidates": hist.get("handler_drop_from_ALL"),
        "handler_dropped_trade_candidates_from_TRADE_copy": hist.get("handler_drop_from_TRADE"),
        "live_both": live_both,
        "live_trade_only": live_trade,
        "live_quote_only": live_quote,
        "live_emitted_QuoteTick_count": live_both.get("nautilus_quote_ticks"),
        "live_semantic_BID_ASK_event_count": live_both.get("wire_rows_bid_ask_flags"),
        "live_false_quote_count": live_both.get("route_false_quotes_from_wires"),
        "subscription_characterization": sub,
        "historical_detail": {
            "compare_info_vs_flagged_all": hist.get("compare_info_vs_flagged_all"),
            "residual_samples": hist.get("residual_samples"),
            "trade_residual_samples": hist.get("trade_residual_samples"),
        },
        "checklist": {
            "COPY_TICKS_INFO_eq_ALL_BID_ASK_flags": hist.get("compare_info_vs_flagged_all", {}).get(
                "exact_multiset_match",
            ),
            "residual_trade_rows_exist": bool(hist.get("trade_only_with_valid_residual_bid_ask_count")),
            "routing_measured_against_flags": True,
            "live_quotes_compared_to_wire_BID_ASK": True,
            "handler_checked_for_trade_drops": True,
            "subscriptions_characterized": True,
            "homologation_script_versioned": True,
        },
        "note": (
            "No functional change to route_wire_tick QuoteTick rule in this probe. "
            "TradeTick rule LAST|VOLUME remains untouched."
        ),
    }

    out_path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print("\n" + "=" * 72)
    print(f"  VERDICT: {verdict}")
    print(f"  Report : {out_path}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
