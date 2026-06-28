"""
TC-HOM-D07: Multi-symbol WS quote streaming (BTCUSD + USTEC).

Subscribes to quote ticks for each configured symbol and waits for at least one
tick per symbol within the scenario timeout.
"""
from __future__ import annotations

import threading
from collections.abc import Callable

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.trading.strategy import Strategy

from homologation.config import HomologationConfig, probe_symbol_tick
from homologation.node_factory import build_trading_node, instrument_id
from homologation.report import HomologationReport, ScenarioStatus
from homologation.scenarios.node_runner import NodeStopGate, run_node_until


class _MultiSymbolConfig(StrategyConfig, frozen=True):
    instrument_ids: tuple
    wait_secs: float
    min_ticks_per_symbol: int


class _MultiSymbolStrategy(Strategy):
    def __init__(
        self,
        config: _MultiSymbolConfig,
        done: threading.Event,
        outcome: dict,
        stop_node: Callable[[], None],
    ) -> None:
        super().__init__(config)
        self._done = done
        self._outcome = outcome
        self._stop_node = stop_node
        self.tick_counts: dict[str, int] = {str(iid): 0 for iid in config.instrument_ids}
        self._timer: threading.Timer | None = None

    def on_start(self) -> None:
        missing = []
        for iid in self.config.instrument_ids:
            if self.cache.instrument(iid) is None:
                missing.append(str(iid))
            else:
                self.subscribe_quote_ticks(instrument_id=iid)
        if missing:
            self._fail(f"Instruments not in cache: {', '.join(missing)}")
            return

        self._timer = threading.Timer(self.config.wait_secs, self._on_timeout)
        self._timer.daemon = True
        self._timer.start()

    def on_quote_tick(self, tick: QuoteTick) -> None:
        key = str(tick.instrument_id)
        self.tick_counts[key] = self.tick_counts.get(key, 0) + 1
        if all(
            self.tick_counts.get(str(iid), 0) >= self.config.min_ticks_per_symbol
            for iid in self.config.instrument_ids
        ):
            self._finish_ok()

    def on_stop(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
        for iid in self.config.instrument_ids:
            self.unsubscribe_quote_ticks(instrument_id=iid)
        self._stop_node()

    def _on_timeout(self) -> None:
        if self._done.is_set():
            return
        parts = [f"{k}={v}" for k, v in self.tick_counts.items()]
        self._fail(f"Timeout waiting for all symbols: {', '.join(parts)}")

    def _finish_ok(self) -> None:
        self._outcome["completed"] = True
        self._done.set()
        self.stop()

    def _fail(self, detail: str) -> None:
        self._outcome["completed"] = False
        self._outcome["detail"] = detail
        self._done.set()
        self.stop()


async def run_multi_symbol_stream(cfg: HomologationConfig, report: HomologationReport) -> None:
    """TC-HOM-D07: concurrent quote ticks for multiple symbols via WS feed."""
    case_id = "TC-HOM-D07"
    name = "Multi-symbol WS quote stream"

    if not cfg.feed_enabled:
        report.add(
            case_id,
            name,
            ScenarioStatus.SKIP,
            "Set MT5_FEED_ENABLED=1 and start NT5TickFeedService",
        )
        return

    symbols = list(cfg.multi_symbols)
    inactive: list[str] = []
    for sym in symbols:
        tick = probe_symbol_tick(cfg.host, cfg.port, sym)
        if tick is None or (tick[0] <= 0.0 and tick[1] <= 0.0):
            inactive.append(sym)

    if inactive:
        report.add(
            case_id,
            name,
            ScenarioStatus.SKIP,
            f"No live quote for symbol(s): {', '.join(inactive)} (session closed?)",
            symbols=symbols,
            inactive=inactive,
        )
        return

    inst_ids = tuple(instrument_id(sym) for sym in symbols)
    wait_secs = min(cfg.scenario_timeout_secs, 90.0)
    done = threading.Event()
    outcome: dict = {"completed": False, "detail": ""}
    stop_gate_holder: list[NodeStopGate | None] = [None]
    strategy_holder: list[_MultiSymbolStrategy | None] = [None]

    def _build_node():
        node = build_trading_node(cfg, trader_id="HOMOLOG-MULTI", symbols=symbols)
        strategy = _MultiSymbolStrategy(
            _MultiSymbolConfig(
                strategy_id="HOMOLOG-MULTI",
                instrument_ids=inst_ids,
                wait_secs=wait_secs,
                min_ticks_per_symbol=1,
            ),
            done=done,
            outcome=outcome,
            stop_node=lambda: stop_gate_holder[0].request_stop() if stop_gate_holder[0] else None,
        )
        strategy_holder[0] = strategy
        node.trader.add_strategy(strategy)
        return node

    try:
        await run_node_until(_build_node, done, wait_secs + 60.0, stop_gate_holder)
    except TimeoutError:
        strategy = strategy_holder[0]
        counts = strategy.tick_counts if strategy is not None else {}
        report.add(
            case_id,
            name,
            ScenarioStatus.FAIL,
            f"Node timeout; tick counts={counts}",
            symbols=symbols,
        )
        return
    except Exception as exc:
        report.add(case_id, name, ScenarioStatus.FAIL, str(exc))
        return

    strategy = strategy_holder[0]
    if outcome.get("detail"):
        report.add(case_id, name, ScenarioStatus.FAIL, outcome["detail"], symbols=symbols)
        return

    counts = strategy.tick_counts if strategy is not None else {}
    report.add(
        case_id,
        name,
        ScenarioStatus.PASS,
        "; ".join(f"{sym}={counts.get(str(instrument_id(sym)), 0)}" for sym in symbols),
        symbols=symbols,
        tick_counts=counts,
        transport="ws_feed",
    )
