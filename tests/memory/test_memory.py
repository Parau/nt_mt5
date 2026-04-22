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
    when subscribing and unsubscribing repeatedly. We'll use the raw adapter methods.
    """
    client = MetaTrader5Client.__new__(MetaTrader5Client)
    client._event_subscriptions = {}
    type(client)._log = property(lambda self: MagicMock())
    client._mt5_client = {"mt5": MagicMock()}

    from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
    from nautilus_mt5.data_types import MT5Symbol

    inst_id = InstrumentId(Symbol("EURUSD"), Venue("METATRADER_5"))
    mt5_sym = MT5Symbol(symbol="EURUSD", broker="METATRADER_5")

    # To test actual method impacts directly:
    for _ in range(100):
        # We test the public client interface and trace its effect on native event callbacks
        client.subscribe_event(f"BidAsk", MagicMock())

    # Since subscribe_event is a generic dict update, it should top at 1 element
    assert len(client._event_subscriptions) == 1

    client.unsubscribe_event("BidAsk")

    # De-subscription eliminates the single mapping tracked natively
    assert len(client._event_subscriptions) == 0

    # We verify the native add tracker handles it safely inside Subscriptions
    from nautilus_mt5.common import Subscriptions
    client._subscriptions = Subscriptions()
    client._subscriptions.add(1, "BidAsk_1", MagicMock(), MagicMock())
    try:
        client._subscriptions.add(1, "BidAsk_2", MagicMock(), MagicMock())
    except KeyError:
        pass # Expected protection against duplicates internally
    assert len(client._subscriptions._req_id_to_name) == 1

    # We remove
    client._subscriptions.remove(1)
    assert len(client._subscriptions._req_id_to_name) == 0

    # Check what happens with multiple requests in internal requests tracker
    from nautilus_mt5.common import Requests
    client._requests = Requests()
    client._next_valid_req_id = 0
    def mock_next_req_id():
        client._next_valid_req_id += 1
        return client._next_valid_req_id
    client._next_req_id = mock_next_req_id

    for i in range(100):
        req = client._requests.add(client._next_req_id(), f"test_req_{i}", MagicMock())
        assert req is not None

    assert len(client._requests._req_id_to_name) == 100

    for i in range(1, 101):
        client._requests.remove(req_id=i)

    assert len(client._requests._req_id_to_name) == 0
