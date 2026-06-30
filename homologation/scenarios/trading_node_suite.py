"""
TC-HOM-D01 + TC-HOM-E01: Combined TradingNode session.

Runs quote-tick validation and (optionally) market round-trip on a single
TradingNode to avoid repeated MT5 initialize/shutdown cycles on the bridge.
"""
from __future__ import annotations

import threading
from enum import Enum, auto

from collections.abc import Callable

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.events import OrderDenied, OrderFilled, OrderRejected
from nautilus_trader.model.identifiers import ClientOrderId
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy

from homologation.config import HomologationConfig
from homologation.node_factory import build_trading_node, instrument_id
from homologation.report import HomologationReport, ScenarioStatus
from homologation.scenarios.node_runner import NodeStopGate, run_node_until, stop_node_from_strategy
from homologation.support.order_specs import homolog_order_qty_str


class _Phase(Enum):
    QUOTE_TICKS = auto()
    MARKET_BUY = auto()
    MARKET_SELL = auto()
    DONE = auto()
    ABORTED = auto()


class _SuiteConfig(StrategyConfig, frozen=True):
    instrument_id: object
    min_ticks: int
    enable_execution: bool
    order_quantity: str


class _SuiteStrategy(Strategy):
    def __init__(
        self,
        config: _SuiteConfig,
        done: threading.Event,
        outcome: dict,
        stop_node: Callable[[], None],
    ) -> None:
        super().__init__(config)
        self._done = done
        self._outcome = outcome
        self._stop_node = stop_node
        self._phase = _Phase.QUOTE_TICKS
        self.tick_count = 0
        self.last_bid: float | None = None
        self.last_ask: float | None = None
        self._buy_order_id: ClientOrderId | None = None
        self._sell_order_id: ClientOrderId | None = None
        self._buy_fill_px = 0.0
        self._buy_fill_qty = 0.0
        self._buy_qty: Quantity | None = None
        self._sell_fill_px = 0.0

    def on_start(self) -> None:
        instrument = self.cache.instrument(self.config.instrument_id)
        if instrument is None:
            self._fail("d01", "Instrument not in cache")
            return
        self.subscribe_quote_ticks(instrument_id=self.config.instrument_id)

    def on_quote_tick(self, tick: QuoteTick) -> None:
        if self._phase is not _Phase.QUOTE_TICKS:
            return

        self.tick_count += 1
        self.last_bid = float(tick.bid_price)
        self.last_ask = float(tick.ask_price)
        self.log.info(f"QuoteTick #{self.tick_count}: bid={self.last_bid} ask={self.last_ask}")

        if self.tick_count < self.config.min_ticks:
            return

        self._outcome["d01_ok"] = True
        if not self.config.enable_execution:
            self._finish_all()
            return

        self._phase = _Phase.MARKET_BUY
        self._submit_buy()

    def on_order_rejected(self, event: OrderRejected) -> None:
        self._phase = _Phase.ABORTED
        self._fail("e01", f"Order rejected: {event.reason}")

    def on_order_denied(self, event: OrderDenied) -> None:
        self._phase = _Phase.ABORTED
        self._fail("e01", f"Order denied: {event.reason}")

    def on_order_filled(self, event: OrderFilled) -> None:
        if event.client_order_id == self._buy_order_id:
            self._buy_fill_px = float(event.last_px)
            self._buy_fill_qty = float(event.last_qty)
            self._submit_sell()
        elif event.client_order_id == self._sell_order_id:
            self._sell_fill_px = float(event.last_px)
            self._outcome["e01_ok"] = True
            self._outcome["e01_detail"] = (
                f"BUY {self._buy_fill_qty}@{self._buy_fill_px:.2f} → "
                f"SELL @{self._sell_fill_px:.2f}"
            )
            self._finish_all()

    def on_stop(self) -> None:
        self.unsubscribe_quote_ticks(instrument_id=self.config.instrument_id)
        self._stop_node()

    def _min_quantity(self) -> Quantity:
        instrument = self.cache.instrument(self.config.instrument_id)
        if instrument and instrument.min_quantity:
            return instrument.min_quantity
        return Quantity.from_str(self.config.order_quantity)

    def _submit_buy(self) -> None:
        qty = self._min_quantity()
        self._buy_qty = qty
        order = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=OrderSide.BUY,
            quantity=qty,
            time_in_force=TimeInForce.IOC,
        )
        self._buy_order_id = order.client_order_id
        self.submit_order(order)
        self.log.info(f"Submitted BUY {qty}")

    def _submit_sell(self) -> None:
        self._phase = _Phase.MARKET_SELL
        if self._buy_qty is not None:
            qty = self._buy_qty
        else:
            instrument = self.cache.instrument(self.config.instrument_id)
            if instrument is not None:
                qty = instrument.make_qty(self._buy_fill_qty)
            else:
                qty = Quantity.from_int(int(self._buy_fill_qty))
        order = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=OrderSide.SELL,
            quantity=qty,
            time_in_force=TimeInForce.IOC,
        )
        self._sell_order_id = order.client_order_id
        self.submit_order(order)
        self.log.info(f"Submitted SELL {qty}")

    def _fail(self, key: str, detail: str) -> None:
        self._outcome[f"{key}_ok"] = False
        self._outcome[f"{key}_detail"] = detail
        self._done.set()
        self.stop()

    def _finish_all(self) -> None:
        self._phase = _Phase.DONE
        self._done.set()
        self.stop()


