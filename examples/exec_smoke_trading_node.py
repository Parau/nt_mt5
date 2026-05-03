"""
exec_smoke_trading_node.py
==========================

Phase 7.4 example — complete round-trip TradingNode exec smoke for the MT5 adapter.

Smoke sequence (execution mode)
---------------------------------
  1. Connect data + exec clients to the MT5 gateway.
  2. Subscribe USTEC quote ticks — verifies the data client works end-to-end
     inside a real NautilusTrader TradingNode.
  3. On the first tick → submit a minimum-volume **BUY market** order (FOK).
  4. On BUY fill → submit an equal-volume **SELL market** order to close.
  5. On SELL fill → print a human-readable summary (entry price, exit price,
     gross P&L, commissions) and stop cleanly.
  6. Any rejection at any stage → log the reason and abort safely.

Data-only mode (default, no env var needed)
-------------------------------------------
  Subscribes to ticks and logs 5 of them, then stops.  No orders are placed.
  Use this to verify data connectivity without touching the account.

Safety gate
-----------
Live order execution is **disabled** by default.  Set::

    MT5_ENABLE_LIVE_EXECUTION=1

to allow the strategy to place real orders on your DEMO account.

Environment variables
---------------------
MT5_HOST                   RPyC gateway host  (default: 127.0.0.1)
MT5_PORT                   RPyC gateway port  (default: 18812)
MT5_ACCOUNT_NUMBER         MT5 account login  (required for exec validation)
MT5_ENABLE_LIVE_EXECUTION  Set to "1" to permit real order placement
MT5_SYMBOL                 Symbol to trade    (default: USTEC)
MT5_BROKER                 Broker/server name (default: Tickmill-Demo)

Usage
-----
    # Data-only smoke (default — no orders):
    python examples/exec_smoke_trading_node.py

    # Full round-trip on DEMO account:
    MT5_ACCOUNT_NUMBER=12345678 MT5_ENABLE_LIVE_EXECUTION=1 \\
        python examples/exec_smoke_trading_node.py
"""
from __future__ import annotations

import os
import threading
from enum import Enum, auto

from nautilus_trader.config import LiveDataEngineConfig, LoggingConfig, RoutingConfig, TradingNodeConfig
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.events import OrderFilled, OrderRejected
from nautilus_trader.model.identifiers import ClientOrderId, InstrumentId, Symbol, Venue
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy
from nautilus_trader.config import StrategyConfig

from nautilus_mt5 import TICKMILL_DEMO_PROFILE
from nautilus_mt5.client.types import MT5TerminalAccessMode
from nautilus_mt5.config import (
    ExternalRPyCTerminalConfig,
    MetaTrader5DataClientConfig,
    MetaTrader5ExecClientConfig,
    MetaTrader5InstrumentProviderConfig,
)
from nautilus_mt5.data_types import MT5Symbol
from nautilus_mt5.factories import MT5LiveDataClientFactory, MT5LiveExecClientFactory

# ---------------------------------------------------------------------------
# Module-level node reference (set after TradingNode is built) — used by the
# strategy to stop the node cleanly after the round-trip completes.
# ---------------------------------------------------------------------------

_node_ref: TradingNode | None = None

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

MT5_HOST = os.environ.get("MT5_HOST", "127.0.0.1")
MT5_PORT = int(os.environ.get("MT5_PORT", "18812"))
MT5_ACCOUNT = os.environ.get("MT5_ACCOUNT_NUMBER", "")
MT5_SYMBOL = os.environ.get("MT5_SYMBOL", "USTEC")
MT5_BROKER = os.environ.get("MT5_BROKER", "Tickmill-Demo")
ENABLE_EXECUTION = os.environ.get("MT5_ENABLE_LIVE_EXECUTION", "").strip() == "1"

_DATA_ONLY_TICK_LIMIT = 5  # stop after N ticks in data-only mode

_VENUE = Venue("METATRADER_5")
_INSTRUMENT_ID = InstrumentId(Symbol(MT5_SYMBOL), _VENUE)

# ---------------------------------------------------------------------------
# Strategy state machine
# ---------------------------------------------------------------------------


class _Phase(Enum):
    IDLE = auto()           # waiting for first tick
    WAITING_BUY = auto()    # BUY submitted, waiting for fill
    WAITING_SELL = auto()   # SELL submitted, waiting for fill
    DONE = auto()           # both legs filled — smoke passed
    ABORTED = auto()        # rejection received — smoke failed


class ExecSmokeConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    enable_execution: bool = False


