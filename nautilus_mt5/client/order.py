from decimal import Decimal

from nautilus_mt5.data_types import CommissionReport, Execution, AccountOrderRef
from nautilus_trader.model.identifiers import Symbol
from nautilus_mt5.metatrader5.models import Order as MT5Order

from nautilus_mt5.common import BaseMixin

from nautilus_trader.common.enums import LogColor


class MetaTrader5ClientOrderMixin(BaseMixin):
    """
    Manages orders for the MetaTrader5Client.

    This class enables the execution and management of trades. It maintains an internal
    state that tracks the relationship between Nautilus orders and MT5 API orders,
    ensuring that actions such as placing, modifying, and canceling orders are correctly
    reflected in both systems.

    """

    def place_order(self, order: MT5Order) -> None:
        """
        Place an order through the MT5Client.

        Parameters
        ----------
        order : MT5Order
            The order object containing details such as the order ID, symbol
            details, and order specifics.

        """
        self._order_id_to_order_ref[order.order_id] = AccountOrderRef(
            account_id=order.account,
            order_id=order.orderRef.rsplit(":", 1)[0] if getattr(order, "orderRef", None) else str(order.order_id),
        )
        if getattr(order, "orderRef", None):
            order.orderRef = f"{order.orderRef}:{order.order_id}"

        send_method = getattr(self._mt5_client["mt5"], "order_send", None)
        if send_method:
            if send_method.__name__ == "order_send":
                req = {
                    "action": getattr(order, "action", 1), # TRADE_ACTION_DEAL
                    "symbol": getattr(order, "symbol", ""),
                    "volume": float(getattr(order, "volume", 0.0)),
                    "type": getattr(order, "type", 0), # ORDER_TYPE_BUY/SELL
                    "price": getattr(order, "price", 0.0),
                    "sl": getattr(order, "sl", 0.0),
                    "tp": getattr(order, "tp", 0.0),
                    "deviation": getattr(order, "deviation", 20),
                    "magic": getattr(order, "magic", 234000),
                    "comment": getattr(order, "comment", "python script open"),
                    "type_time": getattr(order, "type_time", 0), # ORDER_TIME_GTC
                    "type_filling": getattr(order, "type_filling", 2), # ORDER_FILLING_RETURN (Default)
                }
                res = send_method(req)
                self._log.info(f"MT5 order_send RESULT: {res}")
            else:
                res = send_method(order.order_id, order.symbol, order)
                self._log.info(f"MT5 order_send RESULT: {res}")
        else:
            self._log.warning("MT5Client has no method to send orders. (Missing order_send)")

    def place_order_list(self, orders: list[MT5Order]) -> None:
        """
        Place a list of orders through the EClient.

        Parameters
        ----------
        orders : list[MT5Order]
            A list of order objects to be placed.

        """
        for order in orders:
            order.orderRef = f"{order.orderRef}:{order.order_id}"
            self._mt5_client["mt5"].order_send(order)

    def cancel_order(self, order_id: int, manual_cancel_order_time: str = "") -> None:
        """
        Cancel an order through the MT5Client.

        Parameters
        ----------
        order_id : int
            The unique identifier for the order to be canceled (ticket).
        """
        send_method = getattr(self._mt5_client['mt5'], "order_send", None)
        if send_method:
            req = {
                "action": 8, # TRADE_ACTION_REMOVE
                "order": int(order_id),
            }
            res = send_method(req)
            self._log.info(f"MT5 order_send RESULT (CANCEL): {res}")
        else:
            self._log.warning("MT5Client has no method to send cancel orders. (Missing order_send)")

    def cancel_all_orders(self) -> None:
        """
        Request to cancel all open orders through the MT5Client.
        """
        self._log.warning(
            "Canceling all open orders, regardless of how they were originally placed.",
        )
        self._log.warning("MT5 does not natively support reqGlobalCancel. You must iterate open positions/orders and cancel individually.")

    async def get_open_orders(self, account_id: str) -> list[MT5Order]:
        """
        Retrieve a list of open orders for a specific account. Once the request is
        completed, openOrderEnd() will be called.

        Parameters
        ----------
        account_id : str
            The account identifier for which to retrieve open orders.

        Returns
        -------
        list[MT5Order]

        """
        self._log.debug(f"Requesting open orders for {account_id}")
        name = "OpenOrders"
        if not (request := self._requests.get(name=name)):
            request = self._requests.add(
                req_id=self._next_req_id(),
                name=name,
                handle=getattr(self._mt5_client["mt5"], "orders_get", None),
            )
            if not request:
                return []
            request.handle()

        all_orders: list[MT5Order] | None = await self._await_request(request, 30)
        if all_orders:
            orders: list[MT5Order] = [
                order for order in all_orders if order.account == account_id
            ]
        else:
            orders = []

        return orders

    def next_order_id(self) -> int:
        """
        Retrieve the next valid order ID to be used for a new order.

        Returns
        -------
        int

        """
        order_id: int = self._next_valid_order_id
        self._next_valid_order_id += 1
        self._mt5_client['mt5'].req_ids()
        return order_id

    async def process_next_valid_id(self, *, order_id: int) -> None:
        """
        Receive the next valid order id.

        Will be invoked automatically upon successful API client connection,
        or after call to MT5Client::req_ids
        Important: the next valid order ID is only valid at the time it is received.

        """
        self._next_valid_order_id = max(self._next_valid_order_id, order_id, 101)
        if self.accounts() and not self._is_mt5_connected.is_set():
            self._log.debug("`_is_mt5_connected` set by `nextValidId`.", LogColor.BLUE)
            self._is_mt5_connected.set()

    async def process_open_order(
        self,
        *,
        order_id: int,
        symbol: Symbol,
        order: MT5Order,
    ) -> None:
        """
        Feed in currently open orders.
        """
        order.symbol = symbol.symbol if hasattr(symbol, "symbol") else str(symbol)
        order.orderRef = order.orderRef.rsplit(":", 1)[0] if order.orderRef else str(order.order_id)

        # Handle response to on-demand request
        if request := self._requests.get(name="OpenOrders"):
            request.result.append(order)
            # Validate and add reverse mapping, if not exists
            if order_ref := self._order_id_to_order_ref.get(order.order_id):
                if not (
                    order_ref.account_id == order.account
                    and order_ref.order_id == order.orderRef
                ):
                    self._log.warning(
                        f"Discrepancy found in order, expected {order_ref}, "
                        f"was (account={order.account}, order_id={order.orderRef}",
                    )
            else:
                self._order_id_to_order_ref[order.order_id] = AccountOrderRef(
                    account_id=order.account,
                    order_id=order.orderRef,
                )
            return

        # Handle event based response
        name = f"openOrder-{order.account}"
        if handler := self._event_subscriptions.get(name, None):
            handler(
                order_ref=order.orderRef.rsplit(":", 1)[0],
                order=order,
            )

    async def process_open_order_end(self) -> None:
        """
        Notifies the end of the open orders' reception.
        """
        if request := self._requests.get(name="OpenOrders"):
            self._end_request(request.req_id)

    async def process_order_status(
        self,
        *,
        order_id: int,
        status: str,
        filled: Decimal,
        remaining: Decimal,
        avg_fill_price: float,
        perm_id: int,
        parent_id: int,
        last_fill_price: float,
        client_id: int,
        why_held: str,
        mkt_cap_price: float,
    ) -> None:
        """
        Get the up-to-date information of an order every time it changes.

        Note: Often there are duplicate orderStatus messages.

        """
        order_ref = self._order_id_to_order_ref.get(order_id, None)
        if order_ref:
            name = f"orderStatus-{order_ref.account_id}"
            if handler := self._event_subscriptions.get(name, None):
                handler(
                    order_ref=self._order_id_to_order_ref[order_id].order_id,
                    order_status=status,
                )

    async def process_exec_details(
        self,
        *,
        req_id: int,
        contract: Symbol,
        execution: Execution,
    ) -> None:
        """
        Provide the executions that happened in the prior 24 hours.
        """
        if not (cache := self._exec_id_details.get(execution.execId, None)):
            self._exec_id_details[execution.execId] = {}
            cache = self._exec_id_details[execution.execId]
        cache["execution"] = execution
        cache["order_ref"] = str(execution.order_id).rsplit(":", 1)[0]

        name = f"execDetails-{execution.acctNumber}"
        if (handler := self._event_subscriptions.get(name, None)) and cache.get(
            "commission_report",
        ):
            handler(
                order_ref=cache["order_ref"],
                execution=cache["execution"],
                commission_report=cache["commission_report"],
            )
            cache.pop(execution.execId, None)

    async def process_commission_report(
        self,
        *,
        commission_report: CommissionReport,
    ) -> None:
        """
        Provide the CommissionReport of an Execution.
        """
        if not (cache := self._exec_id_details.get(commission_report.execId, None)):
            self._exec_id_details[commission_report.execId] = {}
            cache = self._exec_id_details[commission_report.execId]
        cache["commission_report"] = commission_report

        if cache.get("execution") and (
            account := getattr(cache["execution"], "acctNumber", None)
        ):
            name = f"execDetails-{account}"
            if handler := self._event_subscriptions.get(name, None):
                handler(
                    order_ref=cache["order_ref"],
                    execution=cache["execution"],
                    commission_report=cache["commission_report"],
                )
                cache.pop(commission_report.execId, None)
