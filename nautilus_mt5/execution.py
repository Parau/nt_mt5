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
from nautilus_mt5.parsing.execution import MAP_ORDER_ACTION
from nautilus_mt5.parsing.execution import MAP_ORDER_STATUS
from nautilus_mt5.parsing.execution import MAP_ORDER_TYPE
from nautilus_mt5.parsing.execution import MAP_TIME_IN_FORCE
from nautilus_mt5.parsing.execution import MAP_TRIGGER_METHOD
from nautilus_mt5.parsing.execution import ORDER_SIDE_TO_ORDER_ACTION
from nautilus_mt5.parsing.execution import timestring_to_timestamp
from nautilus_mt5.providers import MetaTrader5InstrumentProvider


mt5_to_nautilus_trigger_method = dict(
    zip(MAP_TRIGGER_METHOD.values(), MAP_TRIGGER_METHOD.keys(), strict=False),
)
mt5_to_nautilus_time_in_force = dict(
    zip(MAP_TIME_IN_FORCE.values(), MAP_TIME_IN_FORCE.keys(), strict=False),
)
mt5_to_nautilus_order_side = dict(
    zip(MAP_ORDER_ACTION.values(), MAP_ORDER_ACTION.keys(), strict=False),
)
mt5_to_nautilus_order_type = dict(
    zip(MAP_ORDER_TYPE.values(), MAP_ORDER_TYPE.keys(), strict=False)
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
        The nautilus MetaTrader5Client using ibapi.
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
            oms_type=OmsType.NETTING,
            instrument_provider=instrument_provider,
            account_type=AccountType.MARGIN,
            base_currency=None,  # IB accounts are multi-currency | TODO: change this to USD
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            config=config,
        )
        self._client: MetaTrader5Client = client
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
        if not account_info:
            raise ConnectionError("Failed to retrieve account info from MT5 bridge.")

        expected_login = int(self.config.account_id)
        actual_login = int(getattr(account_info, "login", 0))

        if expected_login != actual_login:
            raise ConnectionError(f"Account mismatch. Expected: {expected_login}, Actual logged in: {actual_login}")

        # Load initial balances from the retrieved account_info
        if hasattr(account_info, 'balance'):
            self._log.debug(f"Initial balance: {account_info.balance}")
            # Mock sending a summary event locally to initialize states
            currency = getattr(account_info, 'currency', 'USD')
            self._on_account_summary("FullInitMarginReq", str(getattr(account_info, 'margin_initial', 0.0)), currency)
            self._on_account_summary("FullMaintMarginReq", str(getattr(account_info, 'margin_maintenance', 0.0)), currency)
            self._on_account_summary("NetLiquidation", str(getattr(account_info, 'equity', account_info.balance)), currency)

        self._log.info(
            f"Account `{self.account_id.get_id()}` validated and associated with Terminal.",
            LogColor.GREEN,
        )

    async def _disconnect(self):
        self._client.registered_nautilus_clients.discard(self.id)
        if (
            self._client.is_running
            and self._client.registered_nautilus_clients == set()
        ):
            self._client.stop()

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
            if getattr(mt5_order, "type_time", 0) == 1 # ORDER_TIME_SPECIFIED
            and getattr(mt5_order, "expire_time", "")
            else None
        )

        mapped_order_type_info = mt5_to_nautilus_order_type.get(getattr(mt5_order, "type", 0), OrderType.MARKET)
        if isinstance(mapped_order_type_info, tuple):
            order_type, time_in_force = mapped_order_type_info
        else:
            order_type = mapped_order_type_info
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
            order_side=mt5_to_nautilus_order_side[mt5_order.action],
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
                f"Infer OrderStatusReport from open position {position.symbol.__dict__}",
            )
            if position.quantity > 0:
                order_side = OrderSide.BUY
            elif position.quantity < 0:
                order_side = OrderSide.SELL
            else:
                continue  # Skip, IB may continue to display closed positions

            instrument = await self.instrument_provider.find_with_symbol_id(
                position.symbol.symbol,
            )
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
        Generate a list of `FillReport`s with optional query filters. The returned list
        may be empty if no trades match the given parameters.

        Parameters
        ----------
        instrument_id : InstrumentId, optional
            The instrument ID query filter.
        venue_order_id : VenueOrderId, optional
            The venue order ID (assigned by the venue) query filter.
        start : pd.Timestamp, optional
            The start datetime (UTC) query filter.
        end : pd.Timestamp, optional
            The end datetime (UTC) query filter.

        Returns
        -------
        list[FillReport]

        """
        self._log.warning("Cannot generate `list[FillReport]`: not yet implemented.")

        return []  # TODO: Implement

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
                continue  # Skip, IB may continue to display closed positions

            instrument = await self.instrument_provider.find_with_symbol_id(
                position.symbol.symbol,
            )
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


    def _transform_order_to_mt5_order(
        self,
        order: Order,
        instrument: Instrument,
    ) -> MT5Order:
        from nautilus_mt5.parsing.execution import map_order_type_and_action, map_filling_type

        mt5_order = MT5Order()
        mt5_order.orderRef = order.client_order_id.value
        mt5_order.account = self.client_id.value
        mt5_order.symbol = instrument.info["symbol"]["symbol"]
        mt5_order.volume = float(order.quantity.as_double())

        action, mt5_type = map_order_type_and_action(order.type, order.side)
        mt5_order.action = action
        mt5_order.type = mt5_type

        if order.price:
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
            instrument = self._cache.instrument(command.order.instrument_id)
            mt5_order: MT5Order = self._transform_order_to_mt5_order(command.order, instrument)
            mt5_order.order_id = self._client.next_order_id()
            self._client.place_order(mt5_order)
            self._handle_order_event(status=OrderStatus.SUBMITTED, order=command.order)
        except ValueError as e:
            self._handle_order_event(
                status=OrderStatus.REJECTED,
                order=command.order,
                reason=str(e),
            )

    async def _submit_order_list(self, command: SubmitOrderList) -> None:
        PyCondition.type(command, SubmitOrderList, "command")

        order_id_map = {}
        client_id_to_orders = {}
        mt5_orders = []

        # Translate orders
        for order in command.order_list.orders:
            order_id_map[order.client_order_id.value] = self._client.next_order_id()
            client_id_to_orders[order.client_order_id.value] = order

            try:
                instrument = self._cache.instrument(order.instrument_id)
                mt5_order = self._transform_order_to_mt5_order(order, instrument)
                mt5_order.transmit = False
                mt5_order.order_id = order_id_map[order.client_order_id.value]
                mt5_orders.append(mt5_order)
            except ValueError as e:
                # All orders in the list are declined to prevent unintended side effects
                for o in command.order_list.orders:
                    if o == order:
                        self._handle_order_event(
                            status=OrderStatus.REJECTED,
                            order=command.order,
                            reason=str(e),
                        )
                    else:
                        self._handle_order_event(
                            status=OrderStatus.REJECTED,
                            order=command.order,
                            reason=f"The order has been rejected due to the rejection of the order with "
                            f"{order.client_order_id!r} in the list",
                        )
                return

        # Mark last order to transmit
        mt5_orders[-1].transmit = True

        for mt5_order in mt5_orders:
            # Map the Parent Order Ids
            if parent_id := order_id_map.get(mt5_order.parentId):
                mt5_order.parentId = parent_id
            # Place orders
            order_ref = mt5_order.orderRef
            self._client.place_order(mt5_order)
            self._handle_order_event(
                status=OrderStatus.SUBMITTED,
                order=client_id_to_orders[order_ref],
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
                if total - locked < locked:
                    total = 400000  # TODO: Bug; Cannot recalculate balance when no current balance
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
                # TODO: self.generate_order_filled
                self._log.debug(f"Order {order.client_order_id} is filled.")
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
            self.generate_order_filled(
                strategy_id=nautilus_order.strategy_id,
                instrument_id=nautilus_order.instrument_id,
                client_order_id=nautilus_order.client_order_id,
                venue_order_id=VenueOrderId(str(execution.order_id)),
                venue_position_id=None,
                trade_id=TradeId(execution.exec_id),
                order_side=OrderSide[ORDER_SIDE_TO_ORDER_ACTION[getattr(execution, "side", "BUY")]],
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
