import pytest

from nautilus_mt5.factories import MT5LiveDataClientFactory, MT5LiveExecClientFactory

def test_factories_imports():
    assert MT5LiveDataClientFactory is not None
    assert MT5LiveExecClientFactory is not None
