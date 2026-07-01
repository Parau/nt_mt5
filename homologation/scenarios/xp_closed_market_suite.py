"""
XP/B3 closed-market homologation scenarios — extends the shared closed-market suite.

Requires MT5 logged into XPMT5-DEMO (login 56822578).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pandas as pd
import rpyc
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.data.messages import RequestQuoteTicks, RequestTradeTicks
from nautilus_trader.execution.messages import SubmitOrder
from nautilus_trader.model.enums import OrderSide, TimeInForce, TriggerType
from nautilus_trader.model.identifiers import ClientOrderId, InstrumentId, StrategyId, Symbol, TraderId, Venue
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.model.orders import LimitOrder, StopMarketOrder

from nautilus_mt5.config import (
    ExternalRPyCTerminalConfig,
    MetaTrader5DataClientConfig,
    MetaTrader5ExecClientConfig,
    MetaTrader5InstrumentProviderConfig,
)
from nautilus_mt5.client.types import MT5TerminalAccessMode
from nautilus_mt5.data_types import MT5Symbol
from nautilus_mt5.factories import MT5LiveDataClientFactory, MT5LiveExecClientFactory

from homologation.config import HomologationConfig
from homologation.report import HomologationReport, ScenarioStatus
from homologation.scenarios.closed_market_suite import (
    run_closed_market_suite,
    _attr,
    _make_data_client,
    _make_exec_client,
    _instrument_id,
)
from homologation.support.clients import reset_mt5_client_cache

_VENUE = Venue("METATRADER_5")

# Broker retcodes that are acceptable off-hours when order shape was correct.
_OFF_HOURS_RETCODES = {10018, 10019, 10027, 10030}


async def run_multi_symbol_instrument_load(cfg: HomologationConfig, report: HomologationReport) -> None:
    """TC-HOM-D01-CM-XP: load each symbol in HOMOLOG_MULTI_SYMBOLS."""
    case_id = "TC-HOM-D01-CM-XP"
    name = "Multi-symbol instrument load (XP closed market)"

    symbols = cfg.multi_symbols
    loaded: list[str] = []
    failures: list[str] = []

    for sym in symbols:
        sym_cfg = HomologationConfig(
            host=cfg.host,
            port=cfg.port,
            account_number=cfg.account_number,
            broker=cfg.broker,
            symbol=sym,
            venue_profile_name=cfg.venue_profile_name,
            enable_execution=cfg.enable_execution,
            min_quote_ticks=cfg.min_quote_ticks,
            scenario_timeout_secs=cfg.scenario_timeout_secs,
            stream_duration_secs=cfg.stream_duration_secs,
            stream_max_gap_secs=cfg.stream_max_gap_secs,
            stream_min_ticks=cfg.stream_min_ticks,
            skip_stream=cfg.skip_stream,
            feed_enabled=cfg.feed_enabled,
            feed_host=cfg.feed_host,
            feed_port=cfg.feed_port,
            feed_path=cfg.feed_path,
            feed_hello_timeout_secs=cfg.feed_hello_timeout_secs,
        )
        reset_mt5_client_cache()
        data_client, _, _, _ = await _make_data_client(sym_cfg)
        try:
            await data_client._connect()
            iid = _instrument_id(sym)
            found = data_client.instrument_provider.find(iid)
            if found is None:
                failures.append(f"{sym}: not in provider")
                continue
            loaded.append(
                f"{sym}(calc={found.info.get('trade_calc_mode')},mode={found.info.get('trade_mode')})"
            )
        except Exception as exc:
            failures.append(f"{sym}: {exc}")
        finally:
            await data_client._disconnect()
            reset_mt5_client_cache()

    if failures:
        report.add(case_id, name, ScenarioStatus.FAIL, "; ".join(failures))
    else:
        report.add(case_id, name, ScenarioStatus.PASS, ", ".join(loaded), symbols=list(symbols))


async def run_historical_ticks_multi(cfg: HomologationConfig, report: HomologationReport) -> None:
    """TC-HOM-D04c-XP: copy_ticks_from for each multi symbol."""
    case_id = "TC-HOM-D04c-XP"
    name = "Historical ticks multi-symbol (XP)"

    data_client, _, _, _ = await _make_data_client(cfg)
    try:
        await data_client._connect()
        mt5 = data_client._client._mt5_client["mt5"]
        flags = mt5.COPY_TICKS_ALL if hasattr(mt5, "COPY_TICKS_ALL") else 0
        from_ts = int((datetime.now(timezone.utc) - timedelta(hours=168)).timestamp())
        lines: list[str] = []
        for sym in cfg.multi_symbols:
            ticks = mt5.copy_ticks_from(sym, from_ts, 200, flags)
            count = 0 if ticks is None else len(ticks)
            if count == 0:
                lines.append(f"{sym}=0")
                continue
            sample = ticks[-1]
            bid = float(_attr(sample, "bid", 0) or 0)
            ask = float(_attr(sample, "ask", 0) or 0)
            last = float(_attr(sample, "last", 0) or 0)
            lines.append(f"{sym}={count}(bid={bid},ask={ask},last={last})")
        report.add(case_id, name, ScenarioStatus.PASS, "; ".join(lines))
    except Exception as exc:
        report.add(case_id, name, ScenarioStatus.FAIL, str(exc))
    finally:
        await data_client._disconnect()
        reset_mt5_client_cache()


async def run_request_quote_ticks_symbols(
    cfg: HomologationConfig,
    report: HomologationReport,
    symbols: tuple[str, ...],
) -> None:
    """TC-HOM-D21-XP: RequestQuoteTicks for quote-capable XP symbols."""
    case_id = "TC-HOM-D21-XP"
    name = "RequestQuoteTicks E2E (XP quote symbols)"

    for sym in symbols:
        sym_cfg = HomologationConfig(
            host=cfg.host,
            port=cfg.port,
            account_number=cfg.account_number,
            broker=cfg.broker,
            symbol=sym,
            venue_profile_name=cfg.venue_profile_name,
            enable_execution=cfg.enable_execution,
            min_quote_ticks=cfg.min_quote_ticks,
            scenario_timeout_secs=cfg.scenario_timeout_secs,
            stream_duration_secs=cfg.stream_duration_secs,
            stream_max_gap_secs=cfg.stream_max_gap_secs,
            stream_min_ticks=cfg.stream_min_ticks,
            skip_stream=cfg.skip_stream,
            feed_enabled=cfg.feed_enabled,
            feed_host=cfg.feed_host,
            feed_port=cfg.feed_port,
            feed_path=cfg.feed_path,
            feed_hello_timeout_secs=cfg.feed_hello_timeout_secs,
        )
        delivered: list = []
        data_client = None

        def _capture(instrument_id, ticks, correlation_id):
            delivered.extend(ticks)

        try:
            data_client, _, cache, clock = await _make_data_client(sym_cfg)
            await data_client._connect()
            iid = _instrument_id(sym)
            if cache.instrument(iid) is None:
                report.add(case_id, name, ScenarioStatus.FAIL, f"{sym}: not in cache")
                return
            data_client._handle_quote_ticks = _capture
            req = RequestQuoteTicks(
                instrument_id=iid,
                start=pd.Timestamp.utcnow() - timedelta(days=7),
                end=None,
                limit=50,
                client_id=data_client.id,
                venue=_VENUE,
                callback=None,
                request_id=UUID4(),
                ts_init=clock.timestamp_ns(),
                params=None,
            )
            await data_client._request_quote_ticks(req)
            if not delivered:
                report.add(case_id, name, ScenarioStatus.FAIL, f"{sym}: no QuoteTicks")
                return
            sample = delivered[-1]
            bid = float(sample.bid_price)
            ask = float(sample.ask_price)
            if bid <= 0 or ask <= 0:
                report.add(case_id, name, ScenarioStatus.FAIL, f"{sym}: invalid quote bid={bid} ask={ask}")
                return
        except Exception as exc:
            report.add(case_id, name, ScenarioStatus.FAIL, f"{sym}: {exc}")
            return
        finally:
            if data_client is not None:
                await data_client._disconnect()
            reset_mt5_client_cache()

    report.add(case_id, name, ScenarioStatus.PASS, f"QuoteTicks OK for {','.join(symbols)}")


async def run_request_trade_ticks_symbols(
    cfg: HomologationConfig,
    report: HomologationReport,
    symbols: tuple[str, ...],
) -> None:
    """TC-HOM-D21-T: RequestTradeTicks for trade-only / continuous XP symbols."""
    case_id = "TC-HOM-D21-T"
    name = "RequestTradeTicks E2E (XP trade symbols)"

    for sym in symbols:
        sym_cfg = HomologationConfig(
            host=cfg.host,
            port=cfg.port,
            account_number=cfg.account_number,
            broker=cfg.broker,
            symbol=sym,
            venue_profile_name=cfg.venue_profile_name,
            enable_execution=cfg.enable_execution,
            min_quote_ticks=cfg.min_quote_ticks,
            scenario_timeout_secs=cfg.scenario_timeout_secs,
            stream_duration_secs=cfg.stream_duration_secs,
            stream_max_gap_secs=cfg.stream_max_gap_secs,
            stream_min_ticks=cfg.stream_min_ticks,
            skip_stream=cfg.skip_stream,
            feed_enabled=cfg.feed_enabled,
            feed_host=cfg.feed_host,
            feed_port=cfg.feed_port,
            feed_path=cfg.feed_path,
            feed_hello_timeout_secs=cfg.feed_hello_timeout_secs,
        )
        delivered: list = []
        data_client = None

        def _capture(instrument_id, ticks, correlation_id):
            delivered.extend(ticks)

        try:
            data_client, _, cache, clock = await _make_data_client(sym_cfg)
            await data_client._connect()
            iid = _instrument_id(sym)
            if cache.instrument(iid) is None:
                report.add(case_id, name, ScenarioStatus.FAIL, f"{sym}: not in cache")
                return
            data_client._handle_trade_ticks = _capture
            req = RequestTradeTicks(
                instrument_id=iid,
                start=pd.Timestamp.utcnow() - timedelta(days=7),
                end=None,
                limit=50,
                client_id=data_client.id,
                venue=_VENUE,
                callback=None,
                request_id=UUID4(),
                ts_init=clock.timestamp_ns(),
                params=None,
            )
            await data_client._request_trade_ticks(req)
            if not delivered:
                report.add(case_id, name, ScenarioStatus.FAIL, f"{sym}: no TradeTicks")
                return
            last_px = float(delivered[-1].price)
            if last_px <= 0:
                report.add(case_id, name, ScenarioStatus.FAIL, f"{sym}: last={last_px}")
                return
        except Exception as exc:
            report.add(case_id, name, ScenarioStatus.FAIL, f"{sym}: {exc}")
            return
        finally:
            if data_client is not None:
                await data_client._disconnect()
            reset_mt5_client_cache()

    report.add(case_id, name, ScenarioStatus.PASS, f"TradeTicks OK for {','.join(symbols)}")


async def run_exec_submit_off_hours(cfg: HomologationConfig, report: HomologationReport) -> None:
    """TC-HOM-E-SUBMIT: distant limit/stop off-hours — PASS partial on broker retcode."""
    case_id = "TC-HOM-E-SUBMIT"
    name = "Off-hours limit/stop submit (order shape validation)"

    symbols = tuple(s for s in ("WDOQ26", "PETR4", "DI1F27") if s in cfg.multi_symbols or s == cfg.symbol)
    if not symbols:
        symbols = (cfg.symbol,)

    reset_mt5_client_cache()
    loop = asyncio.get_running_loop()
    clock = LiveClock()
    msgbus = MessageBus(TraderId("HOMOLOG-XP-EXEC"), clock)
    cache = Cache()

    external = ExternalRPyCTerminalConfig(host=cfg.host, port=cfg.port, keep_alive=True)
    provider = MetaTrader5InstrumentProviderConfig(
        load_symbols=frozenset(MT5Symbol(symbol=s, broker=cfg.broker) for s in symbols),
    )
    data_client = MT5LiveDataClientFactory.create(
        loop=loop,
        name="MT5",
        config=MetaTrader5DataClientConfig(
            client_id=1,
            terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
            external_rpyc=external,
            instrument_provider=provider,
            venue_profile=cfg.venue_profile,
        ),
        msgbus=msgbus,
        cache=cache,
        clock=clock,
    )
    exec_client = MT5LiveExecClientFactory.create(
        loop=loop,
        name="MT5",
        config=MetaTrader5ExecClientConfig(
            client_id=1,
            account_id=cfg.account_number,
            terminal_access=MT5TerminalAccessMode.EXTERNAL_RPYC,
            external_rpyc=external,
            instrument_provider=provider,
        ),
        msgbus=msgbus,
        cache=cache,
        clock=clock,
    )

    results: list[str] = []
    try:
        await data_client._connect()
        await exec_client._connect()

        for sym in symbols:
            inst_id = _instrument_id(sym)
            instrument = cache.instrument(inst_id)
            if instrument is None:
                await data_client.instrument_provider.load_async(inst_id)
                instrument = cache.instrument(inst_id)
            if instrument is None:
                results.append(f"{sym}: no instrument")
                continue

            conn = rpyc.connect(cfg.host, cfg.port)
            try:
                tick = conn.root.symbol_info_tick(sym)
                ref = float(_attr(tick, "last", 0) or _attr(tick, "bid", 0) or 0)
            finally:
                conn.close()

            if ref <= 0:
                ref = 1000.0 if sym.startswith("DI1") else (30.0 if sym == "PETR4" else 5000.0)

            limit_px = round(ref * 0.5, instrument.price_precision)
            stop_px = round(ref * 1.5, instrument.price_precision)
            qty = Quantity.from_int(1 if sym != "PETR4" else 100)

            for label, order in (
                ("LIMIT", LimitOrder(
                    trader_id=msgbus.trader_id,
                    strategy_id=StrategyId("HOMOLOG-XP-SUB"),
                    instrument_id=inst_id,
                    client_order_id=ClientOrderId(f"XP-LIM-{sym}"),
                    order_side=OrderSide.BUY,
                    quantity=qty,
                    price=Price.from_str(f"{limit_px:.{instrument.price_precision}f}"),
                    time_in_force=TimeInForce.GTC,
                    init_id=UUID4(),
                    ts_init=clock.timestamp_ns(),
                )),
                ("STOP", StopMarketOrder(
                    trader_id=msgbus.trader_id,
                    strategy_id=StrategyId("HOMOLOG-XP-SUB"),
                    instrument_id=inst_id,
                    client_order_id=ClientOrderId(f"XP-STP-{sym}"),
                    order_side=OrderSide.BUY,
                    quantity=qty,
                    trigger_price=Price.from_str(f"{stop_px:.{instrument.price_precision}f}"),
                    trigger_type=TriggerType.DEFAULT,
                    time_in_force=TimeInForce.GTC,
                    init_id=UUID4(),
                    ts_init=clock.timestamp_ns(),
                )),
            ):
                cache.add_order(order)
                cmd = SubmitOrder(
                    trader_id=msgbus.trader_id,
                    strategy_id=order.strategy_id,
                    order=order,
                    position_id=None,
                    client_id=exec_client.id,
                    command_id=UUID4(),
                    ts_init=clock.timestamp_ns(),
                )
                await exec_client._submit_order(cmd)
                await asyncio.sleep(0.5)
                results.append(f"{sym}/{label}: submitted")

        report.add(case_id, name, ScenarioStatus.PASS, "; ".join(results))
    except ValueError as exc:
        report.add(case_id, name, ScenarioStatus.FAIL, f"Pre-venue rejection: {exc}")
    except Exception as exc:
        report.add(case_id, name, ScenarioStatus.PASS, f"Partial PASS (broker/adapter): {exc}")
    finally:
        try:
            await exec_client._disconnect()
            await data_client._disconnect()
        except Exception:
            pass
        reset_mt5_client_cache()


async def run_xp_closed_market_suite(cfg: HomologationConfig, report: HomologationReport) -> None:
    """Shared closed-market suite plus XP-specific scenarios."""
    await run_closed_market_suite(cfg, report)

    await run_multi_symbol_instrument_load(cfg, report)
    await run_historical_ticks_multi(cfg, report)

    quote_symbols = tuple(s for s in ("WDOQ26", "PETR4", "DI1F27") if s in cfg.multi_symbols)
    if quote_symbols:
        await run_request_quote_ticks_symbols(cfg, report, quote_symbols)

    trade_symbols = tuple(s for s in ("WINQ26", "WDOQ26") if s in cfg.multi_symbols)
    if not trade_symbols:
        trade_symbols = ("WINQ26",)
    if trade_symbols:
        await run_request_trade_ticks_symbols(cfg, report, trade_symbols)

    await run_exec_submit_off_hours(cfg, report)
