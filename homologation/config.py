"""Homologation environment configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass

import rpyc

from nautilus_mt5.venue_profile import VenueProfile, resolve_venue_profile


def _profile_defaults(profile_name: str) -> dict[str, str]:
    key = (profile_name or "tickmill").strip().lower().replace("-", "_")
    if key in ("amp", "amp_us", "amp_us_profile", "amp_global", "ampglobalusa"):
        return {
            "broker": "AMPGlobalUSA-Demo",
            "symbol": "MESU26",
            "account": "1588658",
            "multi_symbols": "EPU26,MESU26,ENQU26,MNQU26",
        }
    if key in ("xp", "xp_b3", "xp_b3_profile", "b3", "xpmt5"):
        return {
            "broker": "XPMT5-DEMO",
            "symbol": "WDOQ26",
            "account": "56822578",
            "multi_symbols": "WDOQ26,PETR4,DI1F27,WINQ26",
        }
    return {
        "broker": "Tickmill-Demo",
        "symbol": "BTCUSD",
        "account": "",
        "multi_symbols": "BTCUSD,USTEC",
    }


@dataclass(frozen=True)
class HomologationConfig:
    host: str
    port: int
    account_number: str
    broker: str
    symbol: str
    venue_profile_name: str
    enable_execution: bool
    min_quote_ticks: int
    scenario_timeout_secs: float
    stream_duration_secs: float
    stream_max_gap_secs: float
    stream_min_ticks: int
    skip_stream: bool
    feed_enabled: bool
    feed_host: str
    feed_port: int
    feed_path: str
    feed_hello_timeout_secs: float

    @property
    def venue_profile(self) -> VenueProfile:
        return resolve_venue_profile(self.venue_profile_name)

    @property
    def multi_symbols(self) -> tuple[str, ...]:
        defaults = _profile_defaults(self.venue_profile_name)
        raw = os.environ.get("HOMOLOG_MULTI_SYMBOLS", defaults["multi_symbols"])
        parts = tuple(s.strip() for s in raw.split(",") if s.strip())
        return parts if parts else (self.symbol,)

    @classmethod
    def from_env(cls) -> HomologationConfig:
        profile_name = os.environ.get("MT5_VENUE_PROFILE", "tickmill").strip()
        defaults = _profile_defaults(profile_name)

        host = os.environ.get("MT5_HOST", "127.0.0.1")
        port = int(os.environ.get("MT5_PORT", "18812"))
        symbol = os.environ.get("MT5_SYMBOL", defaults["symbol"])
        broker = os.environ.get("MT5_BROKER", defaults["broker"])
        enable_execution = os.environ.get("MT5_ENABLE_LIVE_EXECUTION", "").strip() == "1"
        min_ticks = int(os.environ.get("HOMOLOG_MIN_TICKS", "3"))
        timeout = float(os.environ.get("HOMOLOG_TIMEOUT_SECS", "120"))
        stream_duration = float(os.environ.get("HOMOLOG_STREAM_SECS", "120"))
        stream_max_gap = float(os.environ.get("HOMOLOG_STREAM_MAX_GAP_SECS", "30"))
        stream_min_ticks = int(os.environ.get("HOMOLOG_STREAM_MIN_TICKS", "5"))
        skip_stream = os.environ.get("HOMOLOG_SKIP_STREAM", "").strip() == "1"
        feed_enabled = os.environ.get("MT5_FEED_ENABLED", "").strip() == "1"
        feed_host = os.environ.get("MT5_FEED_HOST", "0.0.0.0")
        feed_port_raw = os.environ.get("MT5_FEED_PORT", "").strip()
        if feed_port_raw:
            feed_port = int(feed_port_raw)
        elif port == 18813:
            feed_port = 8766  # MT5-Docker xp profile
        elif port == 18814:
            feed_port = 8767  # MT5-Docker amp profile
        else:
            feed_port = 8765  # MT5-Docker tickmill / default
        feed_path = os.environ.get("MT5_FEED_PATH", "/mt5-feed")
        feed_hello_timeout = float(os.environ.get("MT5_FEED_HELLO_TIMEOUT_SECS", "30"))

        account = os.environ.get("MT5_ACCOUNT_NUMBER", defaults["account"]).strip()
        if not account:
            account = str(_probe_account_login(host, port))

        return cls(
            host=host,
            port=port,
            account_number=account,
            broker=broker,
            symbol=symbol,
            venue_profile_name=profile_name,
            enable_execution=enable_execution,
            min_quote_ticks=min_ticks,
            scenario_timeout_secs=timeout,
            stream_duration_secs=stream_duration,
            stream_max_gap_secs=stream_max_gap,
            stream_min_ticks=stream_min_ticks,
            skip_stream=skip_stream,
            feed_enabled=feed_enabled,
            feed_host=feed_host,
            feed_port=feed_port,
            feed_path=feed_path,
            feed_hello_timeout_secs=feed_hello_timeout,
        )


def _probe_account_login(host: str, port: int) -> int:
    conn = rpyc.connect(host, port)
    try:
        info = conn.root.account_info()
        if isinstance(info, dict):
            login = info.get("login")
        else:
            login = getattr(info, "login", None)
        if login is None:
            raise RuntimeError("MT5 bridge returned no account login — set MT5_ACCOUNT_NUMBER")
        return int(login)
    finally:
        conn.close()


def probe_symbol_tick(host: str, port: int, symbol: str) -> tuple[float, float] | None:
    conn = rpyc.connect(host, port)
    try:
        try:
            conn.root.symbol_select(symbol, True)
        except Exception:
            pass
        tick = conn.root.symbol_info_tick(symbol)
        if tick is None:
            return None
        if isinstance(tick, dict):
            bid, ask = float(tick["bid"]), float(tick["ask"])
        else:
            bid, ask = float(tick.bid), float(tick.ask)
        if bid <= 0.0 and ask <= 0.0:
            return None
        return bid, ask
    finally:
        conn.close()
