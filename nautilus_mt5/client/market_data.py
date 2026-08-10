
import asyncio
import functools
import math
import operator
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from inspect import iscoroutinefunction
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytz

from nautilus_mt5.common import BarData


from nautilus_trader.core.data import Data
from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import BarType
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import TradeId
from nautilus_trader.model.instruments.base import Instrument


from nautilus_mt5.client.errors import MT5HistoricalDataError
from nautilus_mt5.data_types import MT5Symbol
from nautilus_mt5.client.tick_poll import is_quote_tick_subscription
from nautilus_mt5.common import Subscription
from nautilus_mt5.feed.converter import wire_tick_to_trade_tick
from nautilus_mt5.feed.messages import WireTick
from nautilus_mt5.parsing.data import what_to_show
from nautilus_mt5.parsing.instruments import mt5_symbol_to_instrument_id
from nautilus_mt5.parsing.tick_volume import resolve_trade_tick_size
from nautilus_mt5.parsing.rates import (
    bar_spec_to_mt5_timeframe,
    ib_duration_to_timedelta,
    mql_rate_row_to_bar_data,
    timestamp_to_utc_datetime,
)
from nautilus_mt5.tick_routing import resolve_trade_aggressor
from nautilus_mt5.tick_routing import route_wire_tick

_NS_PER_SECOND = 1_000_000_000
_REQUIRED_TRADE_FIELDS = frozenset(
    {
        "time_msc",
        "bid",
        "ask",
        "last",
        "volume",
        "volume_real",
        "flags",
    },
)


def _resolve_mt5_constant(mt5: Any, name: str) -> Any:
    """Resolve a named MT5 constant from attribute or ``get_constant`` fallback."""
    value = getattr(mt5, name, None)
    if value is not None:
        return value

    get_constant = getattr(mt5, "get_constant", None)
    if callable(get_constant):
        try:
            value = get_constant(name)
        except Exception as exc:
            raise MT5HistoricalDataError(
                f"MT5 get_constant({name!r}) failed",
            ) from exc
        if value is not None:
            return value

    raise MT5HistoricalDataError(
        f"MT5 terminal surface does not expose required constant {name}",
    )


def _best_effort_mt5_last_error(mt5: Any) -> Any:
    """Best-effort ``last_error()``; never hides the original failure."""
    last_error = getattr(mt5, "last_error", None)
    if not callable(last_error):
        return None
    try:
        return last_error()
    except Exception as exc:  # noqa: BLE001 — diagnostics must not mask provider failure
        return f"<last_error failed: {exc!r}>"


def _historical_utc_timestamp(value: datetime | pd.Timestamp) -> pd.Timestamp:
    """Normalize a timezone-aware bound to UTC; reject naive values."""
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        raise MT5HistoricalDataError("historical bound must be timezone-aware")
    return ts.tz_convert("UTC")


class MarketDataTypeEnum:
    REALTIME = 1
    @classmethod
    def to_str(cls, val): return 'REALTIME'

