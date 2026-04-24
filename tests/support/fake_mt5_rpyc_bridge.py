from typing import Any, Dict, List, Tuple, Optional


class FakeMT5RPyCRoot:
    """
    Fake RPyC root for MetaTrader 5 gateway simulation.
    Exposes the minimum surface required for external_rpyc mode.
    """

    def __init__(self):
        self._constants = {
            "TIMEFRAME_M1": 1,
            "TIMEFRAME_M5": 5,
            "COPY_TICKS_ALL": 0,
        }

    def exposed_initialize(self, *args, **kwargs) -> bool:
        return True

    def exposed_login(self, *args, **kwargs) -> bool:
        return True

    def exposed_last_error(self, *args, **kwargs) -> Tuple[int, str]:
        return (0, "OK")

    def exposed_version(self, *args, **kwargs) -> Tuple[int, int, str]:
        return (500, 0, "Fake MT5")

    def exposed_shutdown(self, *args, **kwargs) -> bool:
        return True

    def exposed_get_constant(self, name: str) -> Any:
        return self._constants.get(name)

    def exposed_terminal_info(self, *args, **kwargs) -> Dict[str, Any]:
        return {
            "name": "Fake MetaTrader 5",
            "company": "Fake Broker",
            "connected": True,
            "trade_allowed": True,
            "build": 3000,
        }

    def exposed_account_info(self, *args, **kwargs) -> Dict[str, Any]:
        return {
            "login": 123456,
            "server": "FakeServer",
            "balance": 100000.0,
            "equity": 100000.0,
            "currency": "USD",
        }

    def exposed_symbols_get(self, *args, **kwargs) -> List[str]:
        return ["EURUSD"]

    def exposed_symbol_info(self, symbol: str, *args, **kwargs) -> Optional[Dict[str, Any]]:
        if symbol == "EURUSD":
            return {
                "name": "EURUSD",
                "visible": True,
                "digits": 5,
                "point": 0.00001,
            }
        return None

    def exposed_symbol_info_tick(self, symbol: str, *args, **kwargs) -> Optional[Dict[str, Any]]:
        if symbol == "EURUSD":
            return {
                "symbol": "EURUSD",
                "bid": 1.10000,
                "ask": 1.10020,
                "last": 1.10010,
                "time": 1700000000,
            }
        return None

    def exposed_symbol_select(self, symbol: str, enable: bool = True) -> bool:
        return True

    def exposed_copy_rates_from_pos(self, symbol: str, timeframe: int, start_pos: int, count: int) -> List[Dict[str, Any]]:
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
        return [
            {
                "time": 1700000000,
                "bid": 1.10000,
                "ask": 1.10020,
                "last": 1.10010,
                "flags": 0,
            }
        ] * count

    def exposed_order_send(self, request: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "retcode": 10009,
            "comment": "Request completed",
            "order": 1,
            "deal": 1,
        }

    def exposed_positions_get(self, *args, **kwargs) -> List[Dict[str, Any]]:
        return [
            {
                "ticket": 1,
                "symbol": "EURUSD",
                "type": 0,
                "volume": 0.1,
                "price_open": 1.10000,
            }
        ]

    def exposed_history_orders_total(self, *args, **kwargs) -> int:
        return 1

    def exposed_history_orders_get(self, *args, **kwargs) -> List[Dict[str, Any]]:
        return [
            {
                "ticket": 1,
                "symbol": "EURUSD",
                "type": 0,
                "volume_initial": 0.1,
            }
        ]

    def exposed_history_deals_total(self, *args, **kwargs) -> int:
        return 1

    def exposed_history_deals_get(self, *args, **kwargs) -> List[Dict[str, Any]]:
        return [
            {
                "ticket": 1,
                "order": 1,
                "symbol": "EURUSD",
                "type": 0,
                "volume": 0.1,
            }
        ]


class FakeMT5RPyCConnection:
    """
    Fake RPyC connection for MetaTrader 5 gateway simulation.
    """

    def __init__(self):
        self.root = FakeMT5RPyCRoot()


def make_fake_mt5_rpyc_connection() -> FakeMT5RPyCConnection:
    """
    Helper function to create a FakeMT5RPyCConnection.
    """
    return FakeMT5RPyCConnection()
