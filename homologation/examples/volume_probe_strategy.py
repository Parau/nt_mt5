"""
VolumeProbeStrategy — reference model for MT5 adapter strategy development.

Objective
---------
Demonstrate the **canonical pattern** for handling trade volume in NautilusTrader
strategies backed by the ``nt_mt5`` adapter.  The adapter exposes two distinct
volume concepts that must **never** be conflated:

1. **Trade quantity (qty)** — ``TradeTick.size`` in instrument units
   (contracts for futures, shares for equities).  Valid only when the
   ``VenueProfile`` declares ``trade_ticks != UNSUPPORTED`` for the instrument's
   ``trade_calc_mode`` (e.g. XP/AMP exchange futures and B3 equities).

2. **Financial notional** — ``instrument.notional_value(tick.size, tick.price)``
   returning ``Money`` in the instrument currency.  Valid only when the parser
   set ``instrument.info["notional_mode"] == "linear_price_multiplier"``
   (e.g. WIN/WDO/MES, PETR4).  **Not valid** for DI1 (yield semantics) or
   Tickmill CFD/FX.

3. **Bar volume** — ``Bar.volume`` from MT5 ``tick_volume`` / ``real_volume``.
   This is an **activity proxy**, not per-trade contract/share count, and must
   not be used as a substitute for ``TradeTick.size`` or financial notional.

How to use this file
--------------------
- Copy the ``on_start`` capability resolution and the handler split into your
  own strategy; replace the ``_handle_*`` stubs with your logic.
- Pass the **same** ``venue_profile_name`` as ``MetaTrader5DataClientConfig``
  (``xp_b3``, ``tickmill``, ``amp_us``).
- Helpers live in ``nautilus_mt5.volume_capability``; unit tests in
  ``tests/unit/test_volume_capability.py``; live smoke in
  ``homologation/tools/volume_capability_smoke.py``.

Expected capability matrix (reference)
--------------------------------------
| Instrument        | trade_qty | financial_notional | bar.volume semantics   |
|-------------------|-----------|--------------------|------------------------|
| WINQ26 / MESU26   | yes       | yes                | exchange activity      |
| PETR4             | yes       | yes (multiplier=1) | exchange activity      |
| DI1F27            | yes       | no (yield)         | exchange activity      |
| BTCUSD / USTEC    | no        | no                 | tick-count activity    |

Not wired into homologation runners — this is a **template only**.
"""
from __future__ import annotations

from nautilus_trader.model.data import Bar, TradeTick
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Money
from nautilus_trader.trading.strategy import Strategy, StrategyConfig

from nautilus_mt5.venue_profile import resolve_venue_profile
from nautilus_mt5.volume_capability import (
    InstrumentVolumeCapability,
    financial_notional_from_tick,
    resolve_volume_capability,
    trade_qty_from_tick,
)


class VolumeProbeConfig(StrategyConfig, frozen=True):
    """
    Strategy config for the volume probe template.

    Attributes
    ----------
    instrument_ids
        Instruments to probe (must already be loaded in cache by InstrumentProvider).
    venue_profile_name
        Must match ``MetaTrader5DataClientConfig.venue_profile`` — e.g.
        ``"xp_b3"`` for XP/B3, ``"tickmill"`` for Tickmill-Demo,
        ``"amp_us"`` for AMP Global CME futures.
    """

    instrument_ids: tuple[InstrumentId, ...]
    venue_profile_name: str = "xp_b3"


class VolumeProbeStrategy(Strategy):
    """
    Reference strategy: resolve volume capabilities once, then branch handlers.

    Architectural rule: **decide per instrument in ``on_start``**, not per venue
    name or hard-coded symbol lists.  Runtime gates (``tick.size > 0``) remain
    as a second line of defence inside the helpers.
    """

    def __init__(self, config: VolumeProbeConfig) -> None:
        super().__init__(config)
        # Same profile object semantics as MetaTrader5DataClientConfig.
        self._profile = resolve_venue_profile(config.venue_profile_name)
        # Resolved once per instrument_id; keyed by str(instrument_id).
        self._caps: dict[str, InstrumentVolumeCapability] = {}

    def on_start(self) -> None:
        for instrument_id in self.config.instrument_ids:
            instrument = self.cache.instrument(instrument_id)
            if instrument is None:
                self.log.warning(f"Instrument not in cache: {instrument_id}")
                continue

            # Single source of truth: VenueProfile + instrument.info metadata.
            cap = resolve_volume_capability(instrument, self._profile)
            self._caps[str(instrument_id)] = cap

            self.log.info(
                f"{instrument_id} trade_qty={cap.trade_qty} "
                f"financial_notional={cap.financial_notional} "
                f"notional_mode={cap.notional_mode!r}"
            )

            self.subscribe_quote_ticks(instrument_id)
            # Do not subscribe trade ticks when profile marks them UNSUPPORTED
            # (Tickmill CFD/FX) — the DataClient would reject anyway.
            if cap.trade_qty:
                self.subscribe_trade_ticks(instrument_id)

    def on_trade_tick(self, tick: TradeTick) -> None:
        instrument = self.cache.instrument(tick.instrument_id)
        cap = self._caps.get(str(tick.instrument_id))
        if instrument is None or cap is None:
            return

        # Gate 1 — trade quantity (contracts/shares).  Independent of notional.
        qty = trade_qty_from_tick(cap, tick)
        if qty is None:
            return  # instrument unsupported, or tick without resolvable size

        # Gate 2 — financial notional (Money).  May be None even when qty is valid
        # (DI1 yield contracts, CFD without linear multiplier).
        notional = financial_notional_from_tick(instrument, cap, tick)
        if notional is not None:
            self._handle_trade_with_notional(tick, qty, notional)
        else:
            self._handle_trade_qty_only(tick, qty)

    def on_bar(self, bar: Bar) -> None:
        cap = self._caps.get(str(bar.bar_type.instrument_id))
        if cap is None:
            return

        activity = bar.volume.as_double()
        if activity <= 0:
            return

        # Bar volume semantics differ by instrument class:
        # - CFD/CurrencyPair (Tickmill): tick_volume count only → activity proxy
        # - FuturesContract/Equity (XP/AMP): may include real_volume, but still
        #   NOT equivalent to TradeTick.size or financial notional per bar.
        if cap.bar_volume_activity_only:
            self._handle_bar_activity(bar, activity)
        else:
            self._handle_bar_exchange_volume(bar, activity)

    # ── Replace these stubs with your strategy logic ──────────────────────

    def _handle_trade_with_notional(
        self,
        tick: TradeTick,
        qty: float,
        notional: Money,
    ) -> None:
        """WIN/WDO/MES/PETR4 path: both qty and financial volume available."""
        pass

    def _handle_trade_qty_only(self, tick: TradeTick, qty: float) -> None:
        """DI1 and similar: qty valid, financial notional intentionally absent."""
        pass

    def _handle_bar_activity(self, bar: Bar, activity: float) -> None:
        """Tickmill CFD/FX: bar.volume is tick-count activity, not trade qty."""
        pass

    def _handle_bar_exchange_volume(self, bar: Bar, volume: float) -> None:
        """XP/AMP exchange bars: volume as activity proxy (not financial notional)."""
        pass
