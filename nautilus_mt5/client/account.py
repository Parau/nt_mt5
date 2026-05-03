import asyncio
from decimal import Decimal
import functools
from typing import Any, Tuple

from nautilus_trader.common.enums import LogColor
from nautilus_trader.model.position import Position

from nautilus_mt5.common import BaseMixin
from nautilus_mt5.data_types import MT5Position, MT5Symbol


class MetaTrader5ClientAccountMixin(BaseMixin):
    """
    Handles various account and position related requests for the
    MetaTrader5Client.

    Parameters
    ----------
    client : MetaTrader5Client
        The client instance that will be used to communicate with the Terminal API.

    """

    def accounts(self) -> set[str]:
        """
        Return a set of account identifiers managed by this instance.

        Returns
        -------
        set[str]

        """
        return self._account_ids.copy()

    async def get_account_info(self) -> Any:
        """
        Retrieve information about the current trading account.

        Returns
        -------
        Any
        """
        import rpyc
        from types import SimpleNamespace
        try:
            res = await asyncio.to_thread(self._mt5_client['mt5'].account_info)
            if res is None:
                return None

            # Obtain local copy if it's an RPyC netref
            res_local = rpyc.classic.obtain(res)

            if isinstance(res_local, dict):
                return SimpleNamespace(**res_local)
            return res_local
        except Exception as e:
            self._log.warning(f"Error fetching account info: {e}")
            return None

    def subscribe_account_summary(self) -> None:
        """
        Subscribe to the account summary for all accounts.

        It sends a request to MetaTrader 5 to retrieve account summary
        information.

        """

        name = "accountSummary"
        if not (subscription := self._subscriptions.get(name=name)):
            req_id = self._next_req_id()

            # Hack for missing real-time account stream method in MetaTrader5 client
            req_func = getattr(self._mt5_client['mt5'], "req_account_summary", getattr(self._mt5_client['mt5'], "account_info", lambda *args, **kwargs: None))
            cancel_func = getattr(self._mt5_client['mt5'], "cancel_account_summary", lambda *args, **kwargs: None)

            subscription = self._subscriptions.add(
                req_id=req_id,
                name=name,
                handle=functools.partial(
                    req_func,
                    req_id=req_id,
                ) if "req_account_summary" in str(req_func) else req_func,
                cancel=functools.partial(
                    cancel_func,
                    req_id=req_id,
                ) if "cancel_account_summary" in str(cancel_func) else cancel_func,
            )

        if not subscription:
            return

        subscription.handle()

    def unsubscribe_account_summary(self, account_id: str) -> None:
        """
        Unsubscribe from the account summary for the specified account.

        Parameters
        ----------
        account_id : str
            The identifier of the account to unsubscribe from.

        """
        name = "accountSummary"
        if subscription := self._subscriptions.get(name=name):
            self._subscriptions.remove(subscription.req_id)
            cancel_func = getattr(self._mt5_client['mt5'], "cancel_account_summary", None)
            if cancel_func:
                cancel_func(req_id=subscription.req_id)
            else:
                self._log.warning("No method found to cancel account summary.")
            self._log.debug(f"Unsubscribed from {subscription}")
        else:
            self._log.debug(f"Subscription doesn't exist for {name}")

    async def get_positions(self, account_id: str) -> list[Position] | None:
        """
        Fetch open positions for a specified account.

        Parameters
        ----------
        account_id: str
            The account identifier for which to fetch positions.

        Returns
        -------
        list[Position] | ``None``

        """
        self._log.debug(f"Requesting Open Positions for {account_id}")
        name = "OpenPositions"
        if not (request := self._requests.get(name=name)):
            async def _fetch():
                import rpyc
                try:
                    res = await asyncio.to_thread(self._mt5_client['mt5'].positions_get, group=f"*{account_id}*")
                    if res is None:
                        return []
                    # obtain local copy to avoid Netrefs
                    res_local = rpyc.classic.obtain(res)
                    return res_local
                except Exception as e:
                    self._log.warning(f"Error fetching positions: {e}")
                    return []

            request = self._requests.add(
                req_id=self._next_req_id(),
                name=name,
                handle=lambda: asyncio.create_task(_fetch())
            )
            if not request:
                return None

            # Executa e assina no Future a saida da lambda async
            task = request.handle()
            task.add_done_callback(
                lambda t: self._loop.call_soon_threadsafe(request.future.set_result, t.result() if not t.exception() else [])
            )

            all_positions = await self._await_request(request, 30)
        else:
            all_positions = await self._await_request(request, 30)
        if not all_positions:
            return None
        positions = []
        for pos in all_positions:
            if isinstance(pos, dict):
                # Raw dict from EXTERNAL_RPYC direct bridge call — convert to MT5Position.
                symbol_str = pos.get("symbol", "")
                if not symbol_str:
                    continue
                pos_type = pos.get("type", 0)  # 0=BUY, 1=SELL
                volume = Decimal(str(pos.get("volume", 0.0)))
                quantity = volume if pos_type == 0 else -volume
                avg_cost = float(pos.get("price_open", 0.0))
                commission = float(pos.get("commission", 0.0))
                symbol = MT5Symbol(symbol=symbol_str)
                positions.append(MT5Position(account_id, symbol, quantity, avg_cost, commission))
            elif getattr(pos, "account_id", None) == account_id:
                positions.append(pos)
        return positions if positions else None

    async def get_history_deals(
        self,
        from_ts: int = 0,
        to_ts: int | None = None,
    ) -> list[dict]:
        """
        Retrieve historical deal records from MT5.

        Parameters
        ----------
        from_ts : int
            Start of the range as a Unix timestamp (seconds). Defaults to 0.
        to_ts : int, optional
            End of the range as a Unix timestamp (seconds). Defaults to current time.

        Returns
        -------
        list[dict]
        """
        import time as _time
        import rpyc

        if to_ts is None:
            to_ts = int(_time.time())

        try:
            res = await asyncio.to_thread(
                self._mt5_client["mt5"].history_deals_get, from_ts, to_ts
            )
            if res is None:
                return []
            res_local = rpyc.classic.obtain(res)
            if isinstance(res_local, (list, tuple)):
                return list(res_local)
            # numpy structured array or similar
            try:
                return [dict(zip(res_local.dtype.names, row)) for row in res_local]
            except Exception:
                return list(res_local)
        except Exception as e:
            self._log.warning(f"Error fetching history deals: {e}")
            return []

    async def process_account_summary(
        self,
        *,
        req_id: int,
        account_id: str,
        tag: str,
        value: str,
        currency: str,
    ) -> None:
        """
        Receive account information.
        """
        name = f"accountSummary-{account_id}"
        if handler := self._event_subscriptions.get(name, None):
            handler(tag, value, currency)

    async def process_managed_accounts(self, *, accounts: Tuple[str]) -> None:
        """
        Receive a tuple with the managed account ids.

        Occurs automatically on initial API client connection.

        """

        self._account_ids = set(accounts)  # {a for a in accounts_list.split(",") if a}
        self._log.debug(f"Managed accounts set: {self._account_ids}")

        if self._next_valid_order_id >= 0 and not self._is_mt5_connected.is_set():
            self._log.debug(
                "`_is_mt5_connected` set by `managed_accounts`.", LogColor.BLUE
            )
            self._is_mt5_connected.set()

    async def process_position(
        self,
        *,
        account_id: str,
        symbol: MT5Symbol,
        position: Decimal,
        avg_cost: float,
    ) -> None:
        """
        Provide the portfolio's open positions.
        """
        if request := self._requests.get(name="OpenPositions"):
            request.result.append(MT5Position(account_id, symbol, position, avg_cost))

    async def process_position_end(self) -> None:
        """
        Indicate that all the positions have been transmitted.
        """
        if request := self._requests.get(name="OpenPositions"):
            self._end_request(request.req_id)
