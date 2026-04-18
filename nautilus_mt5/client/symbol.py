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

        async def _mock_resolve():
            info = SymbolInfo(
                name=symbol.symbol,
                path="Test",
                currency_base="USD",
                currency_profit="USD",
                currency_margin="USD",
                description="Test Asset",
                digits=2,
                point=0.01,
                volume_min=0.1,
                volume_max=100.0,
                volume_step=0.1,
                trade_tick_size=0.25,
                trade_tick_value=5.0,
            )
            await self.process_symbol_details(req_id=req_id, symbol_infos=[info])
            await self.process_symbol_details_end(req_id=req_id)

        request = self._requests.add(
            req_id=req_id,
            name=f"MT5Symbol({symbol})",
            handle=lambda: asyncio.create_task(_mock_resolve())
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
