"""Homologation environment configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass

import rpyc


@dataclass(frozen=True)
class HomologationConfig:
    host: str
    port: int
    account_number: str
    broker: str
    symbol: str
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

    @classmethod
    def from_env(cls) -> HomologationConfig:
        host = os.environ.get("MT5_HOST", "127.0.0.1")
        port = int(os.environ.get("MT5_PORT", "18812"))
        symbol = os.environ.get("MT5_SYMBOL", "BTCUSD")  # default: crypto open 24/7 on Tickmill
        broker = os.environ.get("MT5_BROKER", "Tickmill-Demo")
        enable_execution = os.environ.get("MT5_ENABLE_LIVE_EXECUTION", "").strip() == "1"
        min_ticks = int(os.environ.get("HOMOLOG_MIN_TICKS", "3"))
        timeout = float(os.environ.get("HOMOLOG_TIMEOUT_SECS", "120"))
        stream_duration = float(os.environ.get("HOMOLOG_STREAM_SECS", "120"))
        stream_max_gap = float(os.environ.get("HOMOLOG_STREAM_MAX_GAP_SECS", "30"))
        stream_min_ticks = int(os.environ.get("HOMOLOG_STREAM_MIN_TICKS", "5"))
        skip_stream = os.environ.get("HOMOLOG_SKIP_STREAM", "").strip() == "1"
        feed_enabled = os.environ.get("MT5_FEED_ENABLED", "").strip() == "1"
        feed_host = os.environ.get("MT5_FEED_HOST", "0.0.0.0")
        feed_port = int(os.environ.get("MT5_FEED_PORT", "8765"))
        feed_path = os.environ.get("MT5_FEED_PATH", "/mt5-feed")
        feed_hello_timeout = float(os.environ.get("MT5_FEED_HELLO_TIMEOUT_SECS", "30"))

        account = os.environ.get("MT5_ACCOUNT_NUMBER", "").strip()
        if not account:
            account = str(_probe_account_login(host, port))

        return cls(
            host=host,
            port=port,
            account_number=account,
            broker=broker,
            symbol=symbol,
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
        tick = conn.root.symbol_info_tick(symbol)
        if tick is None:
            return None
        if isinstance(tick, dict):
            return float(tick["bid"]), float(tick["ask"])
        return float(tick.bid), float(tick.ask)
    finally:
        conn.close()
