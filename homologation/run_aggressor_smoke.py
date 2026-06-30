"""XP aggressor smoke — historical (D31) + live feed SubscribeTradeTicks (D30).

Usage (CMD):
    set MT5_HOST=127.0.0.1 && set MT5_PORT=18813 && set MT5_VENUE_PROFILE=xp_b3 && ^
    set MT5_FEED_ENABLED=1 && set HOMOLOG_TRADE_SYMBOLS=WINQ26 && ^
    E:\\miniconda\\envs\\trading\\python.exe homologation\\run_aggressor_smoke.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import threading
from collections import Counter
from collections.abc import Callable
from datetime import timedelta

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pandas as pd
from nautilus_trader.config import StrategyConfig
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.data.messages import RequestTradeTicks
from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.enums import AggressorSide
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.trading.strategy import Strategy

from homologation.config import HomologationConfig, probe_symbol_tick
from homologation.node_factory import build_trading_node, instrument_id
from homologation.scenarios.closed_market_suite import _instrument_id, _make_data_client
from homologation.scenarios.node_runner import NodeStopGate, run_node_until
from homologation.scenarios.trade_tick_open_market import _trade_symbols
from homologation.support.clients import reset_mt5_client_cache

_VENUE = Venue("METATRADER_5")


async def _fetch_historical_trade_ticks(
    cfg: HomologationConfig,
    sym: str,
    *,
    limit: int,
    lookback_days: int,
) -> list:
    sym_cfg = HomologationConfig(
        host=cfg.host,
        port=cfg.port,
        account_number=cfg.account_number,
        broker=cfg.broker,
        symbol=sym,
        venue_profile_name=cfg.venue_profile_name,
        enable_execution=cfg.enable_execution,
        min_quote_ticks=cfg.min_quote_ticks,
        scenario_timeout_secs=cfg.scenario_timeout_secs,
        stream_duration_secs=cfg.stream_duration_secs,
        stream_max_gap_secs=cfg.stream_max_gap_secs,
        stream_min_ticks=cfg.stream_min_ticks,
        skip_stream=cfg.skip_stream,
        feed_enabled=cfg.feed_enabled,
        feed_host=cfg.feed_host,
        feed_port=cfg.feed_port,
        feed_path=cfg.feed_path,
        feed_hello_timeout_secs=cfg.feed_hello_timeout_secs,
    )
    delivered: list = []
    data_client = None

    def _capture(_instrument_id, ticks, _correlation_id):
        delivered.extend(ticks)

    reset_mt5_client_cache()
    try:
        data_client, _, cache, clock = await _make_data_client(sym_cfg)
        await data_client._connect()
        iid = _instrument_id(sym)
        if cache.instrument(iid) is None:
            raise RuntimeError(f"{sym}: instrument not in cache")
        data_client._handle_trade_ticks = _capture
        req = RequestTradeTicks(
            instrument_id=iid,
            start=pd.Timestamp.utcnow() - timedelta(days=lookback_days),
            end=None,
            limit=limit,
            client_id=data_client.id,
            venue=_VENUE,
            callback=None,
            request_id=UUID4(),
            ts_init=clock.timestamp_ns(),
            params=None,
        )
        await data_client._request_trade_ticks(req)
        return delivered
    finally:
        if data_client is not None:
            await data_client._disconnect()
        reset_mt5_client_cache()
        await asyncio.sleep(0.3)


def _summarize_aggressor(ticks: list) -> tuple[int, int, int, float]:
    sides = Counter(t.aggressor_side for t in ticks)
    buyers = sides.get(AggressorSide.BUYER, 0)
    sellers = sides.get(AggressorSide.SELLER, 0)
    no_agg = sides.get(AggressorSide.NO_AGGRESSOR, 0)
    coverage = (buyers + sellers) / len(ticks) if ticks else 0.0
    return buyers, sellers, no_agg, coverage


class _AggressorStreamConfig(StrategyConfig, frozen=True):
    instrument_id: object
    duration_secs: float
    min_ticks: int


class _AggressorStreamStrategy(Strategy):
    def __init__(
        self,
        config: _AggressorStreamConfig,
        done: threading.Event,
        outcome: dict,
        stop_node: Callable[[], None],
    ) -> None:
        super().__init__(config)
        self._done = done
        self._outcome = outcome
        self._stop_node = stop_node
        self.tick_count = 0
        self._timer: threading.Timer | None = None

    def on_start(self) -> None:
        if self.cache.instrument(self.config.instrument_id) is None:
            self._fail("Instrument not in cache")
            return
        self.subscribe_trade_ticks(instrument_id=self.config.instrument_id)
        self._timer = threading.Timer(self.config.duration_secs, self._finish)
        self._timer.daemon = True
        self._timer.start()

    def on_trade_tick(self, tick: TradeTick) -> None:
        self.tick_count += 1
        sides: Counter = self._outcome.setdefault("aggressor", Counter())
        sides[tick.aggressor_side] += 1
        if self.tick_count <= 3 or self.tick_count % 10 == 0:
            self.log.info(
                f"TradeTick #{self.tick_count}: price={tick.price} aggressor={tick.aggressor_side}",
            )

    def on_stop(self) -> None:
        if self._timer is not None:
            self._timer.cancel()

    def _finish(self) -> None:
        min_ticks = self.config.min_ticks
        sides: Counter = self._outcome.get("aggressor", Counter())
        hinted = sides.get(AggressorSide.BUYER, 0) + sides.get(AggressorSide.SELLER, 0)
        if self.tick_count >= min_ticks and hinted > 0:
            self._outcome["ok"] = True
            self._outcome["detail"] = (
                f"ticks={self.tick_count} BUYER={sides.get(AggressorSide.BUYER, 0)} "
                f"SELLER={sides.get(AggressorSide.SELLER, 0)} "
                f"NO_AGGRESSOR={sides.get(AggressorSide.NO_AGGRESSOR, 0)}"
            )
        elif self.tick_count >= min_ticks:
            self._outcome["ok"] = False
            self._outcome["detail"] = f"ticks={self.tick_count} but all NO_AGGRESSOR"
        else:
            self._outcome["ok"] = False
            self._outcome["detail"] = f"only {self.tick_count} ticks (min {min_ticks})"
        self._done.set()
        self._stop_node()
        self.stop()

    def _fail(self, detail: str) -> None:
        self._outcome["ok"] = False
        self._outcome["detail"] = detail
        self._done.set()
        self.stop()


async def _run_live_feed_smoke(cfg: HomologationConfig, sym: str) -> tuple[bool, str]:
    if not cfg.feed_enabled:
        return False, "feed disabled (set MT5_FEED_ENABLED=1)"

    tick = probe_symbol_tick(cfg.host, cfg.port, sym)
    if tick is None:
        return False, f"{sym}: no live tick (market closed?)"

    duration = float(os.environ.get("HOMOLOG_AGGRESSOR_STREAM_SECS", "45"))
    min_ticks = int(os.environ.get("HOMOLOG_AGGRESSOR_MIN_TICKS", "5"))
    done = threading.Event()
    outcome: dict = {"ok": False, "detail": ""}
    stop_gate_holder: list[NodeStopGate | None] = [None]

    def _build():
        node = build_trading_node(cfg, trader_id="HOMOLOG-AGG", symbols=[sym])
        strat = _AggressorStreamStrategy(
            config=_AggressorStreamConfig(
                strategy_id=f"HOMOLOG-AGG-{sym}",
                instrument_id=instrument_id(sym),
                duration_secs=duration,
                min_ticks=min_ticks,
            ),
            done=done,
            outcome=outcome,
            stop_node=lambda: (
                stop_gate_holder[0].request_stop() if stop_gate_holder[0] else None
            ),
        )
        node.trader.add_strategy(strat)
        return node

    reset_mt5_client_cache()
    try:
        await run_node_until(_build, done, duration + 90.0, stop_gate_holder)
    except TimeoutError:
        return False, f"timeout after {duration + 90:.0f}s"
    except Exception as exc:
        return False, str(exc)

    return bool(outcome.get("ok")), str(outcome.get("detail", "unknown"))


async def main() -> int:
    cfg = HomologationConfig.from_env()
    if cfg.venue_profile.name != "xp-b3":
        print("SKIP: aggressor smoke requires MT5_VENUE_PROFILE=xp_b3")
        return 0

    limit = int(os.environ.get("HOMOLOG_AGGRESSOR_LIMIT", "100"))
    lookback = int(os.environ.get("HOMOLOG_TRADE_LOOKBACK_DAYS", "7"))
    symbols = _trade_symbols(cfg)
    exit_code = 0

    print("=" * 64)
    print("  XP AGGRESSOR SMOKE")
    print(f"  Gateway : {cfg.host}:{cfg.port}")
    print(f"  Feed    : {'ON' if cfg.feed_enabled else 'OFF'} ({cfg.feed_host}:{cfg.feed_port})")
    print(f"  Symbols : {','.join(symbols)}")
    print("=" * 64)

    print("\n--- D31 historical (RequestTradeTicks) ---")
    for sym in symbols:
        try:
            ticks = await _fetch_historical_trade_ticks(
                cfg, sym, limit=limit, lookback_days=lookback,
            )
        except Exception as exc:
            print(f"  {sym}: FAIL — {exc}")
            exit_code = 1
            continue

        if not ticks:
            print(f"  {sym}: FAIL — no TradeTicks")
            exit_code = 1
            continue

        buyers, sellers, no_agg, coverage = _summarize_aggressor(ticks)
        print(f"  {sym}: {len(ticks)} ticks  BUYER={buyers} SELLER={sellers} NO_AG={no_agg} ({coverage:.1%})")
        if buyers + sellers == 0:
            print(f"  {sym}: FAIL — historical all NO_AGGRESSOR")
            exit_code = 1
        else:
            print(f"  {sym}: PASS — historical aggressor")

    print("\n--- D30 live (SubscribeTradeTicks + WS feed) ---")
    for sym in symbols:
        ok, detail = await _run_live_feed_smoke(cfg, sym)
        if ok:
            print(f"  {sym}: PASS — {detail}")
        else:
            print(f"  {sym}: FAIL — {detail}")
            if cfg.feed_enabled:
                exit_code = 1

    print()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
