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
        req_id = self._next_req_id()

        async def _real_resolve():
            try:
                # Real implementation to get symbol info
                info = getattr(self._mt5_client['mt5'], "symbol_info", None)(symbol.symbol)
                if not info:
                    self._log.error(f"Symbol {symbol.symbol} not found in MT5.")
                    if getattr(self, "_requests", None):
                        self._end_request(req_id, success=False)
                    return None

                # Normalize RPyC netref to pure Python dictionary
                if hasattr(info, "_asdict"):
                    info_dict = info._asdict()
                elif hasattr(info, "__dict__"):
                    info_dict = info.__dict__.copy()
                else:
                    info_dict = dict(info)

                # Fix properties that netref might expose incorrectly or miss
                if "name" not in info_dict:
                    info_dict["name"] = symbol.symbol

                class _NormalizedInfo:
                    def __init__(self, **kwargs):
                        self.__dict__.update(kwargs)

                normalized_info = _NormalizedInfo(**info_dict)

                if getattr(self, "_requests", None):
                    req = self._requests.get(req_id=req_id)
                    if req:
                        new_list = [normalized_info]
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
