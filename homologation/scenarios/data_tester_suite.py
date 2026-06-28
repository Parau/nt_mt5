"""
TC-HOM-D03 + TC-HOM-D05: Live bar subscribe and unsubscribe-on-stop.

Bar streaming still uses IB-style bridge hooks (``req_real_time_bars`` /
``cancel_historical_data``). When the EXTERNAL_RPYC gateway does not expose
those methods, D03/D05 (bars) fail with an explicit bridge-gap message.
Quote-tick unsubscribe on stop (WS feed path) is exercised in D05 regardless.
"""
from __future__ import annotations

import threading
from collections.abc import Callable

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarAggregation, BarSpecification, BarType, QuoteTick
from nautilus_trader.model.enums import AggregationSource, PriceType
from nautilus_trader.trading.strategy import Strategy

from homologation.config import HomologationConfig
from homologation.node_factory import build_trading_node, instrument_id
from homologation.report import HomologationReport, ScenarioStatus
from homologation.scenarios.node_runner import NodeStopGate, run_node_until
from homologation.support.bridge_probe import bridge_bar_stream_ready


def _m1_bar_type(symbol: str):
    inst_id = instrument_id(symbol)
    spec = BarSpecification(1, BarAggregation.MINUTE, PriceType.LAST)
    return BarType(inst_id, spec, AggregationSource.EXTERNAL)


class _BarSubscribeConfig(StrategyConfig, frozen=True):
    instrument_id: object
    bar_type: object
    min_bars: int
    wait_secs: float


