"""
TC-HOM-D02: Sustained quote tick streaming (WS feed).

Subscribes to live quote ticks via the MQL5 Service → InboundFeedGateway path
(``feed.enabled=True``). Validates tick-a-tick delivery without long silent gaps.

Requires ``MT5_FEED_ENABLED=1`` and ``NT5TickFeedService`` running in MT5.
Legacy RPyC ``symbol_info_tick`` polling is not validated by this scenario.
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.trading.strategy import Strategy

from homologation.config import HomologationConfig
from homologation.node_factory import build_trading_node, instrument_id
from homologation.report import HomologationReport, ScenarioStatus
from homologation.scenarios.node_runner import NodeStopGate, run_node_until


class _StreamConfig(StrategyConfig, frozen=True):
    instrument_id: object
    duration_secs: float
    max_gap_secs: float
    min_ticks: int


class _StreamStrategy(Strategy):
    def __init__(
        self,
        config: _StreamConfig,
        done: threading.Event,
        outcome: dict,
        stop_node: Callable[[], None],
    ) -> None:
        super().__init__(config)
        self._done = done
        self._outcome = outcome
        self._stop_node = stop_node
        self.tick_count = 0
        self.max_gap_secs = 0.0
        self._last_tick_mono = 0.0
        self._gap_watch_stop = threading.Event()
        self._gap_watch_thread: threading.Thread | None = None
        self._duration_timer: threading.Timer | None = None

    def on_start(self) -> None:
        instrument = self.cache.instrument(self.config.instrument_id)
        if instrument is None:
            self._fail("Instrument not in cache")
            return

        self.subscribe_quote_ticks(instrument_id=self.config.instrument_id)

        self._duration_timer = threading.Timer(self.config.duration_secs, self._finish_ok)
        self._duration_timer.daemon = True
        self._duration_timer.start()

        self._gap_watch_thread = threading.Thread(
            target=self._watch_gaps,
            daemon=True,
            name="homolog-gap-watch",
        )
        self._gap_watch_thread.start()

    def on_quote_tick(self, tick: QuoteTick) -> None:
        now = time.monotonic()
        if self._last_tick_mono > 0.0:
            gap = now - self._last_tick_mono
            self.max_gap_secs = max(self.max_gap_secs, gap)
        self._last_tick_mono = now
        self.tick_count += 1

        if self.tick_count == 1 or self.tick_count % 10 == 0:
            self.log.info(
                f"Stream tick #{self.tick_count}: "
                f"bid={float(tick.bid_price)} ask={float(tick.ask_price)}"
            )

    def on_stop(self) -> None:
        self._gap_watch_stop.set()
        if self._duration_timer is not None:
            self._duration_timer.cancel()
        self.unsubscribe_quote_ticks(instrument_id=self.config.instrument_id)
        self._stop_node()

    def _watch_gaps(self) -> None:
        poll_secs = min(2.0, max(0.5, self.config.max_gap_secs / 4.0))
        while not self._gap_watch_stop.wait(poll_secs):
            if self._last_tick_mono <= 0.0:
                continue
            gap = time.monotonic() - self._last_tick_mono
            if gap > self.config.max_gap_secs:
                self._fail(
                    f"Stream stalled: no tick for {gap:.1f}s "
                    f"(max {self.config.max_gap_secs}s)"
                )
                return

    def _finish_ok(self) -> None:
        self._outcome["completed"] = True
        self._done.set()
        self.stop()

    def _fail(self, detail: str) -> None:
        self._outcome["completed"] = False
        self._outcome["detail"] = detail
        self._done.set()
        self.stop()


async def run_tick_stream(cfg: HomologationConfig, report: HomologationReport) -> None:
    """Run TC-HOM-D02 sustained quote tick streaming."""
    case_id = "TC-HOM-D02"
    name = "Sustained quote tick stream"

    if cfg.skip_stream:
        report.add(
            case_id,
            name,
            ScenarioStatus.SKIP,
            "Set HOMOLOG_SKIP_STREAM=0 to run streaming scenario",
        )
        return

    if not cfg.feed_enabled:
        report.add(
            case_id,
            name,
            ScenarioStatus.SKIP,
            "Set MT5_FEED_ENABLED=1 and start NT5TickFeedService for WS stream validation",
        )
        return

    done = threading.Event()
    outcome: dict = {"completed": False, "detail": ""}
    stop_gate_holder: list[NodeStopGate | None] = [None]
    strategy_holder: list[_StreamStrategy | None] = [None]
    inst_id = instrument_id(cfg.symbol)

    def _build_node():
        node = build_trading_node(cfg, trader_id="HOMOLOG-STREAM")
        strategy = _StreamStrategy(
            _StreamConfig(
                strategy_id="HOMOLOG-STREAM",
                instrument_id=inst_id,
                duration_secs=cfg.stream_duration_secs,
                max_gap_secs=cfg.stream_max_gap_secs,
                min_ticks=cfg.stream_min_ticks,
            ),
            done=done,
            outcome=outcome,
            stop_node=lambda: stop_gate_holder[0].request_stop() if stop_gate_holder[0] else None,
        )
        strategy_holder[0] = strategy
        node.trader.add_strategy(strategy)
        return node

    node_timeout = cfg.stream_duration_secs + 60.0

    try:
        await run_node_until(_build_node, done, node_timeout, stop_gate_holder)
    except TimeoutError:
        strategy = strategy_holder[0]
        ticks = strategy.tick_count if strategy is not None else 0
        report.add(
            case_id,
            name,
            ScenarioStatus.FAIL,
            f"Node timeout after {node_timeout:.0f}s — ticks={ticks}",
            ticks=ticks,
        )
        return
    except Exception as exc:
        report.add(case_id, name, ScenarioStatus.FAIL, str(exc))
        return

    strategy = strategy_holder[0]
    ticks = strategy.tick_count if strategy is not None else 0
    max_gap = strategy.max_gap_secs if strategy is not None else 0.0

    if outcome.get("detail"):
        report.add(
            case_id,
            name,
            ScenarioStatus.FAIL,
            outcome["detail"],
            ticks=ticks,
            max_gap_secs=max_gap,
        )
        return

    if ticks < cfg.stream_min_ticks:
        report.add(
            case_id,
            name,
            ScenarioStatus.FAIL,
            f"Only {ticks}/{cfg.stream_min_ticks} ticks in {cfg.stream_duration_secs:.0f}s",
            ticks=ticks,
            max_gap_secs=max_gap,
        )
        return

    feed_uri = f"ws://{cfg.feed_host}:{cfg.feed_port}{cfg.feed_path}"
    report.add(
        case_id,
        name,
        ScenarioStatus.PASS,
        (
            f"{ticks} ticks in {cfg.stream_duration_secs:.0f}s "
            f"(max inter-tick gap {max_gap:.1f}s, transport=ws_feed)"
        ),
        ticks=ticks,
        max_gap_secs=max_gap,
        duration_secs=cfg.stream_duration_secs,
        transport="ws_feed",
        feed_uri=feed_uri,
    )
