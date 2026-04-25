import pytest
import rpyc
from tests.support.fake_mt5_rpyc_bridge import make_fake_mt5_rpyc_connection

@pytest.fixture
def fake_external_rpyc_environment(monkeypatch):
    """
    Fixture to setup a fake RPyC environment by monkeypatching rpyc.connect.
    Returns the fake connection root.
    """
    fake_connection = make_fake_mt5_rpyc_connection()
    fake_root = fake_connection.root

    def mock_rpyc_connect(host, port, config=None, keepalive=False):
        return fake_connection

    monkeypatch.setattr(rpyc, "connect", mock_rpyc_connect)
    return fake_root