class _BarSubscribeStrategy(Strategy):
    def __init__(
        self,
        config: _BarSubscribeConfig,
        done: threading.Event,
        outcome: dict,
        stop_node: Callable[[], None],
    ) -> None:
        super().__init__(config)
        self._done = done
        self._outcome = outcome
        self._stop_node = stop_node
        self.bar_count = 0
        self._timer: threading.Timer | None = None

    def on_start(self) -> None:
        if self.cache.instrument(self.config.instrument_id) is None:
            self._fail("Instrument not in cache")
            return
        self.subscribe_bars(self.config.bar_type)
        self._timer = threading.Timer(self.config.wait_secs, self._on_timeout)
        self._timer.daemon = True
        self._timer.start()

    def on_bar(self, bar: Bar) -> None:
        self.bar_count += 1
        self.log.info(f"M1 bar #{self.bar_count} close={float(bar.close)}")
        if self.bar_count >= self.config.min_bars:
            self._finish_ok()

    def on_stop(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
        self.unsubscribe_bars(self.config.bar_type)
        self._stop_node()

    def _on_timeout(self) -> None:
        if self._done.is_set():
            return
        self._fail(
            f"Timeout: only {self.bar_count}/{self.config.min_bars} M1 bars "
            f"in {self.config.wait_secs:.0f}s",
        )

    def _finish_ok(self) -> None:
        self._outcome["completed"] = True
        self._done.set()
        self.stop()

    def _fail(self, detail: str) -> None:
        self._outcome["completed"] = False
        self._outcome["detail"] = detail
        self._done.set()
        self.stop()


class _UnsubscribeConfig(StrategyConfig, frozen=True):
    instrument_id: object
    bar_type: object
    min_ticks: int
    test_bars: bool


class _UnsubscribeStrategy(Strategy):
    def __init__(
        self,
        config: _UnsubscribeConfig,
        done: threading.Event,
        outcome: dict,
        stop_node: Callable[[], None],
    ) -> None:
        super().__init__(config)
        self._done = done
        self._outcome = outcome
        self._stop_node = stop_node
        self.tick_count = 0
        self.bar_count = 0
        self._unsubscribed_quotes = False
        self._unsubscribed_bars = False

    def on_start(self) -> None:
        if self.cache.instrument(self.config.instrument_id) is None:
            self._fail("Instrument not in cache")
            return
        self.subscribe_quote_ticks(instrument_id=self.config.instrument_id)
        if self.config.test_bars:
            self.subscribe_bars(self.config.bar_type)

    def on_quote_tick(self, tick: QuoteTick) -> None:
        self.tick_count += 1
        if self.tick_count >= self.config.min_ticks:
            self._finish_ok()

    def on_bar(self, bar: Bar) -> None:
        self.bar_count += 1

    def on_stop(self) -> None:
        self.unsubscribe_quote_ticks(instrument_id=self.config.instrument_id)
        self._unsubscribed_quotes = True
        if self.config.test_bars:
            self.unsubscribe_bars(self.config.bar_type)
            self._unsubscribed_bars = True
        self._outcome["unsubscribed_quotes"] = self._unsubscribed_quotes
        self._outcome["unsubscribed_bars"] = self._unsubscribed_bars
        self._stop_node()

    def _finish_ok(self) -> None:
        self._outcome["completed"] = True
        self._done.set()
        self.stop()

    def _fail(self, detail: str) -> None:
        self._outcome["completed"] = False
        self._outcome["detail"] = detail
        self._done.set()
        self.stop()


async def run_bar_subscribe(cfg: HomologationConfig, report: HomologationReport) -> None:
    """TC-HOM-D03: live M1 bar subscribe via TradingNode."""
    case_id = "TC-HOM-D03"
    name = "Live bar subscribe M1"

    ready, reason = bridge_bar_stream_ready(cfg.host, cfg.port)
    if not ready:
        report.add(
            case_id,
            name,
            ScenarioStatus.FAIL,
            f"{reason} — native ``copy_rates_from_pos`` works; bar subscribe path blocked",
        )
        return

    done = threading.Event()
    outcome: dict = {"completed": False, "detail": ""}
    stop_gate_holder: list[NodeStopGate | None] = [None]
    strategy_holder: list[_BarSubscribeStrategy | None] = [None]
    inst_id = instrument_id(cfg.symbol)
    bar_type = _m1_bar_type(cfg.symbol)
    wait_secs = min(cfg.scenario_timeout_secs, 180.0)

    def _build_node():
        node = build_trading_node(cfg, trader_id="HOMOLOG-D03")
        strategy = _BarSubscribeStrategy(
            _BarSubscribeConfig(
                strategy_id="HOMOLOG-D03",
                instrument_id=inst_id,
                bar_type=bar_type,
                min_bars=1,
                wait_secs=wait_secs,
            ),
            done=done,
            outcome=outcome,
            stop_node=lambda: stop_gate_holder[0].request_stop() if stop_gate_holder[0] else None,
        )
        strategy_holder[0] = strategy
        node.trader.add_strategy(strategy)
        return node

    try:
        await run_node_until(_build_node, done, wait_secs + 45.0, stop_gate_holder)
    except Exception as exc:
        report.add(case_id, name, ScenarioStatus.FAIL, str(exc))
        return

    strategy = strategy_holder[0]
    bars = strategy.bar_count if strategy is not None else 0

    if outcome.get("completed") and bars >= 1:
        report.add(case_id, name, ScenarioStatus.PASS, f"Received {bars} M1 bar(s)", bars=bars)
    else:
        report.add(
            case_id,
            name,
            ScenarioStatus.FAIL,
            outcome.get("detail") or f"Only {bars} bar(s)",
            bars=bars,
        )


async def run_unsubscribe_on_stop(cfg: HomologationConfig, report: HomologationReport) -> None:
    """TC-HOM-D05: unsubscribe quote ticks (and bars when bridge supports them) on stop."""
    case_id = "TC-HOM-D05"
    name = "Unsubscribe on stop (quotes/bars)"

    if not cfg.feed_enabled:
        report.add(
            case_id,
            name,
            ScenarioStatus.SKIP,
            "Set MT5_FEED_ENABLED=1 for WS quote unsubscribe validation",
        )
        return

    bar_ready, bar_reason = bridge_bar_stream_ready(cfg.host, cfg.port)
    done = threading.Event()
    outcome: dict = {"completed": False, "detail": ""}
    stop_gate_holder: list[NodeStopGate | None] = [None]
    strategy_holder: list[_UnsubscribeStrategy | None] = [None]
    inst_id = instrument_id(cfg.symbol)
    bar_type = _m1_bar_type(cfg.symbol)

    def _build_node():
        node = build_trading_node(cfg, trader_id="HOMOLOG-D05")
        strategy = _UnsubscribeStrategy(
            _UnsubscribeConfig(
                strategy_id="HOMOLOG-D05",
                instrument_id=inst_id,
                bar_type=bar_type,
                min_ticks=max(2, cfg.min_quote_ticks),
                test_bars=bar_ready,
            ),
            done=done,
            outcome=outcome,
            stop_node=lambda: stop_gate_holder[0].request_stop() if stop_gate_holder[0] else None,
        )
        strategy_holder[0] = strategy
        node.trader.add_strategy(strategy)
        return node

    try:
        await run_node_until(_build_node, done, cfg.scenario_timeout_secs, stop_gate_holder)
    except TimeoutError:
        ticks = strategy_holder[0].tick_count if strategy_holder[0] else 0
        report.add(case_id, name, ScenarioStatus.FAIL, f"Timeout — ticks={ticks}")
        return
    except Exception as exc:
        report.add(case_id, name, ScenarioStatus.FAIL, str(exc))
        return

    strategy = strategy_holder[0]
    ticks = strategy.tick_count if strategy is not None else 0
    quotes_ok = outcome.get("unsubscribed_quotes", False)
    bars_ok = outcome.get("unsubscribed_bars", False) if bar_ready else None

    if not outcome.get("completed") or ticks < cfg.min_quote_ticks:
        report.add(
            case_id,
            name,
            ScenarioStatus.FAIL,
            outcome.get("detail") or f"Only {ticks} quote ticks",
            ticks=ticks,
        )
        return

    if not quotes_ok:
        report.add(case_id, name, ScenarioStatus.FAIL, "on_stop did not unsubscribe quote ticks")
        return

    if bar_ready and not bars_ok:
        report.add(case_id, name, ScenarioStatus.FAIL, "on_stop did not unsubscribe bars")
        return

    bar_note = "bars=OK" if bar_ready else f"bars=SKIP ({bar_reason})"
    report.add(
        case_id,
        name,
        ScenarioStatus.PASS,
        f"quotes unsubscribed on stop ({ticks} ticks); {bar_note}",
        ticks=ticks,
        bar_stream_ready=bar_ready,
    )
