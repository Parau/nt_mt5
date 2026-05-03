import asyncio
import json
from decimal import Decimal
from typing import Any


from nautilus_mt5.data_types import CommissionReport
from nautilus_mt5.data_types import Execution
from nautilus_mt5.metatrader5.models import Order as MT5Order

from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock
from nautilus_trader.common.component import MessageBus
from nautilus_trader.core.correctness import PyCondition
from nautilus_trader.core.rust.common import LogColor
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.execution.messages import BatchCancelOrders
from nautilus_trader.execution.messages import CancelAllOrders
from nautilus_trader.execution.messages import CancelOrder
from nautilus_trader.execution.messages import ModifyOrder
from nautilus_trader.execution.messages import SubmitOrder
from nautilus_trader.execution.messages import SubmitOrderList
from nautilus_trader.execution.reports import ExecutionMassStatus
from nautilus_trader.execution.reports import FillReport
from nautilus_trader.execution.reports import OrderStatusReport
from nautilus_trader.execution.reports import PositionStatusReport
from nautilus_trader.live.execution_client import LiveExecutionClient

from nautilus_trader.execution.messages import GenerateOrderStatusReport
from nautilus_trader.execution.messages import GenerateOrderStatusReports
from nautilus_trader.execution.messages import GenerateFillReports
from nautilus_trader.execution.messages import GeneratePositionStatusReports

from nautilus_trader.model.enums import AccountType
from nautilus_trader.model.enums import LiquiditySide
from nautilus_trader.model.enums import OmsType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.enums import OrderStatus
from nautilus_trader.model.enums import OrderType
from nautilus_trader.model.enums import PositionSide
from nautilus_trader.model.enums import TimeInForce
from nautilus_trader.model.enums import TriggerType
from nautilus_trader.model.identifiers import AccountId
from nautilus_trader.model.identifiers import ClientId
from nautilus_trader.model.identifiers import ClientOrderId
from nautilus_trader.model.identifiers import TradeId
from nautilus_trader.model.identifiers import VenueOrderId
from nautilus_trader.model.instruments.base import Instrument
from nautilus_trader.model.objects import AccountBalance
from nautilus_trader.model.objects import Currency
from nautilus_trader.model.objects import MarginBalance
from nautilus_trader.model.objects import Money
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity
from nautilus_trader.model.orders.base import Order

from nautilus_mt5.client.client import MetaTrader5Client
from nautilus_mt5.data_types import MT5Position
from nautilus_mt5.constants import MT5_VENUE
from nautilus_mt5.config import MetaTrader5ExecClientConfig
from nautilus_mt5.parsing.execution import MT5_ORDER_TYPE_TO_ORDER_SIDE
from nautilus_mt5.parsing.execution import MT5_ORDER_TYPE_TO_ORDER_TYPE
from nautilus_mt5.parsing.execution import ORDER_TIME_SPECIFIED
from nautilus_mt5.parsing.execution import ORDER_TIME_SPECIFIED_DAY
from nautilus_mt5.parsing.execution import MAP_ORDER_STATUS
from nautilus_mt5.parsing.execution import MAP_TIME_IN_FORCE
from nautilus_mt5.parsing.execution import MAP_TRIGGER_METHOD
from nautilus_mt5.parsing.execution import TRADE_RETCODE_DONE
from nautilus_mt5.parsing.execution import TRADE_RETCODE_PLACED
from nautilus_mt5.parsing.execution import DEAL_TYPE_BUY
from nautilus_mt5.parsing.execution import timestring_to_timestamp
from nautilus_mt5.parsing.instruments import mt5_symbol_to_instrument_id_simplified_symbology
from nautilus_mt5.providers import MetaTrader5InstrumentProvider


mt5_to_nautilus_trigger_method = dict(
    zip(MAP_TRIGGER_METHOD.values(), MAP_TRIGGER_METHOD.keys(), strict=False),
)
mt5_to_nautilus_time_in_force = dict(
    zip(MAP_TIME_IN_FORCE.values(), MAP_TIME_IN_FORCE.keys(), strict=False),
)


