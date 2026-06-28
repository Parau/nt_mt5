"""
Closed-market homologation scenarios — real MT5 bridge, no live tick stream required.

Covers infrastructure, historical RPyC paths, adapter unsupported gates, and exec
connect validation. Live-stream and order-fill scenarios belong in the open-market run.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import rpyc
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.data.messages import (
    RequestInstrument,
    RequestTradeTicks,
    SubscribeInstruments,
    SubscribeOrderBook,
    SubscribeTradeTicks,
)
from nautilus_trader.model.data import OrderBookDelta
from nautilus_trader.model.enums import BookType
from nautilus_trader.model.identifiers import InstrumentId, Symbol, TraderId, Venue

from nautilus_mt5 import TICKMILL_DEMO_PROFILE
from nautilus_mt5.client.types import MT5TerminalAccessMode
from nautilus_mt5.config import (
    ExternalRPyCTerminalConfig,
    MetaTrader5DataClientConfig,
    MetaTrader5ExecClientConfig,
    MetaTrader5InstrumentProviderConfig,
)
from nautilus_mt5.data_types import MT5Symbol
from nautilus_mt5.factories import MT5LiveDataClientFactory, MT5LiveExecClientFactory, MT5_CLIENTS

from homologation.config import HomologationConfig
from homologation.report import HomologationReport, ScenarioStatus
from homologation.support.clients import reset_mt5_client_cache

_VENUE = Venue("METATRADER_5")


def _instrument_id(symbol: str) -> InstrumentId:
    return InstrumentId(Symbol(symbol), _VENUE)

def _data_config(cfg: HomologationConfig) -> MetaTrader5DataClientConfig:
    return MetaTrader5DataClientConfig(
        client_id=1,
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=ExternalRPyCTerminalConfig(host=cfg.host, port=cfg.port, keep_alive=True),
        instrument_provider=MetaTrader5InstrumentProviderConfig(
            load_symbols=frozenset([MT5Symbol(symbol=cfg.symbol, broker=cfg.broker)]),
        ),
        venue_profile=TICKMILL_DEMO_PROFILE,
    )


def _exec_config(cfg: HomologationConfig, account_id: str | None = None) -> MetaTrader5ExecClientConfig:
    return MetaTrader5ExecClientConfig(
        client_id=1,
        account_id=account_id or cfg.account_number,
        terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
        external_rpyc=ExternalRPyCTerminalConfig(host=cfg.host, port=cfg.port, keep_alive=True),
        instrument_provider=MetaTrader5InstrumentProviderConfig(
            load_symbols=frozenset([MT5Symbol(symbol=cfg.symbol, broker=cfg.broker)]),
        ),
    )


def _attr(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    try:
        return obj[name]
    except (TypeError, KeyError, IndexError, ValueError):
        return getattr(obj, name, default)


async def _make_data_client(cfg: HomologationConfig):
    loop = asyncio.get_running_loop()
    clock = LiveClock()
    msgbus = MessageBus(TraderId("HOMOLOG-CM-DATA"), clock)
    cache = Cache()
    client = MT5LiveDataClientFactory.create(
        loop=loop,
        name="MT5",
        config=_data_config(cfg),
        msgbus=msgbus,
        cache=cache,
        clock=clock,
    )
    return client, msgbus, cache, clock


async def _make_exec_client(cfg: HomologationConfig, account_id: str | None = None):
    loop = asyncio.get_running_loop()
    clock = LiveClock()
    msgbus = MessageBus(TraderId("HOMOLOG-CM-EXEC"), clock)
    cache = Cache()
    client = MT5LiveExecClientFactory.create(
        loop=loop,
        name="MT5",
        config=_exec_config(cfg, account_id),
        msgbus=msgbus,
        cache=cache,
        clock=clock,
    )
    return client, cache


async def run_preflight_closed(cfg: HomologationConfig, report: HomologationReport) -> None:
    """TC-HOM-PF: bridge account + symbol_info (tick may be frozen when market closed)."""
    case_id = "TC-HOM-PF"
    name = "Bridge pre-flight (closed market — account + symbol_info)"

    try:
        conn = rpyc.connect(cfg.host, cfg.port)
        try:
            info = conn.root.account_info()
            login = int(_attr(info, "login"))
            server = _attr(info, "server", "")

            try:
                conn.root.symbol_select(cfg.symbol, True)
            except Exception:
                pass

            sym = conn.root.symbol_info(cfg.symbol)
            if sym is None:
                report.add(case_id, name, ScenarioStatus.FAIL, f"symbol_info({cfg.symbol}) is None")
                return

            digits = int(_attr(sym, "digits", 0))
            bookdepth = int(_attr(sym, "ticks_bookdepth", 0))
            tick = conn.root.symbol_info_tick(cfg.symbol)
            bid = _attr(tick, "bid", 0.0) if tick else 0.0
            ask = _attr(tick, "ask", 0.0) if tick else 0.0
            sym_time = _attr(sym, "time", 0)
        finally:
            conn.close()

        if str(login) != cfg.account_number:
            report.add(
                case_id,
                name,
                ScenarioStatus.FAIL,
                f"Account mismatch: env={cfg.account_number} bridge={login}",
            )
            return

        frozen_note = ""
        if bid <= 0 or ask <= 0:
            frozen_note = " (snapshot frozen — market closed; OK for closed-market run)"

        report.add(
            case_id,
            name,
            ScenarioStatus.PASS,
            f"login={login} server={server} {cfg.symbol} digits={digits} "
            f"ticks_bookdepth={bookdepth} bid={bid} ask={ask} symbol_time={sym_time}{frozen_note}",
            login=login,
            server=server,
            ticks_bookdepth=bookdepth,
        )
    except Exception as exc:
        report.add(case_id, name, ScenarioStatus.FAIL, str(exc))


async def run_instrument_load(cfg: HomologationConfig, report: HomologationReport) -> None:
    """TC-HOM-D01-CM: instrument provider loads symbol via data client connect."""
    case_id = "TC-HOM-D01-CM"
    name = "Instrument load via DataClient (closed market)"

    reset_mt5_client_cache()
    data_client, _, cache, clock = await _make_data_client(cfg)
    iid = _instrument_id(cfg.symbol)

    try:
        await data_client._connect()
        found = data_client.instrument_provider.find(iid)
        if found is None:
            report.add(case_id, name, ScenarioStatus.FAIL, f"{iid} not in provider after connect")
            return

        req = RequestInstrument(
            instrument_id=iid,
            start=None,
            end=None,
            client_id=data_client.id,
            venue=_VENUE,
            callback=None,
            request_id=UUID4(),
            ts_init=clock.timestamp_ns(),
            params=None,
        )
        await data_client._request_instrument(req)
        cached = cache.instrument(iid)
        if cached is None:
            report.add(case_id, name, ScenarioStatus.FAIL, "instrument not in cache after request")
            return

        report.add(
            case_id,
            name,
            ScenarioStatus.PASS,
            f"{iid} loaded digits={cached.info.get('digits')} calc_mode={cached.info.get('trade_calc_mode')}",
        )
    except Exception as exc:
        report.add(case_id, name, ScenarioStatus.FAIL, str(exc))
    finally:
        await data_client._disconnect()
        reset_mt5_client_cache()


async def _connected_mt5(cfg: HomologationConfig):
    """Single shared MetaTrader5Client session for closed-market historical probes."""
    reset_mt5_client_cache()
    data_client, _, _, _ = await _make_data_client(cfg)
    await data_client._connect()
    mt5 = data_client._client._mt5_client["mt5"]
    return data_client, mt5


async def run_historical_bars_rpyc(cfg: HomologationConfig, report: HomologationReport) -> None:
    """TC-HOM-D04a: historical M1+M5 via MetaTrader5 wrapper (real bridge path)."""
    case_id = "TC-HOM-D04a"
    name = "Historical bars M1+M5 via MetaTrader5Client → copy_rates_from_pos"

    data_client = None
    try:
        data_client, mt5 = await _connected_mt5(cfg)
        tf_m1 = mt5.TIMEFRAME_M1 if hasattr(mt5, "TIMEFRAME_M1") else 1
        tf_m5 = mt5.TIMEFRAME_M5 if hasattr(mt5, "TIMEFRAME_M5") else 5
        m1 = mt5.copy_rates_from_pos(cfg.symbol, tf_m1, 0, 5)
        m5 = mt5.copy_rates_from_pos(cfg.symbol, tf_m5, 0, 10)

        if m1 is None or len(m1) == 0:
            report.add(case_id, name, ScenarioStatus.FAIL, "No M1 bars from copy_rates_from_pos")
            return
        if m5 is None or len(m5) == 0:
            report.add(case_id, name, ScenarioStatus.FAIL, "No M5 bars from copy_rates_from_pos")
            return

        b = m1[0]
        report.add(
            case_id,
            name,
            ScenarioStatus.PASS,
            f"M1 bars={len(m1)} M5 bars={len(m5)} sample O={_attr(b, 'open')} H={_attr(b, 'high')} "
            f"L={_attr(b, 'low')} C={_attr(b, 'close')}",
            m1_count=len(m1),
            m5_count=len(m5),
        )
    except Exception as exc:
        report.add(case_id, name, ScenarioStatus.FAIL, str(exc))
    finally:
        if data_client is not None:
            await data_client._disconnect()
        reset_mt5_client_cache()


async def run_historical_quote_ticks(cfg: HomologationConfig, report: HomologationReport) -> None:
    """TC-HOM-D04c: historical quote ticks via copy_ticks_from (recent window)."""
    case_id = "TC-HOM-D04c"
    name = "Historical quote ticks via MetaTrader5Client → copy_ticks_from"

    data_client = None
    try:
        data_client, mt5 = await _connected_mt5(cfg)
        flags = mt5.COPY_TICKS_ALL if hasattr(mt5, "COPY_TICKS_ALL") else 0
        from_ts = int((datetime.now(timezone.utc) - timedelta(hours=24)).timestamp())
        ticks = mt5.copy_ticks_from(cfg.symbol, from_ts, 500, flags)

        if ticks is None or len(ticks) == 0:
            report.add(case_id, name, ScenarioStatus.FAIL, "copy_ticks_from returned empty")
            return

        sample = ticks[-1]
        bid = float(_attr(sample, "bid", 0) or 0)
        ask = float(_attr(sample, "ask", 0) or 0)
        last = float(_attr(sample, "last", 0) or 0)
        report.add(
            case_id,
            name,
            ScenarioStatus.PASS,
            f"ticks={len(ticks)} last_sample bid={bid} ask={ask} last={last}",
            tick_count=len(ticks),
            last_zero=(last == 0.0),
        )
    except Exception as exc:
        report.add(case_id, name, ScenarioStatus.FAIL, str(exc))
    finally:
        if data_client is not None:
            await data_client._disconnect()
        reset_mt5_client_cache()


async def run_unsupported_gates(cfg: HomologationConfig, report: HomologationReport) -> None:
    """TC-HOM-D08/D10/D02: VenueProfile and unsupported subscriptions (no raise)."""
    reset_mt5_client_cache()
    data_client, _, _, clock = await _make_data_client(cfg)
    iid = _instrument_id(cfg.symbol)

    try:
        await data_client._connect()

        # D10 order book
        book_cmd = SubscribeOrderBook(
            instrument_id=iid,
            book_data_type=OrderBookDelta,
            book_type=BookType.L1_MBP,
            client_id=data_client.id,
            venue=None,
            command_id=UUID4(),
            ts_init=clock.timestamp_ns(),
        )
        await data_client._subscribe_order_book_deltas(book_cmd)

        # D02 instruments
        inst_cmd = SubscribeInstruments(
            client_id=data_client.id,
            venue=_VENUE,
            command_id=UUID4(),
            ts_init=clock.timestamp_ns(),
        )
        await data_client._subscribe_instruments(inst_cmd)

        # D08 trade ticks subscribe — should not call bridge (VenueProfile gate)
        trade_cmd = SubscribeTradeTicks(
            instrument_id=iid,
            client_id=data_client.id,
            venue=None,
            command_id=UUID4(),
            ts_init=clock.timestamp_ns(),
        )
        await data_client._subscribe_trade_ticks(trade_cmd)

        report.add(
            "TC-HOM-D08",
            "TradeTick subscribe gated by VenueProfile",
            ScenarioStatus.PASS,
            "SubscribeTradeTicks returned without raise (UNSUPPORTED profile)",
        )
        report.add(
            "TC-HOM-D10",
            "Order book unsupported (warning only)",
            ScenarioStatus.PASS,
            "SubscribeOrderBook returned without raise",
        )
        report.add(
            "TC-HOM-D02",
            "SubscribeInstruments unsupported (warning only)",
            ScenarioStatus.PASS,
            "SubscribeInstruments returned without raise",
        )
    except Exception as exc:
        report.add("TC-HOM-D08", "Unsupported data gates", ScenarioStatus.FAIL, str(exc))
    finally:
        await data_client._disconnect()
        reset_mt5_client_cache()


async def run_exec_connect(cfg: HomologationConfig, report: HomologationReport) -> None:
    """TC-HOM-E-CONN: exec client validates account against bridge."""
    case_id = "TC-HOM-E-CONN"
    name = "ExecClient connect + account validation"

    reset_mt5_client_cache()
    exec_client, _ = await _make_exec_client(cfg)

    try:
        await exec_client._connect()
        report.add(case_id, name, ScenarioStatus.PASS, f"Connected account={cfg.account_number}")
    except Exception as exc:
        report.add(case_id, name, ScenarioStatus.FAIL, str(exc))
    finally:
        await exec_client._disconnect()
        reset_mt5_client_cache()


async def run_exec_wrong_account(cfg: HomologationConfig, report: HomologationReport) -> None:
    """TC-HOM-E-EDGE1: wrong account_id rejected on connect."""
    case_id = "TC-HOM-E-EDGE1"
    name = "ExecClient rejects wrong account_id"

    reset_mt5_client_cache()
    exec_client, _ = await _make_exec_client(cfg, account_id="99999999")

    try:
        await exec_client._connect()
        report.add(case_id, name, ScenarioStatus.FAIL, "Connect succeeded with wrong account_id")
    except Exception as exc:
        report.add(case_id, name, ScenarioStatus.PASS, f"Rejected as expected: {type(exc).__name__}")
    finally:
        try:
            await exec_client._disconnect()
        except Exception:
            pass
        reset_mt5_client_cache()


async def run_trade_tick_request_rejected(cfg: HomologationConfig, report: HomologationReport) -> None:
    """TC-HOM-D08b: _request_trade_ticks rejected by VenueProfile before bridge."""
    case_id = "TC-HOM-D08b"
    name = "RequestTradeTicks rejected by VenueProfile"

    reset_mt5_client_cache()
    data_client, _, cache, clock = await _make_data_client(cfg)
    iid = _instrument_id(cfg.symbol)

    try:
        await data_client._connect()
        await data_client.instrument_provider.load_async(iid)
        if cache.instrument(iid) is None:
            report.add(case_id, name, ScenarioStatus.FAIL, "instrument not loaded")
            return

        trade_req = RequestTradeTicks(
            instrument_id=iid,
            start=None,
            end=None,
            limit=5,
            client_id=data_client.id,
            venue=_VENUE,
            callback=None,
            request_id=UUID4(),
            ts_init=clock.timestamp_ns(),
            params=None,
        )
        await data_client._request_trade_ticks(trade_req)

        report.add(
            case_id,
            name,
            ScenarioStatus.PASS,
            "RequestTradeTicks returned without raise (VenueProfile UNSUPPORTED gate)",
        )
    except Exception as exc:
        report.add(case_id, name, ScenarioStatus.FAIL, str(exc))
    finally:
        await data_client._disconnect()
        reset_mt5_client_cache()


async def run_closed_market_suite(cfg: HomologationConfig, report: HomologationReport) -> None:
    """Run all closed-market homologation scenarios."""
    MT5_CLIENTS.clear()
    await run_preflight_closed(cfg, report)
    if report.has_failures:
        return

    await run_historical_bars_rpyc(cfg, report)
    await run_historical_quote_ticks(cfg, report)
    await run_instrument_load(cfg, report)
    await run_unsupported_gates(cfg, report)
    await run_trade_tick_request_rejected(cfg, report)
    await run_exec_connect(cfg, report)
    await run_exec_wrong_account(cfg, report)