async def run_trading_node_suite(cfg: HomologationConfig, report: HomologationReport) -> None:
    """Run D01 (+ E01 when enabled) on one TradingNode session."""
    done = threading.Event()
    outcome: dict = {
        "d01_ok": False,
        "d01_detail": "",
        "e01_ok": False,
        "e01_detail": "",
    }
    stop_gate_holder: list[NodeStopGate | None] = [None]
    strategy_holder: list[_SuiteStrategy | None] = [None]
    inst_id = instrument_id(cfg.symbol)

    def _build_node():
        node = build_trading_node(cfg, trader_id="HOMOLOG-SUITE")
        strategy = _SuiteStrategy(
            _SuiteConfig(
                strategy_id="HOMOLOG-SUITE",
                instrument_id=inst_id,
                min_ticks=cfg.min_quote_ticks,
                enable_execution=cfg.enable_execution,
                order_quantity=homolog_order_qty_str(cfg),
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
        strategy = strategy_holder[0]
        tick_count = strategy.tick_count if strategy is not None else 0
        d01_passed = outcome.get("d01_ok") or tick_count >= cfg.min_quote_ticks
        if d01_passed:
            last_bid = strategy.last_bid if strategy is not None else None
            last_ask = strategy.last_ask if strategy is not None else None
            report.add(
                "TC-HOM-D01",
                "Quote ticks via TradingNode",
                ScenarioStatus.PASS,
                f"Received {tick_count} ticks (last bid={last_bid} ask={last_ask})",
                ticks=tick_count,
            )
        else:
            report.add(
                "TC-HOM-D01",
                "Quote ticks via TradingNode",
                ScenarioStatus.FAIL,
                f"Timeout after {cfg.scenario_timeout_secs}s — ticks={tick_count}",
            )
        if cfg.enable_execution:
            report.add(
                "TC-HOM-E01",
                "Market round-trip (BUY → SELL)",
                ScenarioStatus.FAIL,
                outcome.get("e01_detail") or "Suite timed out before round-trip completed",
            )
        return
    except Exception as exc:
        report.add(
            "TC-HOM-D01",
            "Quote ticks via TradingNode",
            ScenarioStatus.FAIL,
            str(exc),
        )
        return

    strategy = strategy_holder[0]

    # --- D01 result ---
    if outcome.get("d01_ok") or (strategy is not None and strategy.tick_count >= cfg.min_quote_ticks):
        tick_count = strategy.tick_count if strategy is not None else outcome.get("tick_count", 0)
        last_bid = strategy.last_bid if strategy is not None else None
        last_ask = strategy.last_ask if strategy is not None else None
        report.add(
            "TC-HOM-D01",
            "Quote ticks via TradingNode",
            ScenarioStatus.PASS,
            f"Received {tick_count} ticks (last bid={last_bid} ask={last_ask})",
            ticks=tick_count,
        )
    else:
        tick_count = strategy.tick_count if strategy is not None else 0
        report.add(
            "TC-HOM-D01",
            "Quote ticks via TradingNode",
            ScenarioStatus.FAIL,
            outcome.get("d01_detail") or f"Only {tick_count}/{cfg.min_quote_ticks} ticks",
        )

    # --- E01 result ---
    if not cfg.enable_execution:
        report.add(
            "TC-HOM-E01",
            "Market round-trip (BUY → SELL)",
            ScenarioStatus.SKIP,
            "Set MT5_ENABLE_LIVE_EXECUTION=1 to run execution scenarios",
        )
    elif outcome.get("e01_ok"):
        report.add(
            "TC-HOM-E01",
            "Market round-trip (BUY → SELL)",
            ScenarioStatus.PASS,
            outcome.get("e01_detail", ""),
        )
    else:
        report.add(
            "TC-HOM-E01",
            "Market round-trip (BUY → SELL)",
            ScenarioStatus.FAIL,
            outcome.get("e01_detail", "Round-trip did not complete"),
        )
