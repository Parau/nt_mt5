"""
Shared fixtures for Nautilus-level integration tests of the MT5 adapter.

These tests exercise the full path:
    Factory → MetaTrader5DataClient / MetaTrader5ExecutionClient
           → MetaTrader5Client → fake RPyC bridge

No real MT5 terminal, gateway, or network is required.

Layer context
-------------
This directory (tests/integration_tests/adapters/mt5/) is the canonical
NautilusTrader integration test location for Python adapters. Tests here
validate behaviour observable through the public adapter API: instrument
loading, data subscriptions, order events, factory wiring, and config
validation.

For tests that target MetaTrader5Client internals directly (connection
lifecycle, retcode handling, raw RPyC call translation) without going through
the high-level adapter stack, see tests/integration/ instead.
"""
import asyncio

import pytest
import rpyc

from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_trader.model.identifiers import TraderId

from nautilus_mt5.client.client import MetaTrader5Client
from nautilus_mt5.factories import MT5_CLIENTS
from tests.support.fake_mt5_rpyc_bridge import FakeMT5RPyCConnection


@pytest.fixture
def clean_factory_cache():
    """Clear the MT5_CLIENTS singleton cache before and after each test."""
    MT5_CLIENTS.clear()
    yield
    MT5_CLIENTS.clear()


@pytest.fixture
def nautilus_components():
    """Real NautilusTrader components (clock, msgbus, cache)."""
    clock = LiveClock()
    msgbus = MessageBus(TraderId("TESTER-1"), clock)
    cache = Cache()
    return msgbus, cache, clock


@pytest.fixture
def fake_conn():
    """A fresh FakeMT5RPyCConnection for each test."""
    return FakeMT5RPyCConnection()


@pytest.fixture
def nautilus_mt5_harness(monkeypatch, fake_conn):
    """
    Full deterministic harness for Nautilus-level MT5 integration tests.

    Sets up:
    - ``rpyc.connect`` monkeypatched → returns ``fake_conn``
    - ``MetaTrader5Client._start`` monkeypatched → marks client ready immediately
      (suppresses the background ``_start_async`` so it does not race with
      ``_connect()`` called inside ``data_client._connect()`` / ``exec_client._connect()``)

    Returns the ``FakeMT5RPyCConnection`` so tests can inspect recorded calls.
    """
    # 1. Redirect all rpyc connections to the fake.
    monkeypatch.setattr(rpyc, "connect", lambda *a, **kw: fake_conn)

    # 2. Replace the background start so it does not call _connect() concurrently.
    def _fake_mt5client_start(self):
        """Mark client ready without launching background tasks."""
        if self._loop.is_running():
            async def _set_ready():
                self._is_client_ready.set()
            self._create_task(_set_ready())

    monkeypatch.setattr(MetaTrader5Client, "_start", _fake_mt5client_start)

    return fake_conn
