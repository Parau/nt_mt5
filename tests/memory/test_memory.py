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
    from nautilus_trader.common.component import LiveClock, MessageBus
    from nautilus_trader.cache.cache import Cache
    from nautilus_trader.model.identifiers import TraderId

    clock = LiveClock()
    msgbus = MessageBus(TraderId("TEST-MEM-1"), clock)
    cache = Cache()

    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    client = MetaTrader5Client.__new__(MetaTrader5Client)
    client._loop = loop
    type(client)._msgbus = property(lambda self: msgbus)
    type(client)._cache = property(lambda self: cache)
    type(client)._clock = property(lambda self: clock)
    type(client)._log = property(lambda self: MagicMock())

    from nautilus_mt5.client.types import TerminalConnectionMode
    client._terminal_connection_mode = TerminalConnectionMode.IPC
    client._mt5_client = {'mt5': None, 'ea': None}
    client._conn_state = MagicMock()
    client._conn_state.value = 0
    client._is_mt5_connected = asyncio.Event()
    client._is_client_ready = asyncio.Event()

    from nautilus_mt5.common import Subscriptions, Requests
    client._subscriptions = Subscriptions()
    client._internal_msg_queue = asyncio.Queue()
    client._requests = Requests()
    client._msg_handler_task_queue = asyncio.Queue()
    type(client).is_disposed = property(lambda self: False)
    client._config = MagicMock()
    client._client_id = 1

    # Override internal factories to return the Fake service without calling RPyC natively
    mock_mt5 = MagicMock()
    mock_mt5.last_error.return_value = (1, "Mock Error")

    async def fake_fetch_terminal_info():
        client._terminal_info = {
            "version": 5,
            "build": 1234,
            "build_release_date": "Unavailable",
            "connection_time": "Unavailable"
        }

    with patch.object(client, '_create_ipc_client', return_value=mock_mt5), \
         patch.object(client, '_create_ea_client', return_value=None), \
         patch.object(client, '_start_connection_watchdog'), \
         patch.object(client, '_start_terminal_incoming_msg_reader'), \
         patch.object(client, '_start_internal_msg_queue_processor'), \
         patch.object(client, '_fetch_terminal_info', new_callable=AsyncMock, side_effect=fake_fetch_terminal_info):

        for _ in range(10):
            await client._connect()

            assert client._mt5_client['mt5'] is not None

            await client._disconnect()

            assert client._mt5_client['mt5'] is None
            assert client._is_mt5_connected.is_set() is False

        # The core check here is that structures are reset or haven't accumulated mock connections
        assert client._is_mt5_connected.is_set() is False
        assert client._internal_msg_queue.qsize() == 0
        assert client._msg_handler_task_queue.qsize() == 0
        assert len(client._requests.get_futures()) == 0

        # Verify that all Subscriptions mappings are clean
        assert len(client._subscriptions._req_id_to_name) == 0
        assert len(client._subscriptions._req_id_to_handle) == 0
        assert len(client._subscriptions._req_id_to_cancel) == 0
        assert len(client._subscriptions._req_id_to_last) == 0

        # Verify that all Requests mappings are clean
        assert len(client._requests._req_id_to_name) == 0
        assert len(client._requests._req_id_to_handle) == 0
        assert len(client._requests._req_id_to_cancel) == 0
        assert len(client._requests._req_id_to_future) == 0
        assert len(client._requests._req_id_to_result) == 0

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
    assert len(client._subscriptions._req_id_to_handle) == 1
    assert len(client._subscriptions._req_id_to_cancel) == 1
    assert len(client._subscriptions._req_id_to_last) == 1

    # We remove
    client._subscriptions.remove(1)

    assert len(client._subscriptions._req_id_to_name) == 0
    assert len(client._subscriptions._req_id_to_handle) == 0
    assert len(client._subscriptions._req_id_to_cancel) == 0
    assert len(client._subscriptions._req_id_to_last) == 0

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
    assert len(client._requests._req_id_to_handle) == 100
    assert len(client._requests._req_id_to_cancel) == 100
    assert len(client._requests._req_id_to_future) == 100
    assert len(client._requests._req_id_to_result) == 100

    for i in range(1, 101):
        client._requests.remove(req_id=i)

    assert len(client._requests._req_id_to_name) == 0
    assert len(client._requests._req_id_to_handle) == 0
    assert len(client._requests._req_id_to_cancel) == 0
    assert len(client._requests._req_id_to_future) == 0
    assert len(client._requests._req_id_to_result) == 0
