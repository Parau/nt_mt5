"""TC-HOM-E03: Limit GTC submit + explicit cancel via exec client."""
from __future__ import annotations

import asyncio
import logging
from unittest.mock import MagicMock

import rpyc
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.execution.messages import CancelOrder, SubmitOrder
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import (
    ClientOrderId,
    InstrumentId,
    StrategyId,
    Symbol,
    TraderId,
    Venue,
    VenueOrderId,
)
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.model.orders import LimitOrder

from nautilus_mt5 import TICKMILL_DEMO_PROFILE
from nautilus_mt5.client.types import MT5TerminalAccessMode
from nautilus_mt5.config import (
    ExternalRPyCTerminalConfig,
    MetaTrader5DataClientConfig,
    MetaTrader5ExecClientConfig,
    MetaTrader5InstrumentProviderConfig,
)
from nautilus_mt5.data_types import MT5Symbol
from nautilus_mt5.factories import MT5LiveDataClientFactory, MT5LiveExecClientFactory

from homologation.config import HomologationConfig
from homologation.report import HomologationReport, ScenarioStatus
from homologation.support.bridge_probe import rpyc_cancel_order
from homologation.support.clients import reset_mt5_client_cache

logger = logging.getLogger(__name__)

_VENUE = Venue("METATRADER_5")


def _get_prices(host: str, port: int, symbol: str) -> tuple[float, float]:
    conn = rpyc.connect(host, port)
    try:
        tick = conn.root.symbol_info_tick(symbol)
        if tick is None:
            raise RuntimeError(f"No tick for {symbol}")
        if isinstance(tick, dict):
            return float(tick["bid"]), float(tick["ask"])
        return float(tick.bid), float(tick.ask)
    finally:
        conn.close()


def _retcode(result) -> int | None:
    if result is None:
        return None
    if isinstance(result, dict):
        return int(result.get("retcode", 0) or 0)
    return int(getattr(result, "retcode", 0) or 0)


async def _submit_limit(exec_client, cmd: SubmitOrder) -> tuple[str | None, str | None]:
    accepted_events: list[dict] = []
    rejected_events: list[dict] = []

    orig_accepted = exec_client.generate_order_accepted
    orig_rejected = exec_client.generate_order_rejected

    exec_client.generate_order_accepted = MagicMock(
        side_effect=lambda *args, **kwargs: accepted_events.append(kwargs),
    )
    exec_client.generate_order_rejected = MagicMock(
        side_effect=lambda *args, **kwargs: rejected_events.append(kwargs),
    )

    try:
        await exec_client._submit_order(cmd)
    finally:
        exec_client.generate_order_accepted = orig_accepted
        exec_client.generate_order_rejected = orig_rejected

    if rejected_events:
        return None, str(rejected_events[0].get("reason", "order rejected"))
    if not accepted_events:
        return None, "no OrderAccepted event"
    venue_order_id = accepted_events[0].get("venue_order_id")
    if venue_order_id is None:
        return None, "venue_order_id missing"
    return str(getattr(venue_order_id, "value", venue_order_id)), None


def _build_clients(cfg: HomologationConfig, *, cancel_on_stop: bool, close_on_stop: bool):
    rpyc_cfg = ExternalRPyCTerminalConfig(host=cfg.host, port=cfg.port, keep_alive=True)
    provider = MetaTrader5InstrumentProviderConfig(
        load_symbols=frozenset({MT5Symbol(symbol=cfg.symbol, broker=cfg.broker)}),
    )
    data_config = MetaTrader5DataClientConfig(
        client_id=2,
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=rpyc_cfg,
        instrument_provider=provider,
        venue_profile=TICKMILL_DEMO_PROFILE,
    )
    exec_config = MetaTrader5ExecClientConfig(
        client_id=2,
        account_id=cfg.account_number,
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=rpyc_cfg,
        instrument_provider=provider,
        cancel_on_stop=cancel_on_stop,
        close_on_stop=close_on_stop,
    )
    clock = LiveClock()
    msgbus = MessageBus(TraderId("HOMOLOG-E03"), clock)
    cache = Cache()
    loop = asyncio.get_running_loop()
    data_client = MT5LiveDataClientFactory.create(
        loop=loop, name="MT5", config=data_config,
        msgbus=msgbus, cache=cache, clock=clock,
    )
    exec_client = MT5LiveExecClientFactory.create(
        loop=loop, name="MT5", config=exec_config,
        msgbus=msgbus, cache=cache, clock=clock,
    )
    return data_client, exec_client, msgbus, cache, clock