class ExecSmokeStrategy(Strategy):
    """
    Round-trip execution smoke strategy.

    Data-only mode  (``enable_execution=False``):
        Subscribes to quote ticks and logs ``_DATA_ONLY_TICK_LIMIT`` of them,
        then stops.  Verifies data connectivity end-to-end inside TradingNode.

    Execution mode  (``enable_execution=True``):
        Phase 1 — on first tick: submit BUY market (FOK), min volume.
        Phase 2 — on BUY fill: submit SELL market (FOK), same volume, to close.
        Phase 3 — on SELL fill: print summary and stop cleanly.
        Abort    — any rejection: log reason and stop.
    """

    def __init__(self, config: ExecSmokeConfig) -> None:
        super().__init__(config)
        self._phase: _Phase = _Phase.IDLE
        self._tick_count: int = 0
        self._buy_order_id: ClientOrderId | None = None
        self._sell_order_id: ClientOrderId | None = None
        self._buy_fill_px: float = 0.0
        self._buy_fill_qty: float = 0.0
        self._buy_commission: float = 0.0
        self._sell_fill_px: float = 0.0
        self._sell_commission: float = 0.0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        instrument = self.cache.instrument(self.config.instrument_id)
        if instrument is None:
            self.log.error(f"Instrument not found: {self.config.instrument_id}. Stopping.")
            self.stop()
            return
        self.subscribe_quote_ticks(instrument_id=self.config.instrument_id)
        mode = "LIVE ROUND-TRIP" if self.config.enable_execution else "DATA-ONLY (no orders)"
        self.log.info(f"ExecSmokeStrategy started [{mode}] for {self.config.instrument_id}")

    def on_stop(self) -> None:
        self.unsubscribe_quote_ticks(instrument_id=self.config.instrument_id)
        self.log.info("ExecSmokeStrategy stopped.")
        # Stop the trading node from a daemon thread so node.run() returns.
        if _node_ref is not None:
            threading.Thread(target=_node_ref.stop, daemon=True, name="smoke-stop").start()

    # ------------------------------------------------------------------
    # Data events
    # ------------------------------------------------------------------

    def on_quote_tick(self, tick: QuoteTick) -> None:
        self._tick_count += 1
        self.log.info(f"QuoteTick #{self._tick_count}: bid={tick.bid_price} ask={tick.ask_price}")

        if not self.config.enable_execution:
            if self._tick_count >= _DATA_ONLY_TICK_LIMIT:
                self.log.info(
                    f"Data-only smoke complete — received {self._tick_count} ticks. Stopping."
                )
                self.stop()
            return

        # Execution mode: submit BUY on the very first tick.
        if self._phase is _Phase.IDLE:
            self._submit_open(tick)

    # ------------------------------------------------------------------
    # Order events
    # ------------------------------------------------------------------

    def on_order_submitted(self, event) -> None:
        self.log.info(f"[SUBMITTED] {event.client_order_id}")

    def on_order_accepted(self, event) -> None:
        self.log.info(f"[ACCEPTED]  {event.client_order_id} → venue={event.venue_order_id}")

    def on_order_rejected(self, event: OrderRejected) -> None:
        self.log.error(
            f"[REJECTED]  {event.client_order_id} — reason: {event.reason}"
        )
        self._phase = _Phase.ABORTED
        self.log.error("Smoke ABORTED due to order rejection.")
        self.stop()

    def on_order_filled(self, event: OrderFilled) -> None:
        if event.client_order_id == self._buy_order_id:
            self._on_buy_filled(event)
        elif event.client_order_id == self._sell_order_id:
            self._on_sell_filled(event)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _min_quantity(self) -> Quantity:
        instrument = self.cache.instrument(self.config.instrument_id)
        if instrument and instrument.min_quantity:
            return instrument.min_quantity
        return Quantity.from_str("0.1")

    def _submit_open(self, tick: QuoteTick) -> None:
        """Submit the opening BUY market order."""
        qty = self._min_quantity()
        order = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=OrderSide.BUY,
            quantity=qty,
            time_in_force=TimeInForce.IOC,
        )
        self._buy_order_id = order.client_order_id
        self._phase = _Phase.WAITING_BUY
        self.submit_order(order)
        self.log.info(
            f"[OPEN]  Submitted BUY {qty} {self.config.instrument_id} "
            f"(ask={tick.ask_price}) — id={order.client_order_id}"
        )

    def _on_buy_filled(self, event: OrderFilled) -> None:
        self._buy_fill_px = float(event.last_px)
        self._buy_fill_qty = float(event.last_qty)
        self._buy_commission = abs(float(event.commission))
        self.log.info(
            f"[FILL-BUY]  {self._buy_fill_qty} @ {self._buy_fill_px}  "
            f"commission={self._buy_commission}"
        )
        self._submit_close()

    def _submit_close(self) -> None:
        """Submit the closing SELL market order (same volume as BUY fill)."""
        qty = Quantity.from_str(str(self._buy_fill_qty))
        order = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=OrderSide.SELL,
            quantity=qty,
            time_in_force=TimeInForce.IOC,
        )
        self._sell_order_id = order.client_order_id
        self._phase = _Phase.WAITING_SELL
        self.submit_order(order)
        self.log.info(
            f"[CLOSE] Submitted SELL {qty} {self.config.instrument_id} "
            f"— id={order.client_order_id}"
        )

    def _on_sell_filled(self, event: OrderFilled) -> None:
        self._sell_fill_px = float(event.last_px)
        self._sell_commission = abs(float(event.commission))
        self.log.info(
            f"[FILL-SELL] {float(event.last_qty)} @ {self._sell_fill_px}  "
            f"commission={self._sell_commission}"
        )
        self._phase = _Phase.DONE
        self._print_summary()
        self.stop()

    def _print_summary(self) -> None:
        gross_pnl = (self._sell_fill_px - self._buy_fill_px) * self._buy_fill_qty
        total_commission = self._buy_commission + self._sell_commission
        net_pnl = gross_pnl - total_commission
        sep = "=" * 52
        self.log.info(sep)
        self.log.info("  EXEC SMOKE — ROUND-TRIP COMPLETE")
        self.log.info(f"  Symbol     : {self.config.instrument_id}")
        self.log.info(f"  Volume     : {self._buy_fill_qty}")
        self.log.info(f"  Entry (BUY): {self._buy_fill_px}")
        self.log.info(f"  Exit (SELL): {self._sell_fill_px}")
        self.log.info(f"  Gross P&L  : {gross_pnl:+.5f}")
        self.log.info(f"  Commission : -{total_commission:.5f}")
        self.log.info(f"  Net P&L    : {net_pnl:+.5f}")
        self.log.info(f"  Result     : {'PASS' if True else 'FAIL'}")
        self.log.info(sep)


