import pytest
from collections import namedtuple
from nautilus_mt5.metatrader5.utils import normalize_rpyc_return

class FakeRemoteObject:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

class FakeRemoteAsDict:
    def __init__(self, data):
        self.data = data
    def _asdict(self):
        return self.data

def test_normalize_scalars():
    assert normalize_rpyc_return(None) is None
    assert normalize_rpyc_return(True) is True
    assert normalize_rpyc_return(123) == 123
    assert normalize_rpyc_return(123.45) == 123.45
    assert normalize_rpyc_return("hello") == "hello"
    assert normalize_rpyc_return(b"bytes") == b"bytes"

def test_normalize_list():
    data = [1, "two", FakeRemoteObject(val=3)]
    normalized = normalize_rpyc_return(data)
    assert normalized == [1, "two", {"val": 3}]
    assert isinstance(normalized, list)

def test_normalize_dict():
    data = {"a": 1, "b": FakeRemoteObject(val=2)}
    normalized = normalize_rpyc_return(data)
    assert normalized == {"a": 1, "b": {"val": 2}}
    assert isinstance(normalized, dict)

def test_normalize_namedtuple_with_asdict():
    AccountInfo = namedtuple("AccountInfo", "login balance currency")
    payload = AccountInfo(login=123456, balance=100000.0, currency="USD")
    normalized = normalize_rpyc_return(payload)
    assert normalized == {
        "login": 123456,
        "balance": 100000.0,
        "currency": "USD",
    }
    assert isinstance(normalized, dict)

def test_normalize_asdict_object():
    payload = FakeRemoteAsDict({"login": 123456, "balance": 100000.0})
    normalized = normalize_rpyc_return(payload)
    assert normalized == {"login": 123456, "balance": 100000.0}
    assert isinstance(normalized, dict)

def test_normalize_nested_structures():
    data = {
        "account": FakeRemoteAsDict({"login": 123456}),
        "positions": [FakeRemoteObject(symbol="EURUSD")],
        "metadata": {"source": "external_rpyc"},
    }
    normalized = normalize_rpyc_return(data)
    assert normalized == {
        "account": {"login": 123456},
        "positions": [{"symbol": "EURUSD"}],
        "metadata": {"source": "external_rpyc"},
    }

def test_ensure_no_fake_remote_leaks():
    data = [FakeRemoteObject(a=FakeRemoteObject(b=1))]
    normalized = normalize_rpyc_return(data)

    def check_leaks(obj):
        if isinstance(obj, (FakeRemoteObject, FakeRemoteAsDict)):
            pytest.fail(f"Leaked {type(obj)}")
        if isinstance(obj, dict):
            for v in obj.values():
                check_leaks(v)
        elif isinstance(obj, (list, tuple)):
            for item in obj:
                check_leaks(item)

    check_leaks(normalized)
    assert normalized == [{"a": {"b": 1}}]