class MetaTrader5ClientMarketDataMixin:
    """
    Handles market data requests, subscriptions and data processing for the
    MetaTrader5Client.

    This class handles real-time and historical market data subscription management,
    including subscribing and unsubscribing to ticks, bars, and other market data types.
    It processes and formats the received data to be compatible with the Nautilus
    Trader.

    """

    async def set_market_data_type(self, market_data_type: MarketDataTypeEnum) -> None:
        """
        Set the market data type for data subscriptions. This method configures the type
        of market data (live, delayed, etc.) to be used for subsequent data requests.

        Parameters
        ----------
        market_data_type : MarketDataTypeEnum
            The market data type to be set

        """
        self._log.info(
            f"Setting Market DataType to {MarketDataTypeEnum.to_str(market_data_type)}"
        )
        self._mt5_client['mt5'].req_market_data_type(market_data_type)

    async def _subscribe(
        self,
        name: str | tuple,
        subscription_method: Callable | functools.partial,
        cancellation_method: Callable,
        *args: Any,
        **kwargs: Any,
    ) -> Subscription | None:
        """
        Manage the subscription and un-subscription process for market data. This
        internal method is responsible for handling the logic to subscribe or
        unsubscribe to different market data types (ticks, bars, etc.). It uses the
        provided subscription and cancellation methods to control the data flow.

        Parameters
        ----------
        name : Any
            A unique identifier for the subscription.
        subscription_method : Callable
            The method to call for subscribing to market data.
        cancellation_method : Callable
            The method to call for unsubscribing from market data.
        *args
            Variable length argument list for the subscription method.
        **kwargs
            Arbitrary keyword arguments for the subscription method.

        Returns
        -------
        Subscription | ``None``

        """
        if not (subscription := self._subscriptions.get(name=name)):
            req_id = self._next_req_id()
            if subscription_method == self.subscribe_historical_bars:
                handle_func = functools.partial(
                    subscription_method,
                    *args,
                    **kwargs,
                )
            else:
                handle_func = functools.partial(
                    subscription_method, req_id, *args, **kwargs
                )
            subscription = self._subscriptions.add(
                req_id=req_id,
                name=name,
                handle=handle_func,
                cancel=functools.partial(cancellation_method, req_id),
            )
            if not subscription:
                return None
            if iscoroutinefunction(subscription.handle):
                await subscription.handle()
            else:
                subscription.handle()

            return subscription
        else:
            self._log.info(f"Subscription already exists for {subscription}")
            return None

    async def _unsubscribe(
        self,
        name: str | tuple,
        cancellation_method: Callable,
    ) -> None:
        """
        Manage the un-subscription process for market data. This internal method is
        responsible for handling the logic to unsubscribe to different market data types
        (ticks, bars, etc.). It uses the provided cancellation method to control the
        data flow.

        Parameters
        ----------
        cancellation_method : Callable
            The method to call for unsubscribing from market data.
        name : Any
            A unique identifier for the subscription.

        """
        if subscription := self._subscriptions.get(name=name):
            self._subscriptions.remove(subscription.req_id)
            cancellation_method(
                req_id=subscription.req_id, symbol=subscription.handle.args[1]
            )
            self._log.debug(f"Unsubscribed from {subscription}")
        else:
            self._log.debug(f"Subscription doesn't exist for {name}")

    async def subscribe_ticks(
        self,
        instrument_id: InstrumentId,
        symbol: MT5Symbol,
        tick_type: str,
        ignore_size: bool,
    ) -> None:
        """
        Subscribe to tick data for a specified instrument.

        Parameters
        ----------
        instrument_id : InstrumentId
            The identifier of the instrument for which to subscribe.
        symbol : MT5Symbol
            The symbol details for the instrument.
        tick_type : str
            The type of tick data to subscribe to.
        ignore_size : bool
            Omit updates that reflect only changes in size, and not price.
            Applicable to Bid_Ask data requests.

        """

        if self.live_quote_feed_enabled and is_quote_tick_subscription(tick_type):
            self._log.debug(
                "Live quote feed enabled; ignoring RPyC quote tick subscription for "
                f"{instrument_id} ({tick_type}).",
            )
            return

        name = (str(instrument_id), tick_type)
        # Hack for MetaTrader5 missing streaming tick subscription methods
        # Use symbol_info_tick for polling later or a custom RPyC exposed method
        poll_func = getattr(self._mt5_client['mt5'], "req_tick_by_tick_data", None)
        cancel_func = getattr(self._mt5_client['mt5'], "cancel_tick_by_tick_data", None)

        if poll_func and cancel_func:
            await self._subscribe(
                name,
                poll_func,
                cancel_func,
                symbol,
                tick_type,
                0,
                ignore_size,
            )
        else:
            # Gateway does not expose req_tick_by_tick_data; register a no-op subscription
            # so the polling loop in _run_terminal_incoming_msg_reader can find it by name
            # and poll via symbol_info_tick.
            self._log.debug(
                f"MT5 gateway has no streaming tick method; registering polling subscription for {symbol}."
            )
            await self._subscribe(
                name,
                lambda req_id, sym, *a, **kw: None,  # no-op: polling loop does the actual work
                lambda req_id, **kw: None,
                symbol,
                tick_type,
                0,
                ignore_size,
            )

    async def unsubscribe_ticks(
        self, instrument_id: InstrumentId, tick_type: str
    ) -> None:
        """
        Unsubscribes from tick data for a specified instrument.

        Parameters
        ----------
        instrument_id : InstrumentId
            The identifier of the instrument for which to unsubscribe.
        tick_type : str
            The type of tick data to unsubscribe from.

        """
        name = (str(instrument_id), tick_type)
        cancel_func = getattr(self._mt5_client['mt5'], "cancel_tick_by_tick_data", None)
        if cancel_func is None:
            cancel_func = lambda req_id, **kw: None  # no-op for polling-only gateways
        await self._unsubscribe(name, cancel_func)

    async def subscribe_realtime_bars(
        self,
        bar_type: BarType,
        symbol: MT5Symbol,
        use_rth: bool,
    ) -> None:
        """
        Deprecated: live bars use the MQL5 WS feed (``feed.enabled=True``).

        IB ``req_real_time_bars`` is not supported on the MT5 RPyC bridge.
        """
        self._log.warning(
            "subscribe_realtime_bars is deprecated; enable feed.enabled on DataClientConfig "
            f"and use SubscribeBars via NT5TickFeedService (ignored for {bar_type}).",
        )

    async def unsubscribe_realtime_bars(self, bar_type: BarType) -> None:
        """Deprecated — see ``subscribe_realtime_bars``."""
        self._log.warning(
            "unsubscribe_realtime_bars is deprecated; use feed.enabled WS path "
            f"(ignored for {bar_type}).",
        )

    async def subscribe_historical_bars(
        self,
        bar_type: BarType,
        symbol: MT5Symbol,
        use_rth: bool,
        handle_revised_bars: bool,
    ) -> None:
        """
        Deprecated: live bar subscribe uses WS ``subscribe_bars``, not IB hooks.

        Historical on-demand bars remain via ``get_historical_bars`` / ``copy_rates_*``.
        """
        self._log.warning(
            "subscribe_historical_bars is deprecated; enable feed.enabled on DataClientConfig "
            f"and use SubscribeBars via NT5TickFeedService (ignored for {bar_type}).",
        )

    async def unsubscribe_historical_bars(self, bar_type: BarType) -> None:
        """Deprecated — see ``subscribe_historical_bars``."""
        self._log.warning(
            "unsubscribe_historical_bars is deprecated; use feed.enabled WS path "
            f"(ignored for {bar_type}).",
        )

    async def get_historical_bars(
        self,
        bar_type: BarType,
        symbol: MT5Symbol,
        use_rth: bool,
        end_date_time: pd.Timestamp,
        duration: str = "7 D",
        timeout: int = 60,
        *,
        start_date_time: pd.Timestamp | None = None,
        limit: int | None = None,
    ) -> list[Bar]:
        """
        Request historical bars via MT5-native ``copy_rates_*`` (RPyC bridge).

        Uses ``copy_rates_range`` when ``start_date_time`` is set, otherwise
        ``copy_rates_from_pos`` with ``limit`` (default 1000).
        """
        del timeout  # synchronous copy_rates; kept for call-site compatibility

        if use_rth:
            self._log.debug(
                f"use_rth=True ignored for MT5 copy_rates historical bars ({bar_type})",
            )

        if end_date_time.tzinfo is None:
            end_date_time = end_date_time.replace(tzinfo=ZoneInfo("UTC"))
        else:
            end_date_time = end_date_time.astimezone(ZoneInfo("UTC"))

        mt5_symbol = symbol.symbol
        timeframe = bar_spec_to_mt5_timeframe(bar_type.spec)
        mt5 = self._mt5_client["mt5"]

        try:
            mt5.symbol_select(mt5_symbol, True)
        except Exception as exc:
            self._log.warning(f"symbol_select({mt5_symbol}) failed: {exc}")

        rates = await asyncio.to_thread(
            self._copy_rates,
            mt5,
            mt5_symbol,
            timeframe,
            end_date_time,
            duration,
            start_date_time,
            limit,
        )
        if not rates:
            return []

        ts_init = self._clock.timestamp_ns()
        bars: list[Bar] = []
        for row in reversed(rates):
            bar_data = mql_rate_row_to_bar_data(mt5_symbol, row)
            if bar_data.time <= 0 or bar_data.close <= 0.0:
                continue
            bars.append(
                await self._mt5_bar_to_nautilus_bar(
                    bar_type=bar_type,
                    bar=bar_data,
                    ts_init=ts_init,
                ),
            )
        return bars

    def _copy_rates(
        self,
        mt5: Any,
        symbol: str,
        timeframe: int,
        end_date_time: pd.Timestamp,
        duration: str,
        start_date_time: pd.Timestamp | None,
        limit: int | None,
    ) -> list[Any]:
        if start_date_time is not None:
            if start_date_time.tzinfo is None:
                start_date_time = start_date_time.tz_localize("UTC")
            else:
                start_date_time = start_date_time.tz_convert("UTC")
            raw = mt5.copy_rates_range(
                symbol,
                timeframe,
                timestamp_to_utc_datetime(start_date_time),
                timestamp_to_utc_datetime(end_date_time),
            )
        else:
            count = limit if limit is not None and limit > 0 else 1000
            raw = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
            if raw is None or len(raw) == 0:
                delta = ib_duration_to_timedelta(duration)
                date_from = end_date_time - delta
                raw = mt5.copy_rates_range(
                    symbol,
                    timeframe,
                    timestamp_to_utc_datetime(date_from),
                    timestamp_to_utc_datetime(end_date_time),
                )

        if raw is None:
            self._log.warning(
                f"copy_rates returned None for {symbol} timeframe={timeframe}",
            )
            return []
        return list(raw)

    async def get_historical_ticks(
        self,
        symbol: MT5Symbol,
        tick_type: str,
        start_date_time: pd.Timestamp | str = "",
        end_date_time: pd.Timestamp | str = "",
        use_rth: bool = True,
        timeout: int = 60,
        number_of_ticks: int = 1000,
        map_tick_flags_to_aggressor: bool = False,
    ) -> list[QuoteTick | TradeTick] | None:
        """
        Request and retrieve historical tick data for a specified symbol and tick
        type via MT5-native ``copy_ticks_from``.
        """
        import time as _time

        mt5 = self._mt5_client["mt5"]
        symbol_str = symbol.symbol

        if isinstance(end_date_time, pd.Timestamp):
            end_ts = int(end_date_time.timestamp())
        elif isinstance(end_date_time, str) and end_date_time.strip():
            end_ts = int(pd.Timestamp(end_date_time).timestamp())
        else:
            end_ts = int(_time.time())

        if isinstance(start_date_time, pd.Timestamp):
            from_ts = int(start_date_time.timestamp())
        elif isinstance(start_date_time, str) and start_date_time.strip():
            from_ts = int(pd.Timestamp(start_date_time).timestamp())
        else:
            from_ts = None

        flags = getattr(mt5, "COPY_TICKS_ALL", 0)
        try:
            # Prefer copy_ticks_from with a count cap — copy_ticks_range pulls the entire window
            # (e.g. 800k+ ticks over 7 days on WDON26) and is only for uncapped requests.
            if from_ts is not None and number_of_ticks > 0:
                raw = await asyncio.to_thread(
                    mt5.copy_ticks_from,
                    symbol_str,
                    from_ts,
                    number_of_ticks,
                    flags,
                )
            elif from_ts is not None and from_ts < end_ts and hasattr(mt5, "copy_ticks_range"):
                raw = await asyncio.to_thread(
                    mt5.copy_ticks_range,
                    symbol_str,
                    from_ts,
                    end_ts,
                    flags,
                )
            else:
                if from_ts is None:
                    from_ts = end_ts - 86_400
                raw = await asyncio.to_thread(
                    mt5.copy_ticks_from,
                    symbol_str,
                    from_ts,
                    number_of_ticks or 1000,
                    flags,
                )
        except Exception as exc:
            self._log.warning(f"copy_ticks failed for {symbol_str}: {exc}")
            return []

        if raw is None or len(raw) == 0:
            return []

        try:
            import rpyc
            rows = rpyc.classic.obtain(list(raw))
        except Exception:
            rows = list(raw)

        instrument_id = mt5_symbol_to_instrument_id(symbol)
        instrument = self._cache.instrument(instrument_id)
        if instrument is None:
            self._log.warning(
                f"Instrument {instrument_id} not in cache for historical ticks",
            )
            return []

        ticks_out: list[QuoteTick | TradeTick] = []
        for row in rows:
            bid = ask = last = 0.0
            volume = 0.0
            volume_real = 0.0
            time_sec = 0
            time_msc = None
            tick_flags = 0
            try:
                if hasattr(row, "dtype"):
                    bid = float(row["bid"])
                    ask = float(row["ask"])
                    last = float(row["last"])
                    volume = float(row["volume"]) if "volume" in row.dtype.names else 0.0
                    volume_real = (
                        float(row["volume_real"]) if "volume_real" in row.dtype.names else 0.0
                    )
                    time_sec = int(row["time"])
                    time_msc = row["time_msc"] if "time_msc" in row.dtype.names else None
                    if "flags" in row.dtype.names:
                        tick_flags = int(row["flags"])
                elif isinstance(row, dict):
                    bid = float(row.get("bid", 0) or 0)
                    ask = float(row.get("ask", 0) or 0)
                    last = float(row.get("last", 0) or 0)
                    volume = float(row.get("volume", 0) or 0)
                    volume_real = float(row.get("volume_real", 0) or 0)
                    time_sec = int(row.get("time", 0) or 0)
                    time_msc = row.get("time_msc")
                    tick_flags = int(row.get("flags", 0) or 0)
                elif isinstance(row, (tuple, list)) and len(row) >= 3:
                    time_sec = int(row[0])
                    bid = float(row[1])
                    ask = float(row[2])
                    last = float(row[3]) if len(row) > 3 else 0.0
                    volume = float(row[4]) if len(row) > 4 else 0.0
                    time_msc = row[5] if len(row) > 5 else None
                    tick_flags = int(row[6]) if len(row) > 6 else 0
                    volume_real = float(row[7]) if len(row) > 7 else 0.0
                else:
                    bid = float(getattr(row, "bid", 0) or 0)
                    ask = float(getattr(row, "ask", 0) or 0)
                    last = float(getattr(row, "last", 0) or 0)
                    volume = float(getattr(row, "volume", 0) or 0)
                    volume_real = float(getattr(row, "volume_real", 0) or 0)
                    time_sec = int(getattr(row, "time", 0) or 0)
                    time_msc = getattr(row, "time_msc", None)
                    tick_flags = int(getattr(row, "flags", 0) or 0)
            except (TypeError, KeyError, IndexError, ValueError):
                continue

            if time_msc:
                ts_event = int(time_msc) * 1_000_000
            elif time_sec:
                ts_event = int(pd.Timestamp.fromtimestamp(time_sec, tz=pytz.utc).value)
            else:
                continue

            if tick_type in ("TRADES", "AllLast"):
                if last <= 0:
                    continue
                trade_size = resolve_trade_tick_size(volume, volume_real)
                if trade_size is None:
                    continue
                ticks_out.append(TradeTick(
                    instrument_id=instrument_id,
                    price=instrument.make_price(last),
                    size=instrument.make_qty(trade_size),
                    aggressor_side=resolve_trade_aggressor(
                        tick_flags,
                        map_from_tick_flags=map_tick_flags_to_aggressor,
                    ),
                    trade_id=TradeId(str(time_sec)),
                    ts_event=ts_event,
                    ts_init=max(self._clock.timestamp_ns(), ts_event),
                ))
            else:
                if bid <= 0 or ask <= 0:
                    continue
                ticks_out.append(QuoteTick(
                    instrument_id=instrument_id,
                    bid_price=instrument.make_price(bid),
                    ask_price=instrument.make_price(ask),
                    bid_size=instrument.make_qty(0),
                    ask_size=instrument.make_qty(0),
                    ts_event=ts_event,
                    ts_init=max(self._clock.timestamp_ns(), ts_event),
                ))

        ticks_out.sort(key=lambda t: t.ts_init)
        if number_of_ticks > 0 and len(ticks_out) > number_of_ticks:
            ticks_out = ticks_out[-number_of_ticks:]
        return ticks_out

    async def get_historical_trade_ticks_range(
        self,
        *,
        symbol: MT5Symbol,
        instrument: Instrument,
        start_date_time: datetime | pd.Timestamp,
        end_date_time: datetime | pd.Timestamp,
        map_tick_flags_to_aggressor: bool,
    ) -> list[TradeTick]:
        """
        Return TradeTicks for one bounded logical interval (A05).

        Uses ``copy_ticks_range`` + ``COPY_TICKS_TRADE``, exact local ndarray
        materialization, live-equivalent routing/conversion, and inclusive
        ``ts_event`` filtering. Empty local ndarray is success ``[]``; ``None``
        and materialization/structural failures raise ``MT5HistoricalDataError``.
        """
        start_ts = _historical_utc_timestamp(start_date_time)
        end_ts = _historical_utc_timestamp(end_date_time)
        start_ns = int(start_ts.value)
        end_ns = int(end_ts.value)
        if start_ns > end_ns:
            raise MT5HistoricalDataError("historical start was after end")

        fetch_start_seconds = start_ns // _NS_PER_SECOND
        fetch_end_seconds = (end_ns + _NS_PER_SECOND - 1) // _NS_PER_SECOND
        if fetch_end_seconds <= fetch_start_seconds:
            fetch_end_seconds = fetch_start_seconds + 1

        mt5 = self._mt5_client["mt5"]
        flags = _resolve_mt5_constant(mt5, "COPY_TICKS_TRADE")

        try:
            raw = await asyncio.to_thread(
                mt5.copy_ticks_range,
                symbol.symbol,
                fetch_start_seconds,
                fetch_end_seconds,
                flags,
            )
        except Exception as exc:
            raise MT5HistoricalDataError(
                f"copy_ticks_range failed for {symbol.symbol}",
            ) from exc

        if raw is None:
            diagnostics = _best_effort_mt5_last_error(mt5)
            raise MT5HistoricalDataError(
                f"copy_ticks_range returned None for {symbol.symbol}; "
                f"last_error={diagnostics!r}",
            )

        # Exact local production identity — remote ndarray netrefs are failures.
        if type(raw) is not np.ndarray:
            raise MT5HistoricalDataError(
                "copy_ticks_range result is not an exact local numpy.ndarray",
            )
        if raw.dtype.names is None:
            raise MT5HistoricalDataError(
                "copy_ticks_range returned an unstructured numpy.ndarray",
            )

        names = frozenset(raw.dtype.names)
        missing = _REQUIRED_TRADE_FIELDS - names
        if missing:
            raise MT5HistoricalDataError(
                f"copy_ticks_range missing required fields: {sorted(missing)}",
            )

        if len(raw) == 0:
            return []

        batch_ts_init = self._clock.timestamp_ns()
        ticks: list[TradeTick] = []

        for index, row in enumerate(raw):
            try:
                time_msc = operator.index(row["time_msc"])
                volume = operator.index(row["volume"])
                flags_i = operator.index(row["flags"])
                bid = float(row["bid"])
                ask = float(row["ask"])
                last = float(row["last"])
                volume_real = float(row["volume_real"])
            except (KeyError, TypeError, ValueError, OverflowError) as exc:
                raise MT5HistoricalDataError(
                    f"Malformed MT5 historical trade row at index={index}",
                ) from exc

            if time_msc <= 0:
                raise MT5HistoricalDataError(
                    f"Invalid time_msc at index={index}: {time_msc}",
                )
            if volume < 0 or flags_i < 0:
                raise MT5HistoricalDataError(
                    f"Invalid volume/flags at index={index}",
                )
            if (
                not math.isfinite(bid)
                or not math.isfinite(ask)
                or not math.isfinite(last)
                or not math.isfinite(volume_real)
                or volume_real < 0
            ):
                raise MT5HistoricalDataError(
                    f"Non-finite/invalid MT5 trade row at index={index}",
                )

            wire = WireTick(
                time_msc=time_msc,
                bid=bid,
                ask=ask,
                last=last,
                volume=volume,
                volume_real=volume_real,
                flags=flags_i,
            )

            decision = route_wire_tick(instrument, wire)
            if not decision.emit_trade:
                continue

            try:
                trade = wire_tick_to_trade_tick(
                    instrument,
                    wire,
                    batch_ts_init,
                    map_tick_flags_to_aggressor=map_tick_flags_to_aggressor,
                )
            except Exception as exc:
                raise MT5HistoricalDataError(
                    f"Failed converting MT5 historical trade row at index={index}",
                ) from exc

            if trade is not None:
                ticks.append(trade)

        ticks = [
            tick
            for tick in ticks
            if start_ns <= tick.ts_event <= end_ns
        ]
        ticks.sort(key=lambda tick: tick.ts_event)
        return ticks

    #
    # misc.
    #
    async def _convert_mt5_timestamp_to_pandas_timestamp(
        self, timestamp: float
    ) -> pd.Timestamp:
        """
        Converts a MetaTrader 5 timestamp (in milliseconds since the Unix epoch) to a Pandas Timestamp object.

        Args:
            timestamp (float): The MetaTrader 5 timestamp in milliseconds.

        Returns:
            pd.Timestamp: The converted Pandas Timestamp object.
        """

        try:
            # Attempt to convert directly to a Pandas Timestamp
            ts = pd.Timestamp.fromtimestamp(timestamp / 1000, tz=pytz.utc)
        except ValueError:
            # If the conversion fails, try handling potential date format issues
            try:
                # Handle YYYYMMDD format (if applicable)
                timestamp_str = str(int(timestamp))
                ts = pd.to_datetime(timestamp_str, format="%Y%m%d", tz=pytz.utc)
            except ValueError:
                # If both conversions fail, raise a custom exception or handle the error appropriately
                raise ValueError(f"Invalid timestamp: {timestamp}")

        return ts.value

    async def _convert_mt5_bar_date_to_unix_nanos(
        self, bar: BarData, bar_type: BarType
    ) -> int:
        """
        Convert the date from BarData to unix nanoseconds.

        If the bar type's aggregation is 14, the bar.time is always returned in the
        YYYYMMDD format. For all other aggregations, the bar.time is returned
        in system time.

        Parameters
        ----------
        bar : BarData
            The bar data containing the date to be converted.
        bar_type : BarType
            The bar type that specifies the aggregation level.

        Returns
        -------
        int

        """
        if bar_type.spec.aggregation == 14:
            # Day bars are always returned with bar.time in YYYYMMDD format
            ts = pd.to_datetime(bar.time, format="%Y%m%d", utc=True)
        else:
            ts = pd.Timestamp.fromtimestamp(int(bar.time), tz=pytz.utc)

        return ts.value

    async def _mt5_bar_to_ts_init(self, bar: BarData, bar_type: BarType) -> int:
        """
        Calculate the initialization timestamp for a bar.

        This method computes the timestamp at which a bar is initialized, by adjusting
        the provided bar's timestamp based on the bar type's duration. ts_init is set
        to the end of the bar period and not the start.

        Parameters
        ----------
        bar : BarData
            The bar data to be used for the calculation.
        bar_type : BarType
            The type of the bar, which includes information about the bar's duration.

        Returns
        -------
        int

        """
        ts = await self._convert_mt5_bar_date_to_unix_nanos(bar, bar_type)
        return ts + pd.Timedelta(bar_type.spec.timedelta).value

    async def _mt5_bar_to_nautilus_bar(
        self,
        bar_type: BarType,
        bar: BarData,
        ts_init: int,
        is_revision: bool = False,
    ) -> Bar:
        """
        Convert MetaTrader 5 bar data to Nautilus Trader's bar type.

        Parameters
        ----------
        bar_type : BarType
            The type of the bar.
        bar : BarData
            The bar data received from MetaTrader 5.
        ts_init : int
            The unix nanosecond timestamp representing the bar's initialization time.
        is_revision : bool, optional
            Indicates whether the bar is a revision of an existing bar. Defaults to False.

        Returns
        -------
        Bar

        """
        instrument = self._cache.instrument(bar_type.instrument_id)
        if not instrument:
            raise ValueError(f"No cached instrument for {bar_type.instrument_id}")

        ts_event = await self._convert_mt5_bar_date_to_unix_nanos(bar, bar_type)
        return Bar(
            bar_type=bar_type,
            open=instrument.make_price(bar.open),
            high=instrument.make_price(bar.high),
            low=instrument.make_price(bar.low),
            close=instrument.make_price(bar.close),
            volume=instrument.make_qty(0 if bar.volume == -1 else bar.volume),
            ts_event=ts_event,
            ts_init=ts_init,
            is_revision=is_revision,
        )

    #
    # Send data to message bus
    #
    async def _handle_data(self, data: Data) -> None:
        """
        Handle and forward processed data to the appropriate destination. This method is
        a generic data handler that forwards processed market data, such as bars or
        ticks, to the DataEngine.process message bus endpoint.

        Parameters
        ----------
        data : Data
            The processed market data ready to be forwarded.

        """
        self._msgbus.send(endpoint="DataEngine.process", msg=data)

    #
    # Data Processors
    #
    async def _process_bar_data(
        self,
        bar_type_str: str,
        bar: BarData,
        handle_revised_bars: bool,
        historical: bool | None = False,
    ) -> Bar | None:
        """
        Process received bar data and convert it into Nautilus Trader's Bar format. This
        method determines whether the bar is new or a revision of an existing bar and
        converts the bar data to the Nautilus Trader's format.

        Parameters
        ----------
        bar_type_str : str
            The string representation of the bar type.
        bar : BarData
            The bar data received from MetaTrader 5.
        handle_revised_bars : bool
            Indicates whether revised bars should be handled or not.
        historical : bool | None, optional
            Indicates whether the bar data is historical. Defaults to False.

        Returns
        -------
        Bar | ``None``

        """
        previous_bar = self._bar_type_to_last_bar.get(bar_type_str)
        previous_ts = 0 if not previous_bar else int(previous_bar.time)
        current_ts = int(bar.time)

        if current_ts > previous_ts:
            is_new_bar = True
        elif current_ts == previous_ts:
            is_new_bar = False
        else:
            return None  # Out of sync

        self._bar_type_to_last_bar[bar_type_str] = bar
        bar_type: BarType = BarType.from_str(bar_type_str)
        ts_init = self._clock.timestamp_ns()
        if not handle_revised_bars:
            if previous_bar and is_new_bar:
                bar = previous_bar
            else:
                return None  # Wait for bar to close

            if historical:
                ts_init = await self._mt5_bar_to_ts_init(bar, bar_type)
                if ts_init >= self._clock.timestamp_ns():
                    return None  # The bar is incomplete

        # Process the bar
        return await self._mt5_bar_to_nautilus_bar(
            bar_type=bar_type,
            bar=bar,
            ts_init=ts_init,
            is_revision=not is_new_bar,
        )

    async def process_market_data_type(
        self, *, req_id: int, market_data_type: MarketDataTypeEnum
    ) -> None:
        """
        Return the market data type (real-time, frozen, delayed)
        of ticker sent by MT5Client::req_market_data_type when Terminal switches from real-time
        to frozen and back and to delayed and back too.
        """
        if market_data_type == MarketDataTypeEnum.REALTIME:
            self._log.debug(
                f"Market DataType is {MarketDataTypeEnum.to_str(market_data_type)}"
            )
        else:
            self._log.warning(
                f"Market DataType is {MarketDataTypeEnum.to_str(market_data_type)}"
            )

    async def process_tick_by_tick_bid_ask(
        self,
        *,
        req_id: int,
        time: int,
        bid_price: float,
        ask_price: float,
        bid_size: Decimal,
        ask_size: Decimal,
    ) -> None:
        """
        Return "BidAsk" tick-by-tick real-time tick data.
        """
        if not (subscription := self._subscriptions.get(req_id=req_id)):
            return

        if bid_price <= 0.0 or ask_price <= 0.0:
            self._log.debug(
                f"Discarding invalid QuoteTick (bid={bid_price}, ask={ask_price}) for req_id={req_id}."
            )
            return

        instrument_id = InstrumentId.from_str(subscription.name[0])
        instrument = self._cache.instrument(instrument_id)
        if instrument is None:
            self._log.warning(
                f"Instrument {instrument_id} not found in cache for req_id={req_id}. Skipping QuoteTick."
            )
            return
        ts_event = await self._convert_mt5_timestamp_to_pandas_timestamp(time)

        quote_tick = QuoteTick(
            instrument_id=instrument_id,
            bid_price=instrument.make_price(bid_price),
            ask_price=instrument.make_price(ask_price),
            bid_size=instrument.make_qty(bid_size),
            ask_size=instrument.make_qty(ask_size),
            ts_event=ts_event,
            ts_init=max(
                self._clock.timestamp_ns(), ts_event
            ),  # `ts_event` <= `ts_init`
        )

        await self._handle_data(quote_tick)

    async def process_tick_by_tick_all_last(
        self,
        *,
        req_id: int,
        time: int,
        last_price: float,
        volume: Decimal,
        volume_real: Decimal | float = 0,
    ) -> None:
        """Return AllLast / trade tick data from symbol_info_tick polling."""
        if not (subscription := self._subscriptions.get(req_id=req_id)):
            return

        if last_price <= 0.0:
            self._log.debug(
                f"Discarding invalid TradeTick (last={last_price}) for req_id={req_id}.",
            )
            return

        instrument_id = InstrumentId.from_str(subscription.name[0])
        instrument = self._cache.instrument(instrument_id)
        if instrument is None:
            self._log.warning(
                f"Instrument {instrument_id} not found in cache for req_id={req_id}. Skipping TradeTick.",
            )
            return

        ts_event = await self._convert_mt5_timestamp_to_pandas_timestamp(time)
        trade_qty = resolve_trade_tick_size(volume, volume_real)
        if trade_qty is None:
            self._log.debug(
                f"Discarding TradeTick without volume for req_id={req_id}.",
            )
            return
        trade_tick = TradeTick(
            instrument_id=instrument_id,
            price=instrument.make_price(last_price),
            size=instrument.make_qty(trade_qty),
            aggressor_side=resolve_trade_aggressor(0, map_from_tick_flags=False),
            trade_id=TradeId(str(time)),
            ts_event=ts_event,
            ts_init=max(self._clock.timestamp_ns(), ts_event),
        )
        await self._handle_data(trade_tick)

    async def process_realtime_bar(
        self,
        *,
        req_id: int,
        time: int,
        open_: float,
        high: float,
        low: float,
        close: float,
        volume: Decimal,
        spread=int,
        wap: Decimal,
        count: int,
    ) -> None:
        """
        Update real-time 60 second bars.

        TODO: Add spread to nautilus bar type
        """
        if not (subscription := self._subscriptions.get(req_id=req_id)):
            return
        bar_type = BarType.from_str(subscription.name)
        instrument = self._cache.instrument(bar_type.instrument_id)

        bar = Bar(
            bar_type=bar_type,
            open=instrument.make_price(open_),
            high=instrument.make_price(high),
            low=instrument.make_price(low),
            close=instrument.make_price(close),
            volume=instrument.make_qty(0 if volume == -1 else volume),
            ts_event=pd.Timestamp.fromtimestamp(time, tz=pytz.utc).value,
            ts_init=self._clock.timestamp_ns(),
            is_revision=False,
        )

        await self._handle_data(bar)

    async def process_historical_data(self, *, req_id: int, bar: BarData) -> None:
        """
        Return the requested historical data bars.
        """
        if request := self._requests.get(req_id=req_id):
            bar_type = request.name[0]
            bar = await self._mt5_bar_to_nautilus_bar(
                bar_type=bar_type,
                bar=bar,
                ts_init=await self._mt5_bar_to_ts_init(bar, bar_type),
            )
            if bar:
                request.result.append(bar)
        elif subscription := self._subscriptions.get(req_id=req_id):
            bar = await self._process_bar_data(
                bar_type_str=str(subscription.name),
                bar=bar,
                handle_revised_bars=False,
                historical=True,
            )
            if bar:
                await self._handle_data(bar)
        else:
            self._log.debug(f"Received {bar=} on {req_id=}")
            return

    async def process_historical_data_end(
        self, *, req_id: int, start: str, end: str
    ) -> None:
        """
        Mark the end of receiving historical bars.
        """
        self._end_request(req_id)

    async def process_historical_data_update(
        self, *, req_id: int, bar: BarData
    ) -> None:
        """
        Receive bars in real-time if keepUpToDate is set as True in reqHistoricalData.

        Similar to realTimeBars function, except returned data is a composite of
        historical data and real time data to keep charts up to date. Returned bars are
        successfully updated using real-time data.

        """
        if not (subscription := self._subscriptions.get(req_id=req_id)):
            return
        if not isinstance(subscription.handle, functools.partial):
            raise TypeError(
                f"Expecting partial type subscription method. {subscription=}"
            )
        if bar := await self._process_bar_data(
            bar_type_str=str(subscription.name),
            bar=bar,
            handle_revised_bars=subscription.handle.keywords.get(
                "handle_revised_bars", False
            ),
        ):
            if bar.is_single_price() and bar.open.as_double() == 0:
                self._log.debug(f"Ignoring Zero priced {bar=}")
            else:
                await self._handle_data(bar)

    async def process_historical_ticks_bid_ask(
        self,
        *,
        req_id: int,
        ticks: list,
        done: bool,
    ) -> None:
        """
        Return the requested historic bid/ask ticks.
        """
        if not done:
            return
        if request := self._requests.get(req_id=req_id):
            instrument_id = InstrumentId.from_str(request.name[0])
            instrument = self._cache.instrument(instrument_id)

            for tick in ticks:
                ts_event = pd.Timestamp.fromtimestamp(tick.time, tz=pytz.utc).value
                quote_tick = QuoteTick(
                    instrument_id=instrument_id,
                    bid_price=instrument.make_price(tick.priceBid),
                    ask_price=instrument.make_price(tick.priceAsk),
                    bid_size=instrument.make_qty(tick.sizeBid),
                    ask_size=instrument.make_qty(tick.sizeAsk),
                    ts_event=ts_event,
                    ts_init=ts_event,
                )
                request.result.append(quote_tick)

            self._end_request(req_id)

    async def get_price(self, symbol, tick_type="MidPoint"):
        """
        Request market data for a specific symbol and tick type.

        This method requests market data from MetaTrader 5 for the given
        symbol and tick type, waits for the response, and returns the result.

        Parameters
        ----------
        symbol : MT5Symbol
            The symbol details for which market data is requested.
        tick_type : str, optional
            The type of tick data to request (default is "MidPoint").

        Returns
        -------
        Any
            The market data result.

        Raises
        ------
        asyncio.TimeoutError
            If the request times out.

        """
        req_id = self._next_req_id()
        request = self._requests.add(
            req_id=req_id,
            name=f"{symbol.symbol}-{tick_type}",
            handle=functools.partial(
                self._mt5_client['mt5'].req_mkt_data,
                req_id,
                symbol,
                tick_type,
                False,
                False,
                [],
            ),
            cancel=functools.partial(self._mt5_client['mt5'].cancel_mkt_data, req_id),
        )
        request.handle()
        return await self._await_request(request, timeout=60)
