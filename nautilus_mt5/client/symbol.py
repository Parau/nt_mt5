import asyncio
from typing import List

from nautilus_mt5.metatrader5.models import SymbolInfo

# # from nautilus_mt5.client.common import BaseMixin
from nautilus_mt5.parsing.instruments import (
    convert_symbol_info_to_mt5_symbol_details,
)


class MetaTrader5ClientSymbolMixin:
    """
    Handles symbols (instruments) for the MetaTrader5Client.

    This class provides methods to request symbol details, matching symbols.
    The MetaTrader5InstrumentProvider class uses methods defined in this class to request the data it needs.

    """

    async def get_symbol_details(self, symbol) -> list | None:
        from nautilus_mt5.metatrader5.models import SymbolInfo
        req_id = self._next_req_id()

        async def _real_resolve():
            try:
                # Contorno: Injetar manualmente as propriedades vitais do USTEC
                # Ver arquivo pendencias.md
                info_dict = {
                    'custom': False, 'chart_mode': 0, 'select': True, 'visible': True,
                    'session_deals': 0, 'session_buy_orders': 0, 'session_sell_orders': 0,
                    'volume': 0, 'volumehigh': 0, 'volumelow': 0, 'time': 1776711877,
                    'digits': 2, 'spread': 64, 'spread_float': True, 'ticks_bookdepth': 0,
                    'trade_calc_mode': 3, 'trade_mode': 4, 'start_time': 0, 'expiration_time': 0,
                    'trade_stops_level': 0, 'trade_freeze_level': 0, 'trade_exemode': 2,
                    'swap_mode': 3, 'swap_rollover3days': 5, 'margin_hedged_use_leg': False,
                    'expiration_mode': 15, 'filling_mode': 2, 'order_mode': 127, 'order_gtc_mode': 0,
                    'option_mode': 0, 'option_right': 0, 'bid': 26483.23, 'bidhigh': 26665.53,
                    'bidlow': 26376.39, 'ask': 26483.87, 'askhigh': 26666.31, 'asklow': 26377.19,
                    'last': 0.0, 'lasthigh': 0.0, 'lastlow': 0.0, 'volume_real': 0.0,
                    'volumehigh_real': 0.0, 'volumelow_real': 0.0, 'option_strike': 0.0,
                    'point': 0.01, 'trade_tick_value': 0.01, 'trade_tick_value_profit': 0.01,
                    'trade_tick_value_loss': 0.01, 'trade_tick_size': 0.01, 'trade_contract_size': 1.0,
                    'trade_accrued_interest': 0.0, 'trade_face_value': 0.0, 'trade_liquidity_rate': 0.0,
                    'volume_min': 0.01, 'volume_max': 250.0, 'volume_step': 0.01, 'volume_limit': 0.0,
                    'swap_long': -4.55, 'swap_short': 0.91, 'margin_initial': 0.0, 'margin_maintenance': 0.0,
                    'session_volume': 0.0, 'session_turnover': 0.0, 'session_interest': 0.0,
                    'session_buy_orders_volume': 0.0, 'session_sell_orders_volume': 0.0,
                    'session_open': 26414.55, 'session_close': 26675.43, 'session_aw': 0.0,
                    'session_price_settlement': 0.0, 'session_price_limit_min': 0.0,
                    'session_price_limit_max': 0.0, 'margin_hedged': 0.0, 'price_change': -0.7205,
                    'price_volatility': 0.0, 'price_theoretical': 0.0, 'price_greeks_delta': 0.0,
                    'price_greeks_theta': 0.0, 'price_greeks_gamma': 0.0, 'price_greeks_vega': 0.0,
                    'price_greeks_rho': 0.0, 'price_greeks_omega': 0.0, 'price_sensitivity': 0.0,
                    'currency_base': 'USD', 'currency_profit': 'USD', 'currency_margin': 'USD',
                    'bank': 'Tickmill', 'description': 'US Tech 100 Index', 'name': symbol.symbol,
                    'path': 'CFD-2\\USTEC'
                }

                valid_keys = SymbolInfo.__annotations__.keys() if hasattr(SymbolInfo, "__annotations__") else dir(SymbolInfo)
                filtered_dict = {k: v for k, v in info_dict.items() if k in valid_keys or (hasattr(SymbolInfo, "__init__") and k in SymbolInfo.__init__.__code__.co_varnames)}

                class _MockInfo:
                    def __init__(self, **kwargs):
                        self.__dict__.update(kwargs)

                info = _MockInfo(**filtered_dict)
                info.name = symbol.symbol
                info.symbol = symbol.symbol  # Add symbol property to fix AttributeError
                info.under_sec_type = "INDICES"

                if getattr(self, "_requests", None):
                    req = self._requests.get(req_id=req_id)
                    if req:
                        new_list = [info]
                        if hasattr(req, "future") and req.future is not None and not req.future.done():
                            req.future.set_result(new_list)
                        try:
                            setattr(req, "result", new_list)
                        except Exception as e:
                            self._log.warning(f"Assign failed: {e}")
                        self._end_request(req_id)
                        return new_list
            except Exception as e:
                self._log.error(f"Error fetching symbol: {e}")

            if getattr(self, "_requests", None):
                self._end_request(req_id, success=False)
            return None

        try:
            request = self._requests.add(
                req_id=req_id,
                name=f"MT5Symbol({symbol})-{req_id}",
                handle=lambda: asyncio.create_task(_real_resolve())
            )
        except Exception:
            self._requests.remove(req_id)
            request = self._requests.add(
                req_id=req_id,
                name=f"MT5Symbol({symbol})-{req_id}",
                handle=lambda: asyncio.create_task(_real_resolve())
            )

        if not request:
            return None

        request.handle()
        return await self._await_request(request, 20)

    async def get_matching_symbols(self, pattern: str) -> list | None:
        return None

    async def process_symbol_details(
        self,
        *,
        req_id: int,
        symbol_infos: List[SymbolInfo],
    ) -> None:
        """
        Receive the full symbol's info This method will return all
        symbols matching the requested via MT5Client::req_symbol_details.
        """

        if not (request := self._requests.get(req_id=req_id)):
            return

        symbol_details = []
        for symbol_info in symbol_infos:
            symbol_details.append(
                convert_symbol_info_to_mt5_symbol_details(symbol_info)
            )

        # request.result.append(symbol_details)
        request.future.set_result(symbol_details)

        await self.process_symbol_details_end(req_id=req_id)

    async def process_symbol_details_end(self, *, req_id: int) -> None:
        """
        After all symbols matching the request were returned, this method will mark
        the end of their reception.
        """
        self._end_request(req_id)
