import pytest
from nautilus_trader.common.component import MessageBus, LiveClock
from nautilus_trader.cache.cache import Cache
from nautilus_trader.model.identifiers import TraderId

@pytest.fixture
def nautilus_components():
    """
    Fixture to provide real NautilusTrader components.
    """
    clock = LiveClock()
    msgbus = MessageBus(TraderId("TEST-1"), clock)
    cache = Cache()
    return msgbus, cache, clock
