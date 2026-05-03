from dataclasses import dataclass
from typing import Any, Dict, List, Tuple, Optional


@dataclass(frozen=True)
class FakeMT5RPyCCall:
    """
    Represents a recorded call to the fake RPyC bridge.
    """
    method: str
    args: Tuple[Any, ...]
    kwargs: Dict[str, Any]


class FakeMT5RPyCRoot:
    """
    Fake RPyC root for MetaTrader 5 gateway simulation.
    Exposes the minimum surface required for external_rpyc mode.
    Includes call recording for auditing.
    """

    def __init__(self):
        self._constants = {
            "TIMEFRAME_M1": 1,
            "TIMEFRAME_M5": 5,
            "COPY_TICKS_ALL": 0,
        }
        self._calls: List[FakeMT5RPyCCall] = []

    @property
    def calls(self) -> List[FakeMT5RPyCCall]:
        """
        Returns the list of recorded calls.
        """
        return self._calls

    def reset_calls(self) -> None:
        """
        Resets the recorded calls list.
        """
        self._calls.clear()

    def _record_call(self, method: str, args: Tuple[Any, ...], kwargs: Dict[str, Any]) -> None:
        """
        Internal helper to record a call.
        """
        self._calls.append(FakeMT5RPyCCall(method=method, args=args, kwargs=dict(kwargs)))

    def exposed_initialize(self, *args, **kwargs) -> bool:
        self._record_call("initialize", args, kwargs)
        return True

    def exposed_login(self, *args, **kwargs) -> bool:
        self._record_call("login", args, kwargs)
        return True

    def exposed_last_error(self, *args, **kwargs) -> Tuple[int, str]:
        self._record_call("last_error", args, kwargs)
        return (0, "OK")

    def exposed_version(self, *args, **kwargs) -> Tuple[int, int, str]:
        self._record_call("version", args, kwargs)
        return (500, 0, "Fake MT5")

    def exposed_shutdown(self, *args, **kwargs) -> bool:
        self._record_call("shutdown", args, kwargs)
        return True

    def exposed_get_constant(self, name: str) -> Any:
        self._record_call("get_constant", (name,), {})
        return self._constants.get(name)

    def exposed_terminal_info(self, *args, **kwargs) -> Dict[str, Any]:
        self._record_call("terminal_info", args, kwargs)
        return {
            "name": "Fake MetaTrader 5",
            "company": "Fake Broker",
            "connected": True,
            "trade_allowed": True,
            "build": 3000,
        }

    def exposed_account_info(self, *args, **kwargs) -> Dict[str, Any]:
        self._record_call("account_info", args, kwargs)
        return {
            "login": 123456,
            "server": "FakeServer",
            "balance": 100000.0,
            "equity": 100000.0,
            "currency": "USD",
        }

    def exposed_symbols_get(self, *args, **kwargs) -> List[str]:
        self._record_call("symbols_get", args, kwargs)
        return ["EURUSD", "USTEC", "BTCUSD"]

    def exposed_symbol_info(self, symbol: str, *args, **kwargs) -> Optional[Dict[str, Any]]:
        self._record_call("symbol_info", (symbol, *args), kwargs)
        if symbol == "EURUSD":
            return {
                "name": "EURUSD",
                "path": "Forex\\EURUSD",
                "visible": True,
                "select": True,
                "digits": 5,
                "point": 0.00001,
                "spread": 2,
                "spread_float": True,
                "volume_step": 0.01,
                "volume_min": 0.01,
                "volume_max": 100.0,
                "trade_tick_size": 0.00001,
                "trade_contract_size": 100000.0,
                "currency_base": "EUR",
                "currency_profit": "USD",
                "currency_margin": "EUR",
                "under_sec_type": "FOREX",
                "description": "Euro vs US Dollar",
                "time": 0,
                "bid": 1.10000,
                "ask": 1.10020,
                "trade_calc_mode": 0,  # SYMBOL_CALC_MODE_FOREX
            }
        if symbol == "USTEC":
            return {
                "name": "USTEC",
                "path": "Indexes\\USTEC",
                "visible": True,
                "select": True,
                "digits": 2,
                "point": 0.01,
                "spread": 5,
                "spread_float": True,
                "volume_step": 0.01,
                "volume_min": 0.01,
                "volume_max": 100.0,
                "trade_tick_size": 0.01,
                "trade_contract_size": 1.0,
                "currency_base": "USD",
                "currency_profit": "USD",
                "currency_margin": "USD",
                "under_sec_type": "INDEXES",
                "description": "US Tech 100 Index",
                "time": 0,
                "bid": 18500.00,
                "ask": 18500.50,
                "trade_calc_mode": 3,  # SYMBOL_CALC_MODE_CFDINDEX
            }
        if symbol == "BTCUSD":
            return {
                "name": "BTCUSD",
                "path": "Crypto\\BTCUSD",
                "visible": True,
                "select": True,
                "digits": 2,
                "point": 0.01,
                "spread": 100,
                "spread_float": False,
                "volume_step": 0.01,
                "volume_min": 0.01,
                "volume_max": 10.0,
                "trade_tick_size": 0.01,
                "trade_contract_size": 1.0,
                "currency_base": "BTC",
                "currency_profit": "USD",
                "currency_margin": "USD",
                "under_sec_type": "CRYPTO",
                "description": "Bitcoin vs US Dollar",
                "time": 0,
                "bid": 78000.00,
                "ask": 78001.00,
                "trade_calc_mode": 2,  # SYMBOL_CALC_MODE_CFD
            }
        return None

    def exposed_symbol_info_tick(self, symbol: str, *args, **kwargs) -> Optional[Dict[str, Any]]:
        self._record_call("symbol_info_tick", (symbol, *args), kwargs)
        if symbol == "EURUSD":
            return {
                "symbol": "EURUSD",
                "bid": 1.10000,
                "ask": 1.10020,
                "last": 1.10010,
                "time": 1700000000,
            }
        if symbol == "USTEC":
            return {
                "symbol": "USTEC",
                "bid": 18500.00,
                "ask": 18500.50,
                "last": 18500.25,
                "time": 1700000000,
            }
        if symbol == "BTCUSD":
            return {
                "symbol": "BTCUSD",
                "bid": 78000.00,
                "ask": 78001.00,
                "last": 78000.50,
                "time": 1700000000,
            }
        return None

    def exposed_symbol_select(self, symbol: str, enable: bool = True) -> bool:
        self._record_call("symbol_select", (symbol,), {"enable": enable})
        return True

    def exposed_copy_rates_from_pos(self, symbol: str, timeframe: int, start_pos: int, count: int) -> List[Dict[str, Any]]:
        self._record_call("copy_rates_from_pos", (symbol, timeframe, start_pos, count), {})
        if symbol == "USTEC":
            return [
                {
                    "time": 1700000000,
                    "open": 18490.00,
                    "high": 18510.00,
                    "low": 18480.00,
                    "close": 18500.00,
                    "tick_volume": 100,
                    "spread": 5,
                    "real_volume": 100,
                }
            ] * count
        if symbol == "BTCUSD":
            return [
                {
                    "time": 1700000000,
                    "open": 77900.00,
                    "high": 78200.00,
                    "low": 77800.00,
                    "close": 78000.00,
                    "tick_volume": 50,
                    "spread": 100,
                    "real_volume": 50,
                }
            ] * count
        return [
            {
                "time": 1700000000,
                "open": 1.10000,
                "high": 1.10100,
                "low": 1.09900,
                "close": 1.10050,
                "tick_volume": 10,
                "spread": 2,
                "real_volume": 10,
            }
        ] * count

    def exposed_copy_ticks_range(self, symbol: str, date_from: Any, date_to: Any, flags: int) -> List[Dict[str, Any]]:
        self._record_call("copy_ticks_range", (symbol, date_from, date_to, flags), {})
        if symbol == "USTEC":
            return [
                {
                    "time": 1700000000,
                    "bid": 18500.00,
                    "ask": 18500.50,
                    "last": 18500.25,
                    "flags": 0,
                }
            ]
        if symbol == "BTCUSD":
            return [
                {
                    "time": 1700000000,
                    "bid": 78000.00,
                    "ask": 78001.00,
                    "last": 78000.50,
                    "flags": 0,
                }
            ]
        return [
            {
                "time": 1700000000,
                "bid": 1.10000,
                "ask": 1.10020,
                "last": 1.10010,
                "flags": 0,
            }
        ]

    def exposed_copy_ticks_from(self, symbol: str, date_from: Any, count: int, flags: int) -> List[Dict[str, Any]]:
        self._record_call("copy_ticks_from", (symbol, date_from, count, flags), {})
        if symbol == "USTEC":
            return [
                {
                    "time": 1700000000,
                    "bid": 18500.00,
                    "ask": 18500.50,
                    "last": 18500.25,
                    "flags": 0,
                }
            ] * count
        if symbol == "BTCUSD":
            return [
                {
                    "time": 1700000000,
                    "bid": 78000.00,
                    "ask": 78001.00,
                    "last": 78000.50,
                    "flags": 0,
                }
            ] * count
        return [
            {
                "time": 1700000000,
                "bid": 1.10000,
                "ask": 1.10020,
                "last": 1.10010,
                "flags": 0,
            }
        ] * count

    # --- Execution payloads ---

    def exposed_order_send(self, request: Dict[str, Any]) -> Dict[str, Any]:
        self._record_call("order_send", (request,), {})
        symbol = request.get("symbol", "EURUSD")
        action = request.get("action", 1)
        # TRADE_ACTION_PENDING (5) → order placed but not yet filled → retcode 10008
        # TRADE_ACTION_REMOVE (8) → cancel, no deal → retcode 10009 (done)
        # TRADE_ACTION_DEAL (1) → market fill → retcode 10009 + deal
        if action == 5:  # TRADE_ACTION_PENDING
            retcode = 10008  # TRADE_RETCODE_PLACED
            deal = 0
        else:
            retcode = 10009  # TRADE_RETCODE_DONE
            if symbol == "USTEC":
                deal = 101
            elif symbol == "BTCUSD":
                deal = 201
            else:
                deal = 1
        if symbol == "USTEC":
            return {
                "retcode": retcode,
                "comment": "Request completed",
                "order": 1001,
                "deal": deal,
                "symbol": "USTEC",
                "volume": request.get("volume", 0.1),
                "price": 18500.50,
            }
        if symbol == "BTCUSD":
            return {
                "retcode": retcode,
                "comment": "Request completed",
                "order": 2001,
                "deal": deal,
                "symbol": "BTCUSD",
                "volume": request.get("volume", 0.01),
                "price": 78001.00,
            }
        return {
            "retcode": retcode,
            "comment": "Request completed",
            "order": 1,
            "deal": deal,
            "symbol": symbol,
            "volume": request.get("volume", 0.1),
            "price": 1.10020,
        }

    def exposed_positions_get(self, *args, **kwargs) -> List[Dict[str, Any]]:
        self._record_call("positions_get", args, kwargs)
        all_positions = [
            {
                "ticket": 1001,
                "symbol": "USTEC",
                "type": 0,           # POSITION_TYPE_BUY
                "volume": 0.1,
                "price_open": 18500.50,
                "price_current": 18501.00,
                "profit": 0.05,
                "time": 1700000000,
                "time_msc": 1700000000000,
                "magic": 0,
                "comment": "NautilusOrder",
                "identifier": 101,
            },
            {
                "ticket": 1,
                "symbol": "EURUSD",
                "type": 0,
                "volume": 0.1,
                "price_open": 1.10000,
                "price_current": 1.10020,
                "profit": 0.02,
                "time": 1700000000,
                "time_msc": 1700000000000,
                "magic": 0,
                "comment": "",
                "identifier": 1,
            },
        ]
        symbol_filter = kwargs.get("symbol")
        if symbol_filter:
            return [p for p in all_positions if p["symbol"] == symbol_filter]
        return all_positions

    def exposed_history_orders_total(self, *args, **kwargs) -> int:
        self._record_call("history_orders_total", args, kwargs)
        return 2

    def exposed_history_orders_get(self, *args, **kwargs) -> List[Dict[str, Any]]:
        self._record_call("history_orders_get", args, kwargs)
        all_orders = [
            {
                "ticket": 1001,
                "symbol": "USTEC",
                "type": 0,               # ORDER_TYPE_BUY
                "volume_initial": 0.1,
                "volume_current": 0.0,   # fully filled
                "price_open": 18500.50,
                "state": 4,              # ORDER_STATE_FILLED
                "time_setup": 1700000000,
                "time_setup_msc": 1700000000000,
                "time_done": 1700000001,
                "time_done_msc": 1700000001000,
                "type_time": 0,
                "type_filling": 2,
                "magic": 0,
                "comment": "NautilusOrder",
            },
            {
                "ticket": 1,
                "symbol": "EURUSD",
                "type": 0,
                "volume_initial": 0.1,
                "volume_current": 0.0,
                "price_open": 1.10000,
                "state": 4,
                "time_setup": 1700000000,
                "time_setup_msc": 1700000000000,
                "time_done": 1700000001,
                "time_done_msc": 1700000001000,
                "type_time": 0,
                "type_filling": 2,
                "magic": 0,
                "comment": "",
            },
        ]
        group_filter = kwargs.get("group", "")
        if group_filter and group_filter != "*":
            # simple substring filter on symbol
            return [o for o in all_orders if group_filter.strip("*") in o["symbol"] or group_filter == "*"]
        return all_orders

    def exposed_history_deals_total(self, *args, **kwargs) -> int:
        self._record_call("history_deals_total", args, kwargs)
        return 2

    def exposed_history_deals_get(self, *args, **kwargs) -> List[Dict[str, Any]]:
        self._record_call("history_deals_get", args, kwargs)
        return [
            {
                "ticket": 101,
                "order": 1001,
                "symbol": "USTEC",
                "type": 0,           # DEAL_TYPE_BUY
                "entry": 0,          # DEAL_ENTRY_IN
                "volume": 0.1,
                "price": 18500.50,
                "commission": -0.50,
                "time": 1700000000,
                "time_msc": 1700000000000,
                "profit": 0.0,
                "swap": 0.0,
                "magic": 0,
                "comment": "NautilusOrder",
            },
            {
                "ticket": 1,
                "order": 1,
                "symbol": "EURUSD",
                "type": 0,
                "entry": 0,
                "volume": 0.1,
                "price": 1.10020,
                "commission": -0.30,
                "time": 1700000001,
                "time_msc": 1700000001000,
                "profit": 0.0,
                "swap": 0.0,
                "magic": 0,
                "comment": "",
            },
        ]

    def exposed_req_ids(self, *args, **kwargs) -> None:
        """No-op: MT5 assigns order IDs via order_send response, not on request."""
        self._record_call("req_ids", args, kwargs)

    def exposed_req_real_time_bars(self, *args, **kwargs) -> None:
        """No-op stub for real-time bar streaming (not natively supported in MT5)."""
        self._record_call("req_real_time_bars", args, kwargs)

    def exposed_req_tick_by_tick_data(self, *args, **kwargs) -> None:
        """No-op stub for tick streaming (not natively supported via RPyC)."""
        self._record_call("req_tick_by_tick_data", args, kwargs)

    def exposed_cancel_tick_by_tick_data(self, *args, **kwargs) -> None:
        self._record_call("cancel_tick_by_tick_data", args, kwargs)

    def exposed_cancel_historical_data(self, *args, **kwargs) -> None:
        self._record_call("cancel_historical_data", args, kwargs)

    def exposed_orders_get(self, *args, **kwargs) -> List[Dict[str, Any]]:
        self._record_call("orders_get", args, kwargs)
        return []


class FakeMT5RPyCConnection:
    """
    Fake RPyC connection for MetaTrader 5 gateway simulation.
    """

    def __init__(self):
        self.root = FakeMT5RPyCRoot()
        self.closed = False

    def close(self):
        """
        Closes the fake connection.
        """
        self.closed = True


def make_fake_mt5_rpyc_connection() -> FakeMT5RPyCConnection:
    """
    Helper function to create a FakeMT5RPyCConnection.
    """
    return FakeMT5RPyCConnection()