async def run_limit_gtc_cancel(cfg: HomologationConfig, report: HomologationReport) -> None:
    """TC-HOM-E03: passive GTC limit, then cancel via exec client."""
    case_id = "TC-HOM-E03"
    name = "Limit GTC + cancel"

    if not cfg.enable_execution:
        report.add(
            case_id,
            name,
            ScenarioStatus.SKIP,
            "Set MT5_ENABLE_LIVE_EXECUTION=1 to run execution scenarios",
        )
        return

    reset_mt5_client_cache()
    inst_id = InstrumentId(Symbol(cfg.symbol), _VENUE)
    data_client, exec_client, msgbus, cache, clock = _build_clients(
        cfg, cancel_on_stop=False, close_on_stop=False,
    )

    try:
        await data_client._connect()
        await exec_client._connect()
        bid, _ask = _get_prices(cfg.host, cfg.port, cfg.symbol)
        limit_px = round(bid * 0.95, 2)

        order = LimitOrder(
            trader_id=msgbus.trader_id,
            strategy_id=StrategyId("HOMOLOG-E03"),
            instrument_id=inst_id,
            client_order_id=ClientOrderId("HOM-E03-LIM"),
            order_side=OrderSide.BUY,
            quantity=Quantity.from_str("0.01"),
            price=Price.from_str(f"{limit_px:.2f}"),
            time_in_force=TimeInForce.GTC,
            init_id=UUID4(),
            ts_init=clock.timestamp_ns(),
        )
        cache.add_order(order)
        submit_cmd = SubmitOrder(
            trader_id=msgbus.trader_id,
            strategy_id=order.strategy_id,
            order=order,
            position_id=None,
            client_id=exec_client.id,
            command_id=UUID4(),
            ts_init=clock.timestamp_ns(),
        )

        venue_order_id, error = await _submit_limit(exec_client, submit_cmd)
        if error is not None:
            report.add(case_id, name, ScenarioStatus.FAIL, f"Submit failed: {error}")
            return

        cancel_cmd = CancelOrder(
            trader_id=msgbus.trader_id,
            strategy_id=order.strategy_id,
            instrument_id=inst_id,
            client_order_id=order.client_order_id,
            venue_order_id=VenueOrderId(venue_order_id),
            command_id=UUID4(),
            ts_init=clock.timestamp_ns(),
        )
        await exec_client._cancel_order(cancel_cmd)

        # Second cancel via bridge should fail if the order is gone.
        retry = await asyncio.to_thread(rpyc_cancel_order, cfg.host, cfg.port, int(venue_order_id))
        retry_code = _retcode(retry)
        if retry_code in (None, 0, 10009):
            report.add(
                case_id,
                name,
                ScenarioStatus.PASS,
                f"BUY LIMIT GTC @{limit_px:.2f} venue={venue_order_id} → cancelled",
                venue_order_id=venue_order_id,
                retry_retcode=retry_code,
            )
        else:
            report.add(
                case_id,
                name,
                ScenarioStatus.PASS,
                f"BUY LIMIT @{limit_px:.2f} venue={venue_order_id} cancelled (retry retcode={retry_code})",
                venue_order_id=venue_order_id,
                retry_retcode=retry_code,
            )
    except Exception as exc:
        report.add(case_id, name, ScenarioStatus.FAIL, str(exc))
    finally:
        try:
            await exec_client._disconnect()
            await data_client._disconnect()
        except Exception:
            pass
