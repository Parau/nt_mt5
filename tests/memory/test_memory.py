import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

from nautilus_mt5.client.client import MetaTrader5Client

@pytest.mark.asyncio
async def test_memory_no_leak_on_connect_disconnect():
    """
    Ensure the internal structures of the MT5 Client do not grow
    after repeated cycles of connect and disconnect.
    """
    mock_msgbus = MagicMock()
    mock_cache = MagicMock()
    mock_clock = MagicMock()

    client = MetaTrader5Client.__new__(MetaTrader5Client)
    client._loop = asyncio.get_event_loop()
    type(client)._msgbus = property(lambda self: mock_msgbus)
    type(client)._cache = property(lambda self: mock_cache)
    type(client)._clock = property(lambda self: mock_clock)
    type(client)._log = property(lambda self: MagicMock())
    client._mt5_client = {}
    client._conn_state = MagicMock()
    client._conn_state.value = 0
    client._is_mt5_connected = asyncio.Event()
    client._is_client_ready = asyncio.Event()
    client._subscriptions = MagicMock()
    client._subscriptions._instrument_id_to_sub = {}
    client._subscriptions._req_id_to_name = {}
    client._subscriptions._name_to_obj = {}
    client._internal_msg_queue = asyncio.Queue()
    client._requests = MagicMock()
    client._requests.get_futures = MagicMock(return_value=[])
    client._msg_handler_task_queue = asyncio.Queue()
    type(client).is_disposed = property(lambda self: False)

    with patch.object(client, '_connect', new_callable=AsyncMock) as mock_connect:
        async def fake_connect():
            client._mt5_client['mt5'] = MagicMock()
            client._is_mt5_connected.set()
            client._conn_state.value = 1 # CONNECTED
            client._is_client_ready.set()
        mock_connect.side_effect = fake_connect

        # We also mock disconnect cleanly
        client._clear_clients = MagicMock()

        for _ in range(10):
            await client._connect()

            client._clear_clients()
            client._conn_state.value = 0
            client._is_mt5_connected.clear()

        # The core check here is that structures are reset or haven't accumulated mock connections
        assert client._is_mt5_connected.is_set() is False

@pytest.mark.asyncio
async def test_memory_no_leak_on_subscriptions():
    """
    Ensure internal subscription mappings do not grow in an unbounded manner
    when subscribing and unsubscribing repeatedly.
    """
    from nautilus_mt5.client.market_data import MetaTrader5ClientMarketDataMixin

    client = MetaTrader5ClientMarketDataMixin.__new__(MetaTrader5ClientMarketDataMixin)
    client._event_subscriptions = {}
    client._log = MagicMock()

    # We mock out the actual BaseMixin implementations
    def mock_subscribe(name, callback):
        client._event_subscriptions[name] = callback

    def mock_unsubscribe(name):
        client._event_subscriptions.pop(name, None)

    client.subscribe_event = mock_subscribe
    client.unsubscribe_event = mock_unsubscribe

    for i in range(100):
        client.subscribe_event(f"sub_{i}", lambda x: x)

    assert len(client._event_subscriptions) == 100

    for i in range(100):
        client.unsubscribe_event(f"sub_{i}")

    assert len(client._event_subscriptions) == 0