class MetaTrader5ExecutionClient(LiveExecutionClient):
    """
    Provides an execution client for MetaTrader 5 Terminal API, allowing for the
    retrieval of account information and execution of orders.

    Parameters
    ----------
    loop : asyncio.AbstractEventLoop
        The event loop for the client.
    client : MetaTrader5Client
        The nautilus MetaTrader5Client.
    account_id: AccountId
        Account ID associated with this client.
    msgbus : MessageBus
        The message bus for the client.
    cache : Cache
        The cache for the client.
    clock : LiveClock
        The clock for the client.
    instrument_provider : MetaTrader5InstrumentProvider
        The instrument provider.
    config : MetaTrader5ExecClientConfig, optional
        The configuration for the instance.
    name : str, optional
        The custom client ID.

    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        client: MetaTrader5Client,
        account_id: AccountId,
        msgbus: MessageBus,
        cache: Cache,
        clock: LiveClock,
        instrument_provider: MetaTrader5InstrumentProvider,
        config: MetaTrader5ExecClientConfig,
        name: str | None = None,
    ) -> None:
        super().__init__(
            loop=loop,
            client_id=ClientId(name or f"{MT5_VENUE.value}"),
            venue=MT5_VENUE,
            oms_type=OmsType.HEDGING,
            instrument_provider=instrument_provider,
            account_type=AccountType.MARGIN,
            base_currency=None,  # MT5 accounts can be multi-currency | TODO: change this to USD
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            config=config,
        )
        self._client: MetaTrader5Client = client
        self._config: MetaTrader5ExecClientConfig = config
        self._set_account_id(account_id)
        self._account_summary_tags = {
            "NetLiquidation",
            "FullAvailableFunds",
            "FullInitMarginReq",
            "FullMaintMarginReq",
        }

        self._account_summary_loaded: asyncio.Event = asyncio.Event()

        # Hot caches
        self._account_summary: dict[str, dict[str, Any]] = {}

    @property
    def instrument_provider(self) -> MetaTrader5InstrumentProvider:
        return self._instrument_provider  # type: ignore

    async def _connect(self):
        # Connect client and wait for readiness
        await self._client._connect()
        self._client.registered_nautilus_clients.add(self.id)

        await self._client.wait_until_ready()
        await self.instrument_provider.initialize()

        # Event hooks
        account = self.account_id.get_id()
        self._client.subscribe_event(
            f"accountSummary-{account}", self._on_account_summary
        )
        self._client.subscribe_event(f"openOrder-{account}", self._on_open_order)
        self._client.subscribe_event(f"orderStatus-{account}", self._on_order_status)
        self._client.subscribe_event(f"execDetails-{account}", self._on_exec_details)

        # Load account balance
        self._client.subscribe_account_summary()
        # Synchronous account validation
        account_info = await self._client.get_account_info()
        if not account_info or not hasattr(account_info, "login"):
            raise RuntimeError("external_rpyc account_info invalid or login missing")

        expected_login = int(self._config.account_id)
        actual_login = int(getattr(account_info, "login", 0))

        if expected_login != actual_login:
            raise ConnectionError(
                f"external_rpyc execution account mismatch: "
                f"expected account {expected_login}, actual account {actual_login}"
            )

        # Load initial balances from the retrieved account_info
        if hasattr(account_info, 'balance'):
            self._log.debug(f"Initial balance: {account_info.balance}")
            # Mock sending a summary event locally to initialize states
            currency = getattr(account_info, 'currency', 'USD')
            self._on_account_summary("FullInitMarginReq", str(getattr(account_info, 'margin_initial', 0.0)), currency)
            self._on_account_summary("FullMaintMarginReq", str(getattr(account_info, 'margin_maintenance', 0.0)), currency)
            self._on_account_summary("NetLiquidation", str(getattr(account_info, 'equity', account_info.balance)), currency)
            self._on_account_summary("FullAvailableFunds", str(getattr(account_info, 'margin_free', 0.0)), currency)

        self._log.info(
            f"Account `{self.account_id.get_id()}` validated and associated with Terminal.",
            LogColor.GREEN,
        )
        self._set_connected(True)

    async def _disconnect(self):
        if self._config.cancel_on_stop:
            for order in self._cache.orders_open():
                venue_order_id = order.venue_order_id
                if venue_order_id:
                    try:
                        self._client.cancel_order(int(venue_order_id.value))
                    except Exception as e:
                        self._log.warning(
                            f"cancel-on-stop: failed to cancel order {venue_order_id}: {e}"
                        )
                else:
                    self._log.warning(
                        f"cancel-on-stop: no venue_order_id for {order.client_order_id}; skipping"
                    )

        if self._config.close_on_stop:
            await self._close_all_positions_on_stop()

        self._client.registered_nautilus_clients.discard(self.id)
        if (
            self._client.is_running
            and self._client.registered_nautilus_clients == set()
        ):
            self._client.stop()

    async def _close_all_positions_on_stop(self) -> None:
        """Send market close orders for every open MT5 position via the bridge."""
        try:
            mt5_raw = self._client._mt5_client.get("mt5")
            if not mt5_raw:
                self._log.warning("close-on-stop: no MT5 client available")
                return
            positions_fn = getattr(mt5_raw, "positions_get", None)
            order_send_fn = getattr(mt5_raw, "order_send", None)
            if not positions_fn or not order_send_fn:
                self._log.warning("close-on-stop: bridge missing positions_get or order_send")
                return
            open_positions = await asyncio.to_thread(positions_fn)
            if not open_positions:
                return
            for pos in open_positions:
                if isinstance(pos, dict):
                    ticket = int(pos.get("ticket", 0))
                    pos_type = int(pos.get("type", -1))
                    symbol = pos.get("symbol", "")
                    volume = float(pos.get("volume", 0.0))
                else:
                    ticket = int(getattr(pos, "ticket", 0))
                    pos_type = int(getattr(pos, "type", -1))
                    symbol = getattr(pos, "symbol", "")
                    volume = float(getattr(pos, "volume", 0.0))
                if not ticket or not symbol or volume <= 0:
                    continue
                # Close BUY (type=0) with SELL (1); close SELL (type=1) with BUY (0)
                close_order_type = 1 if pos_type == 0 else 0
                req = {
                    "action": 1,  # TRADE_ACTION_DEAL
                    "symbol": symbol,
                    "volume": volume,
                    "type": close_order_type,
                    "position": ticket,
                    "deviation": 20,
                    "magic": 234000,
                    "comment": "close on stop",
                    "type_filling": 2,  # ORDER_FILLING_RETURN
                }
                try:
                    await asyncio.to_thread(order_send_fn, req)
                    self._log.info(
                        f"close-on-stop: closed position {ticket} ({symbol} vol={volume})"
                    )
                except Exception as e:
                    self._log.warning(
                        f"close-on-stop: failed to close position {ticket} ({symbol}): {e}"
                    )
        except Exception as e:
            self._log.warning(f"close-on-stop: unexpected error: {e}")

    async def generate_order_status_report(self, command: GenerateOrderStatusReport) -> OrderStatusReport | None:
        instrument_id = command.instrument_id
        client_order_id = command.client_order_id
        venue_order_id = command.venue_order_id
        """
        Generate an `OrderStatusReport` for the given order identifier parameter(s). If
        the order is not found, or an error occurs, then logs and returns ``None``.

        Parameters
        ----------
        instrument_id : InstrumentId
            The instrument ID for the report.
        client_order_id : ClientOrderId, optional
            The client order ID for the report.
        venue_order_id : VenueOrderId, optional
            The venue order ID for the report.

        Returns
        -------
        OrderStatusReport or ``None``

        Raises
        ------
        ValueError
            If both the `client_order_id` and `venue_order_id` are ``None``.

        """
        PyCondition.type_or_none(client_order_id, ClientOrderId, "client_order_id")
        PyCondition.type_or_none(venue_order_id, VenueOrderId, "venue_order_id")
        if not (client_order_id or venue_order_id):
            self._log.debug(
                "Both `client_order_id` and `venue_order_id` cannot be None."
            )
            return None

        report = None
        mt5_orders = await self._client.get_open_orders(self.account_id.get_id())
        for mt5_order in mt5_orders:
            if (client_order_id and client_order_id.value == mt5_order.orderRef) or (
                venue_order_id
                and venue_order_id.value
                == str(
                    mt5_order.order_id,
                )
            ):
                report = await self._parse_mt5_order_to_order_status_report(mt5_order)
                break
        if report is None:
            self._log.warning(
                f"Order {client_order_id=}, {venue_order_id} not found, Cancelling...",
            )
            self._on_order_status(
                order_ref=client_order_id.value,
                order_status="Cancelled",
                reason="Not found in query",
            )
        return report

    async def _parse_mt5_order_to_order_status_report(
        self, mt5_order: MT5Order
    ) -> OrderStatusReport:
        self._log.debug(f"Trying OrderStatusReport for {mt5_order.__dict__}")
        instrument = await self.instrument_provider.find_with_symbol_id(
            mt5_order.symbol,
        )

        total_qty = (
            Quantity.from_int(0)
            if getattr(mt5_order, "volume", 0.0) == 0.0
            else Quantity.from_str(str(mt5_order.volume))
        )
        filled_qty = (
            Quantity.from_int(0)
            if getattr(mt5_order, "volume_filled", 0.0) == 0.0
            else Quantity.from_str(str(mt5_order.volume_filled))
        )
        if total_qty.as_double() > filled_qty.as_double() > 0:
            order_status = OrderStatus.PARTIALLY_FILLED
        else:
            order_status = MAP_ORDER_STATUS.get(getattr(mt5_order, "state", 0), OrderStatus.SUBMITTED)
        ts_init = self._clock.timestamp_ns()
        price = (
            None
            if getattr(mt5_order, "price", 0.0) == 0.0
            else instrument.make_price(getattr(mt5_order, "price", 0.0))
        )
        expire_time = (
            timestring_to_timestamp(getattr(mt5_order, "expire_time", ""))
            if getattr(mt5_order, "type_time", 0) in (ORDER_TIME_SPECIFIED, ORDER_TIME_SPECIFIED_DAY)
            and getattr(mt5_order, "expire_time", "")
            else None
        )

        mt5_type = getattr(mt5_order, "type", 0)
        order_side = MT5_ORDER_TYPE_TO_ORDER_SIDE.get(mt5_type, OrderSide.BUY)
        order_type = MT5_ORDER_TYPE_TO_ORDER_TYPE.get(mt5_type, OrderType.MARKET)

        time_in_force = TimeInForce.GTC # fallback
        # We map filling type back to TimeInForce if possible
        filling_type = getattr(mt5_order, "type_filling", 2)
        if filling_type == 0:
            time_in_force = TimeInForce.FOK
        elif filling_type == 1:
            time_in_force = TimeInForce.IOC

        order_status = OrderStatusReport(
            account_id=self.account_id,
            instrument_id=instrument.id,
            venue_order_id=VenueOrderId(str(mt5_order.order_id)),
            order_side=order_side,
            order_type=order_type,
            time_in_force=time_in_force,
            order_status=order_status,
            quantity=total_qty,
            filled_qty=Quantity.from_int(0),
            avg_px=Decimal(0),
            report_id=UUID4(),
            ts_accepted=ts_init,
            ts_last=ts_init,
            ts_init=ts_init,
            client_order_id=ClientOrderId(mt5_order.orderRef),
            # order_list_id=,
            # contingency_type=,
            expire_time=expire_time,
            price=price,
            trigger_price=instrument.make_price(getattr(mt5_order, "trigger_price", 0.0)),
            trigger_type=TriggerType.BID_ASK,
            # limit_offset=,
            # trailing_offset=,
        )
        self._log.debug(f"Received {order_status!r}")
        return order_status

    async def generate_order_status_reports(self, command: GenerateOrderStatusReports) -> list[OrderStatusReport]:
        instrument_id = command.instrument_id
        start = command.start
        end = command.end
        open_only = command.open_only
        """
        Generate a list of `OrderStatusReport`s with optional query filters. The
        returned list may be empty if no orders match the given parameters.

        Parameters
        ----------
        instrument_id : InstrumentId, optional
            The instrument ID query filter.
        start : pd.Timestamp, optional
            The start datetime (UTC) query filter.
        end : pd.Timestamp, optional
            The end datetime (UTC) query filter.
        open_only : bool, default False
            If the query is for open orders only.

        Returns
        -------
        list[OrderStatusReport]

        """
        report = []
        # Create the Filled OrderStatusReport from Open Positions
        positions: list[MT5Position] = await self._client.get_positions(
            self.account_id.get_id(),
        )
        if not positions:
            return []
        ts_init = self._clock.timestamp_ns()
        for position in positions:
            self._log.debug(
                f"Infer OrderStatusReport from open position {position.symbol}",
            )
            if position.quantity > 0:
                order_side = OrderSide.BUY
            elif position.quantity < 0:
                order_side = OrderSide.SELL
            else:
                continue  # Skip closed positions

            # Look up instrument from cache using symbol name
            from nautilus_mt5.data_types import MT5Symbol as _MT5Sym
            mt5_sym = _MT5Sym(symbol=position.symbol.symbol)
            pos_instrument_id = mt5_symbol_to_instrument_id_simplified_symbology(mt5_sym)
            instrument = self._cache.instrument(pos_instrument_id)
            if instrument is None:
                self._log.error(
                    f"Cannot generate report: instrument not found for symbol {position.symbol.symbol}",
                )
                continue

            avg_px = instrument.make_price(
                position.avg_cost / instrument.multiplier,
            ).as_decimal()
            quantity = Quantity.from_str(str(position.quantity.copy_abs()))
            order_status = OrderStatusReport(
                account_id=self.account_id,
                instrument_id=instrument.id,
                venue_order_id=VenueOrderId(instrument.id.value),
                order_side=order_side,
                order_type=OrderType.MARKET,
                time_in_force=TimeInForce.FOK,
                order_status=OrderStatus.FILLED,
                quantity=quantity,
                filled_qty=quantity,
                avg_px=avg_px,
                report_id=UUID4(),
                ts_accepted=ts_init,
                ts_last=ts_init,
                ts_init=ts_init,
                client_order_id=ClientOrderId(instrument.id.value),
            )
            self._log.debug(f"Received {order_status!r}")
            report.append(order_status)

        # Create the Open OrderStatusReport from Open Orders
        mt5_orders: list[MT5Order] = await self._client.get_open_orders(
            self.account_id.get_id(),
        )
        for mt5_order in mt5_orders:
            order_status = await self._parse_mt5_order_to_order_status_report(mt5_order)
            report.append(order_status)
        return report

    async def generate_fill_reports(self, command: GenerateFillReports) -> list[FillReport]:
        instrument_id = command.instrument_id
        venue_order_id = command.venue_order_id
        start = command.start
        end = command.end
        """
        Generate a list of `FillReport`s from MT5 historical deals (`history_deals_get`).

        Parameters
        ----------
        instrument_id : InstrumentId, optional
            Filter by instrument.
        venue_order_id : VenueOrderId, optional
            Filter by venue order ID (MT5 order ticket).
        start : pd.Timestamp, optional
            Start of the history window (UTC).
        end : pd.Timestamp, optional
            End of the history window (UTC).

        Returns
        -------
        list[FillReport]
        """
        import time as _time

        from_ts = int(start.timestamp()) if start is not None else 0
        to_ts = int(end.timestamp()) if end is not None else int(_time.time())

        raw_deals = await self._client.get_history_deals(from_ts=from_ts, to_ts=to_ts)
        if not raw_deals:
            return []

        ts_init = self._clock.timestamp_ns()
        reports: list[FillReport] = []

        for deal in raw_deals:
            if isinstance(deal, dict):
                _g = deal.get
            else:
                _g = lambda key, default=None: getattr(deal, key, default)  # noqa: E731

            deal_symbol = _g("symbol", "")
            deal_volume = float(_g("volume", 0.0))
            if not deal_symbol or deal_volume == 0.0:
                continue

            # Resolve instrument from cache using the symbol name
            from nautilus_mt5.data_types import MT5Symbol as _MT5Sym
            mt5_sym = _MT5Sym(symbol=deal_symbol)
            deal_instrument_id = mt5_symbol_to_instrument_id_simplified_symbology(mt5_sym)

            if instrument_id is not None and deal_instrument_id != instrument_id:
                continue

            deal_order = int(_g("order", 0))
            if venue_order_id is not None and str(deal_order) != venue_order_id.value:
                continue

            instrument = self._cache.instrument(deal_instrument_id)
            if instrument is None:
                self._log.warning(
                    f"Cannot generate FillReport for {deal_symbol}: instrument not in cache."
                )
                continue

            deal_type = int(_g("type", 0))
            deal_price = float(_g("price", 0.0))
            deal_ticket = int(_g("ticket", 0))
            deal_commission = float(_g("commission", 0.0))
            deal_time_msc = int(_g("time_msc", int(_g("time", 0)) * 1000))

            order_side = OrderSide.BUY if deal_type == DEAL_TYPE_BUY else OrderSide.SELL

            # Commission: MT5 reports negative values; FillReport expects a Money amount
            commission_currency = instrument.quote_currency
            commission_money = Money(abs(deal_commission), commission_currency)

            ts_event = deal_time_msc * 1_000_000  # milliseconds → nanoseconds

            report = FillReport(
                account_id=self.account_id,
                instrument_id=deal_instrument_id,
                venue_order_id=VenueOrderId(str(deal_order)),
                trade_id=TradeId(str(deal_ticket)),
                order_side=order_side,
                last_qty=instrument.make_qty(deal_volume),
                last_px=instrument.make_price(deal_price),
                commission=commission_money,
                liquidity_side=LiquiditySide.TAKER,
                report_id=UUID4(),
                ts_event=ts_event,
                ts_init=ts_init,
            )
            self._log.debug(f"Generated {report!r}")
            reports.append(report)

        return reports

    async def generate_position_status_reports(self, command: GeneratePositionStatusReports) -> list[PositionStatusReport]:
        instrument_id = command.instrument_id
        start = command.start
        end = command.end
        """
        Generate a list of `PositionStatusReport`s with optional query filters. The
        returned list may be empty if no positions match the given parameters.

        Parameters
        ----------
        instrument_id : InstrumentId, optional
            The instrument ID query filter.
        start : pd.Timestamp, optional
            The start datetime (UTC) query filter.
        end : pd.Timestamp, optional
            The end datetime (UTC) query filter.

        Returns
        -------
        list[PositionStatusReport]

        """
        report = []
        positions: list[MT5Position] | None = await self._client.get_positions(
            self.account_id.get_id(),
        )
        if not positions:
            return []
        for position in positions:
            self._log.debug(
                f"Trying PositionStatusReport for {position.symbol.symbol}"
            )
            if position.quantity > 0:
                side = PositionSide.LONG
            elif position.quantity < 0:
                side = PositionSide.SHORT
            else:
                continue  # Skip closed positions

            # Look up instrument from cache using symbol name
            from nautilus_mt5.data_types import MT5Symbol as _MT5Sym
            mt5_sym = _MT5Sym(symbol=position.symbol.symbol)
            pos_instrument_id = mt5_symbol_to_instrument_id_simplified_symbology(mt5_sym)

            if instrument_id is not None and pos_instrument_id != instrument_id:
                continue

            instrument = self._cache.instrument(pos_instrument_id)
            if instrument is None:
                self._log.error(
                    f"Cannot generate report: instrument not found for symbol {position.symbol.symbol}",
                )
                continue

            if not self._cache.instrument(instrument.id):
                self._handle_data(instrument)

            position_status = PositionStatusReport(
                account_id=self.account_id,
                instrument_id=instrument.id,
                position_side=side,
                quantity=Quantity.from_str(str(abs(position.quantity))),
                report_id=UUID4(),
                ts_last=self._clock.timestamp_ns(),
                ts_init=self._clock.timestamp_ns(),
            )
            self._log.debug(f"Received {position_status!r}")
            report.append(position_status)

        return report

    async def generate_mass_status(
        self,
        lookback_mins: int | None = None,
    ) -> ExecutionMassStatus | None:
        """
        Generate an `ExecutionMassStatus` report.

        MT5 does not expose a single mass-status endpoint. This method
        builds the report by aggregating the individual
        ``generate_order_status_reports``, ``generate_fill_reports``, and
        ``generate_position_status_reports`` calls.
        """
        import datetime as _dt

        now = _dt.datetime.now(_dt.timezone.utc)
        start = (now - _dt.timedelta(minutes=lookback_mins)) if lookback_mins is not None else None
        ts_init = self._clock.timestamp_ns()

        order_cmd = GenerateOrderStatusReports(
            instrument_id=None,
            start=start,
            end=now,
            open_only=False,
            command_id=UUID4(),
            ts_init=ts_init,
        )
        fill_cmd = GenerateFillReports(
            instrument_id=None,
            venue_order_id=None,
            start=start,
            end=now,
            command_id=UUID4(),
            ts_init=ts_init,
        )
        position_cmd = GeneratePositionStatusReports(
            instrument_id=None,
            start=start,
            end=now,
            command_id=UUID4(),
            ts_init=ts_init,
        )

        order_reports = await self.generate_order_status_reports(order_cmd)
        fill_reports = await self.generate_fill_reports(fill_cmd)
        position_reports = await self.generate_position_status_reports(position_cmd)

        mass_status = ExecutionMassStatus(
            client_id=self.id,
            account_id=self.account_id,
            venue=MT5_VENUE,
            report_id=UUID4(),
            ts_init=ts_init,
        )
        mass_status.add_order_reports(order_reports)
        mass_status.add_fill_reports(fill_reports)
        mass_status.add_position_reports(position_reports)

        self._log.info(
            f"generate_mass_status: {len(order_reports)} order(s), "
            f"{len(fill_reports)} fill(s), {len(position_reports)} position(s)."
        )
        return mass_status


    def _transform_order_to_mt5_order(
        self,
        order: Order,
        instrument: Instrument,
    ) -> MT5Order:
        from nautilus_mt5.parsing.execution import map_order_type_and_action, map_filling_type

        mt5_order = MT5Order()
        mt5_order.orderRef = order.client_order_id.value
        mt5_order.account = self.account_id.get_id()
        mt5_order.symbol = instrument.info["symbol"]["symbol"]
        mt5_order.volume = float(order.quantity.as_double())

        action, mt5_type = map_order_type_and_action(order.order_type, order.side)
        mt5_order.action = action
        mt5_order.type = mt5_type

        if order.order_type == OrderType.STOP_MARKET:
            # MT5 BUY_STOP / SELL_STOP: `price` is the stop trigger price.
            trigger = getattr(order, "trigger_price", None)
            mt5_order.price = float(trigger.as_double()) if trigger else 0.0
        elif order.order_type == OrderType.STOP_LIMIT:
            # MT5 BUY_STOP_LIMIT / SELL_STOP_LIMIT:
            #   `price`  = stop trigger price (when to activate the limit)
            #   `stoplimit` = limit price (the actual limit to fill at once triggered)
            trigger = getattr(order, "trigger_price", None)
            mt5_order.price = float(trigger.as_double()) if trigger else 0.0
            limit = getattr(order, "price", None)
            mt5_order.trigger_price = float(limit.as_double()) if limit else 0.0
        elif getattr(order, "price", None):
            mt5_order.price = float(order.price.as_double())
        else:
            mt5_order.price = 0.0

        mt5_order.type_filling = map_filling_type(order.time_in_force)
        mt5_order.type_time = 0 # ORDER_TIME_GTC default
        mt5_order.magic = 0
        mt5_order.comment = "NautilusOrder"

        return mt5_order

    async def _submit_order(self, command: SubmitOrder) -> None:

        PyCondition.type(command, SubmitOrder, "command")
        try:
            from nautilus_mt5.parsing.execution import validate_order_pre_venue
            validate_order_pre_venue(command.order.order_type, command.order.time_in_force)

            instrument = self._cache.instrument(command.order.instrument_id)
            mt5_order: MT5Order = self._transform_order_to_mt5_order(command.order, instrument)
            mt5_order.order_id = self._client.next_order_id()

            # Hedge account: for SELL orders, find the open BUY position ticket so MT5
            # closes it instead of opening a new opposite position.
            if command.order.side == OrderSide.SELL:
                mt5_symbol = instrument.info["symbol"]["symbol"]
                try:
                    open_positions = await asyncio.to_thread(
                        self._client._mt5_client["mt5"].positions_get, symbol=mt5_symbol
                    )
                    self._log.debug(
                        f"Hedge close: positions_get(symbol={mt5_symbol}) returned "
                        f"{len(open_positions) if open_positions else 0} positions, "
                        f"type={type(open_positions[0]).__name__ if open_positions else 'n/a'}"
                    )
                    if open_positions:
                        for pos in open_positions:
                            # pos may be a namedtuple netref or a dict depending on normalize_rpyc_return
                            if isinstance(pos, dict):
                                pos_type = pos.get("type", -1)
                                ticket = int(pos.get("ticket", 0))
                            else:
                                pos_type = int(getattr(pos, "type", -1))
                                ticket = int(getattr(pos, "ticket", 0))
                            if ticket and pos_type == 0:  # POSITION_TYPE_BUY = 0
                                mt5_order.position_ticket = ticket
                                self._log.debug(
                                    f"Hedge close: using position ticket {mt5_order.position_ticket} for SELL"
                                )
                                break
                except Exception as e:
                    self._log.warning(f"Could not fetch open positions for hedge close: {e}")

            result = self._client.place_order(mt5_order)
            self._handle_order_event(status=OrderStatus.SUBMITTED, order=command.order)

            # Interpret retcode: success → ACCEPTED; error → REJECTED
            if isinstance(result, dict):
                retcode = result.get("retcode", 0)
                if retcode in (TRADE_RETCODE_DONE, TRADE_RETCODE_PLACED):
                    venue_order_id = result.get("order", 0)
                    self._handle_order_event(
                        status=OrderStatus.ACCEPTED,
                        order=command.order,
                        order_id=venue_order_id,
                    )
                    # If the order was immediately filled (DONE + deal present), emit fill now.
                    if retcode == TRADE_RETCODE_DONE:
                        deal_id = result.get("deal", 0)
                        fill_price = result.get("price", 0.0)
                        fill_volume = result.get("volume", 0.0)
                        if deal_id and fill_price and fill_volume:
                            instrument = self._cache.instrument(command.order.instrument_id)
                            if instrument:
                                self.generate_order_filled(
                                    strategy_id=command.order.strategy_id,
                                    instrument_id=command.order.instrument_id,
                                    client_order_id=command.order.client_order_id,
                                    venue_order_id=VenueOrderId(str(venue_order_id)),
                                    venue_position_id=None,
                                    trade_id=TradeId(str(deal_id)),
                                    order_side=command.order.side,
                                    order_type=command.order.order_type,
                                    last_qty=instrument.make_qty(fill_volume),
                                    last_px=instrument.make_price(fill_price),
                                    quote_currency=instrument.quote_currency,
                                    commission=Money(0, instrument.quote_currency),
                                    liquidity_side=LiquiditySide.TAKER,
                                    ts_event=self._clock.timestamp_ns(),
                                )
                elif retcode != 0:
                    self._handle_order_event(
                        status=OrderStatus.REJECTED,
                        order=command.order,
                        reason=result.get("comment", f"MT5 retcode: {retcode}"),
                    )
        except ValueError as e:
            self._handle_order_event(
                status=OrderStatus.REJECTED,
                order=command.order,
                reason=str(e),
            )

    async def _submit_order_list(self, command: SubmitOrderList) -> None:
        PyCondition.type(command, SubmitOrderList, "command")

        # MT5 does not natively support contingent order lists (OTO/OCO/bracket).
        # The correct approach for SL/TP emulation is to use emulation_trigger on
        # child orders so the NT OrderEmulator handles contingency locally and
        # submits plain MARKET orders to this adapter when triggered.
        # See docs/execution_capability_matrix.md for supported order types.
        reason = (
            "MT5 adapter does not support order lists (bracket/OTO/OCO). "
            "Use emulation_trigger on child orders for SL/TP emulation via NT OrderEmulator."
        )
        self._log.warning(f"SubmitOrderList rejected: {reason}")
        for order in command.order_list.orders:
            self._handle_order_event(
                status=OrderStatus.REJECTED,
                order=order,
                reason=reason,
            )

    async def _modify_order(self, command: ModifyOrder) -> None:
        PyCondition.not_none(command, "command")
        if not (command.quantity or command.price or command.trigger_price):
            return

        nautilus_order: Order = self._cache.order(command.client_order_id)
        self._log.info(f"Nautilus order status is {nautilus_order.status_string()}")
        try:
            instrument = self._cache.instrument(nautilus_order.instrument_id)
            mt5_order: MT5Order = self._transform_order_to_mt5_order(nautilus_order, instrument)
        except ValueError as e:
            self._handle_order_event(
                status=OrderStatus.REJECTED,
                order=command.order,
                reason=str(e),
            )
            return

        mt5_order.order_id = int(command.venue_order_id.value)
        if mt5_order.parentId:
            parent_nautilus_order = self._cache.order(ClientOrderId(mt5_order.parentId))
            if parent_nautilus_order:
                mt5_order.parentId = int(parent_nautilus_order.venue_order_id.value)
            else:
                mt5_order.parentId = 0
        if command.quantity and command.quantity.as_double() != getattr(mt5_order, "volume", 0.0):
            mt5_order.volume = command.quantity.as_double()
        if command.price and command.price.as_double() != getattr(
            mt5_order, "price", None
        ):
            mt5_order.price = command.price.as_double()
        if command.trigger_price and command.trigger_price.as_double() != getattr(
            mt5_order,
            "trigger_price",
            None,
        ):
            mt5_order.trigger_price = command.trigger_price.as_double()
        self._log.info(f"Placing {mt5_order!r}")
        self._client.place_order(mt5_order)

    async def _cancel_order(self, command: CancelOrder) -> None:
        PyCondition.not_none(command, "command")

        venue_order_id = command.venue_order_id
        if venue_order_id:
            self._client.cancel_order(int(venue_order_id.value))
        else:
            self._log.error(f"VenueOrderId not found for {command.client_order_id}")

    async def _cancel_all_orders(self, command: CancelAllOrders) -> None:
        for order in self._cache.orders_open(
            instrument_id=command.instrument_id,
        ):
            venue_order_id = order.venue_order_id
            if venue_order_id:
                self._client.cancel_order(int(venue_order_id.value))
            else:
                self._log.error(f"VenueOrderId not found for {order.client_order_id}")

    async def _batch_cancel_orders(self, command: BatchCancelOrders) -> None:
        for order in command.cancels:
            await self._cancel_order(order)

    def _on_account_summary(self, tag: str, value: str, currency: str) -> None:
        if not self._account_summary.get(currency):
            self._account_summary[currency] = {}
        try:
            self._account_summary[currency][tag] = float(value)
        except ValueError:
            self._account_summary[currency][tag] = value

        for currency in self._account_summary:
            if not currency:
                continue
            if (
                self._account_summary_tags - set(self._account_summary[currency].keys())
                == set()
            ):
                self._log.info(f"{self._account_summary}", LogColor.GREEN)
                # free = self._account_summary[currency]["FullAvailableFunds"]
                locked = self._account_summary[currency]["FullMaintMarginReq"]
                total = self._account_summary[currency]["NetLiquidation"]
                # AccountBalance enforces total - locked == free >= 0.
                # When locked > total (e.g. extreme margin scenario), clamp locked
                # to total so free = 0 satisfies the invariant without fabricating data.
                if locked > total:
                    self._log.warning(
                        f"FullMaintMarginReq ({locked}) > NetLiquidation ({total}) "
                        "for currency {currency}; clamping locked to total so free=0."
                    )
                    locked = total
                free = total - locked
                account_balance = AccountBalance(
                    total=Money(total, Currency.from_str(currency)),
                    free=Money(free, Currency.from_str(currency)),
                    locked=Money(locked, Currency.from_str(currency)),
                )

                margin_balance = MarginBalance(
                    initial=Money(
                        self._account_summary[currency]["FullInitMarginReq"],
                        currency=Currency.from_str(currency),
                    ),
                    maintenance=Money(
                        self._account_summary[currency]["FullMaintMarginReq"],
                        currency=Currency.from_str(currency),
                    ),
                )

                self.generate_account_state(
                    balances=[account_balance],
                    margins=[margin_balance],
                    reported=True,
                    ts_event=self._clock.timestamp_ns(),
                )

                # Store all available fields to Cache (for now until permanent solution)
                self._cache.add(
                    f"accountSummary:{self.account_id.get_id()}",
                    json.dumps(self._account_summary).encode("utf-8"),
                )

        self._account_summary_loaded.set()

    def _handle_order_event(  # noqa: C901
        self,
        status: OrderStatus,
        order: Order,
        order_id: int | None = None,
        reason: str = "",
    ) -> None:
        if status == OrderStatus.SUBMITTED:
            self.generate_order_submitted(
                strategy_id=order.strategy_id,
                instrument_id=order.instrument_id,
                client_order_id=order.client_order_id,
                ts_event=self._clock.timestamp_ns(),
            )
        elif status == OrderStatus.ACCEPTED:
            if order.status != OrderStatus.ACCEPTED:
                self.generate_order_accepted(
                    strategy_id=order.strategy_id,
                    instrument_id=order.instrument_id,
                    client_order_id=order.client_order_id,
                    venue_order_id=VenueOrderId(str(order_id)),
                    ts_event=self._clock.timestamp_ns(),
                )
            else:
                self._log.debug(f"Order {order.client_order_id} already accepted.")
        elif status == OrderStatus.FILLED:
            if order.status != OrderStatus.FILLED:
                self._log.warning(
                    f"Order {order.client_order_id} reached FILLED via status callback "
                    "but fill details (price, qty, trade_id) are unavailable here. "
                    "The fill event must be emitted by _submit_order or _on_exec_details."
                )
        elif status == OrderStatus.PENDING_CANCEL:
            # TODO: self.generate_order_pending_cancel
            self._log.warning(f"Order {order.client_order_id} is {status.name}")
        elif status == OrderStatus.CANCELED:
            if order.status != OrderStatus.CANCELED:
                self.generate_order_canceled(
                    strategy_id=order.strategy_id,
                    instrument_id=order.instrument_id,
                    client_order_id=order.client_order_id,
                    venue_order_id=order.venue_order_id,
                    ts_event=self._clock.timestamp_ns(),
                )
        elif status == OrderStatus.REJECTED:
            if order.status != OrderStatus.REJECTED:
                self.generate_order_rejected(
                    strategy_id=order.strategy_id,
                    instrument_id=order.instrument_id,
                    client_order_id=order.client_order_id,
                    reason=reason,
                    ts_event=self._clock.timestamp_ns(),
                )
        else:
            self._log.warning(
                f"Order {order.client_order_id} with status={status.name} is unknown or "
                "not yet implemented.",
            )

    async def handle_order_status_report(self, mt5_order: MT5Order) -> None:
        report = await self._parse_mt5_order_to_order_status_report(mt5_order)
        self._send_order_status_report(report)

    def _on_open_order(
        self, order_ref: str, order: MT5Order
    ) -> None:
        if not order.orderRef:
            self._log.warning(
                f"ClientOrderId not available, order={order.__dict__}",
            )
            return
        if not (nautilus_order := self._cache.order(ClientOrderId(order_ref))):
            self.create_task(self.handle_order_status_report(order))
            return

        if getattr(order, "state", 0) in [0, 1]:  # ORDER_STATE_STARTED, ORDER_STATE_PLACED
            instrument = self.instrument_provider.find(nautilus_order.instrument_id)
            total_qty = (
                Quantity.from_int(0)
                if getattr(order, "volume", 0.0) == 0.0
                else Quantity.from_str(str(order.volume))
            )
            price = (
                None
                if getattr(order, "price", 0.0) == 0.0
                else instrument.make_price(getattr(order, "price", 0.0))
            )
            trigger_price = (
                None
                if getattr(order, "trigger_price", 0.0) == 0.0
                else instrument.make_price(getattr(order, "trigger_price", 0.0))
            )
            venue_order_id_modified = bool(
                nautilus_order.venue_order_id is None
                or nautilus_order.venue_order_id != VenueOrderId(str(order.order_id)),
            )

            if total_qty != nautilus_order.quantity or price or trigger_price:
                self.generate_order_updated(
                    strategy_id=nautilus_order.strategy_id,
                    instrument_id=nautilus_order.instrument_id,
                    client_order_id=nautilus_order.client_order_id,
                    venue_order_id=VenueOrderId(str(order.order_id)),
                    quantity=total_qty,
                    price=price,
                    trigger_price=trigger_price,
                    ts_event=self._clock.timestamp_ns(),
                    venue_order_id_modified=venue_order_id_modified,
                )
            self._handle_order_event(
                status=OrderStatus.ACCEPTED,
                order=nautilus_order,
                order_id=order.order_id,
            )

    def _on_order_status(
        self, order_ref: str, order_status: str, reason: str = ""
    ) -> None:
        if order_status in ["ApiCancelled", "Cancelled"]:
            status = OrderStatus.CANCELED
        elif order_status == "PendingCancel":
            status = OrderStatus.PENDING_CANCEL
        elif order_status == "Rejected":
            status = OrderStatus.REJECTED
        elif order_status == "Filled":
            status = OrderStatus.FILLED
        elif order_status == "Inactive":
            self._log.warning(
                f"Order status is 'Inactive' because it is invalid or triggered an error for {order_ref=}",
            )
            return
        elif order_status in ["PreSubmitted", "Submitted"]:
            self._log.debug(
                f"Ignoring `_on_order_status` event for {order_status=} is handled in `_on_open_order`",
            )
            return
        else:
            self._log.warning(
                f"Unknown {order_status=} received on `_on_order_status` for {order_ref=}",
            )
            return

        nautilus_order = self._cache.order(ClientOrderId(order_ref))
        if nautilus_order:
            self._handle_order_event(
                status=status,
                order=nautilus_order,
                reason=reason,
            )
        else:
            self._log.warning(f"ClientOrderId {order_ref} not found in Cache")

    def _on_exec_details(
        self,
        order_ref: str,
        execution: Execution,
        commission_report: CommissionReport,
    ) -> None:
        if not str(execution.order_id):
            self._log.warning(
                f"ClientOrderId not available, order={execution.__dict__}"
            )
            return
        if not (nautilus_order := self._cache.order(ClientOrderId(order_ref))):
            self._log.warning(
                f"ClientOrderId not found in Cache, order={execution.__dict__}"
            )
            return

        instrument = self.instrument_provider.find(nautilus_order.instrument_id)

        if instrument:
            # We map DEAL_TYPE_BUY/SELL from MT5 execution report side
            from nautilus_mt5.parsing.execution import DEAL_TYPE_BUY
            side_int = getattr(execution, "side", DEAL_TYPE_BUY)
            order_side = OrderSide.BUY if side_int == DEAL_TYPE_BUY else OrderSide.SELL

            self.generate_order_filled(
                strategy_id=nautilus_order.strategy_id,
                instrument_id=nautilus_order.instrument_id,
                client_order_id=nautilus_order.client_order_id,
                venue_order_id=VenueOrderId(str(execution.order_id)),
                venue_position_id=None,
                trade_id=TradeId(execution.exec_id),
                order_side=order_side,
                order_type=nautilus_order.order_type,
                last_qty=Quantity(
                    execution.quantity, precision=instrument.size_precision
                ),
                last_px=Price(execution.price, precision=instrument.price_precision),
                quote_currency=instrument.quote_currency,
                commission=Money(
                    commission_report.commission,
                    Currency.from_str(commission_report.currency),
                ),
                liquidity_side=LiquiditySide.NO_LIQUIDITY_SIDE,
                ts_event=timestring_to_timestamp(execution.time).value,
            )