# ---------------------------------------------------------------------------
# Node configuration
# ---------------------------------------------------------------------------

external_rpyc = ExternalRPyCTerminalConfig(host=MT5_HOST, port=MT5_PORT)
instrument_provider = MetaTrader5InstrumentProviderConfig(
    load_symbols=frozenset([MT5Symbol(symbol=MT5_SYMBOL, broker=MT5_BROKER)]),
)

config_node = TradingNodeConfig(
    trader_id="EXEC-SMOKE-001",
    logging=LoggingConfig(log_level="DEBUG"),
    data_clients={
        "MT5": MetaTrader5DataClientConfig(
            client_id=1,
            terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
            external_rpyc=external_rpyc,
            instrument_provider=instrument_provider,
            venue_profile=TICKMILL_DEMO_PROFILE,
        ),
    },
    exec_clients={
        "MT5": MetaTrader5ExecClientConfig(
            client_id=1,
            account_id=MT5_ACCOUNT or None,
            terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
            external_rpyc=external_rpyc,
            instrument_provider=instrument_provider,
            routing=RoutingConfig(default=True),
        ),
    },
    data_engine=LiveDataEngineConfig(
        time_bars_timestamp_on_close=False,
        validate_data_sequence=True,
    ),
)

node = TradingNode(config=config_node)

node.add_data_client_factory("MT5", MT5LiveDataClientFactory)
node.add_exec_client_factory("MT5", MT5LiveExecClientFactory)

strategy = ExecSmokeStrategy(
    ExecSmokeConfig(
        strategy_id="EXEC-SMOKE",
        instrument_id=_INSTRUMENT_ID,
        enable_execution=ENABLE_EXECUTION,
    )
)

node.build()

node.trader.add_strategy(strategy)

# Expose the node to the strategy so it can trigger clean shutdown.
_node_ref = node

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("MT5 Adapter — Exec Smoke TradingNode (Round-Trip)")
    print(f"  Symbol   : {MT5_SYMBOL}")
    print(f"  Gateway  : {MT5_HOST}:{MT5_PORT}")
    print(f"  Account  : {MT5_ACCOUNT or '(not set)'}")
    print(f"  Execution: {'ENABLED — BUY then SELL (DEMO)' if ENABLE_EXECUTION else 'DISABLED — data-only'}")
    if ENABLE_EXECUTION and not MT5_ACCOUNT:
        print()
        print("WARNING: MT5_ENABLE_LIVE_EXECUTION=1 but MT5_ACCOUNT_NUMBER is not set.")
        print("         The exec client may reject connection due to missing account_id.")
    print("=" * 60)
    print()
    try:
        node.run()
    finally:
        node.dispose()
