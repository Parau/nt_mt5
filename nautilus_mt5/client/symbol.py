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
                # Provide a thread-safe local function to resolve the RPyC proxy dot accesses
                def _fetch_symbol_sync(conn, symbol_name):
                    try:
                        if hasattr(conn, 'root') and hasattr(conn.root, 'exposed_symbol_info'):
                            return conn.root.exposed_symbol_info(symbol_name)
                        elif hasattr(conn, 'symbol_info'):
                            return conn.symbol_info(symbol_name)
                    except Exception as e:
                        return None
                    return None

                info_raw = await asyncio.to_thread(_fetch_symbol_sync, self._mt5_client['mt5'], symbol.symbol)

                if info_raw:
                    if not isinstance(info_raw, dict):
                        try:
                            info_dict = dict(info_raw._asdict())
                        except AttributeError:
                            info_dict = {k: getattr(info_raw, k) for k in dir(info_raw) if not k.startswith('_') and not callable(getattr(info_raw, k))}
                    else:
                        info_dict = info_raw

                    info_dict = dict(info_dict)
                    # Patch standard values for symbol
                    info_dict['name'] = symbol.symbol
                    info_dict['point'] = info_dict.get('point', 0.01)
                    info_dict['trade_tick_size'] = info_dict.get('trade_tick_size', 0.01)
                    info_dict['trade_contract_size'] = info_dict.get('trade_contract_size', 1.0)
                    info_dict['volume_min'] = info_dict.get('volume_min', 0.01)
                    info_dict['volume_max'] = info_dict.get('volume_max', 250.0)
                    info_dict['volume_step'] = info_dict.get('volume_step', 0.01)

                    if 'currency_base' not in info_dict or not info_dict['currency_base']:
                        info_dict['currency_base'] = 'USD'
                    if 'currency_profit' not in info_dict or not info_dict['currency_profit']:
                        info_dict['currency_profit'] = 'USD'
                    if 'currency_margin' not in info_dict or not info_dict['currency_margin']:
                        info_dict['currency_margin'] = 'USD'

                    # Handle RPyC returning None or empty strings for path
                    if 'path' not in info_dict or not info_dict['path']:
                        info_dict['path'] = "Custom"
                    if 'description' not in info_dict or not info_dict['description']:
                        info_dict['description'] = symbol.symbol

                    info = SymbolInfo(**{k: v for k, v in info_dict.items() if k in SymbolInfo.__struct_fields__})
                    await self.process_symbol_details(req_id=req_id, symbol_infos=[info])
                else:
                    self._log.error(f"Could not fetch symbol info for {symbol.symbol}")
            except Exception as e:
                self._log.error(f"Failed resolving symbol details: {e}")

            await self.process_symbol_details_end(req_id=req_id)

        try:
            request = self._requests.add(
                req_id=req_id,
                name=f"MT5Symbol({symbol})-{req_id}",
                handle=lambda: asyncio.create_task(_real_resolve())
            )
        except Exception as e:
            # Re-adding a request might fail if it was interrupted
            self._requests.remove(req_id)
            request = self._requests.add(
                req_id=req_id,
                name=f"MT5Symbol({symbol})-{req_id}",
                handle=lambda: asyncio.create_task(_real_resolve())
            )
        if not request:
            return None
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
