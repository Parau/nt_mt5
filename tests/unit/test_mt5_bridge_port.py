"""Regression tests for RPyC bridge bind port configuration."""
from __future__ import annotations

import os
from pathlib import Path

_BRIDGE_DIR = Path(__file__).resolve().parents[2] / "MQL5" / "refactoring" / "bridge"


def _main_block(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    marker = 'if __name__ == "__main__":'
    assert marker in text
    return text.split(marker, 1)[1]


def test_mt5_bridge_uses_rpyc_port_env():
    main = _main_block(_BRIDGE_DIR / "mt5_bridge.py")
    assert 'os.environ.get("RPYC_PORT", "18812")' in main
    assert "port=rpyc_port" in main
    assert "port=18812" not in main


def test_mt5_bridge_v008_uses_rpyc_port_env():
    main = _main_block(_BRIDGE_DIR / "mt5_bridge_v008.py")
    assert 'os.environ.get("RPYC_PORT", "18812")' in main
    assert "port=rpyc_port" in main
    assert "port=18812" not in main


def test_rpyc_port_env_resolution():
    """Mirror of bridge __main__ bind logic (no MT5 import required)."""
    prev = os.environ.get("RPYC_PORT")
    try:
        os.environ.pop("RPYC_PORT", None)
        assert int(os.environ.get("RPYC_PORT", "18812")) == 18812
        os.environ["RPYC_PORT"] = "18813"
        assert int(os.environ.get("RPYC_PORT", "18812")) == 18813
    finally:
        if prev is None:
            os.environ.pop("RPYC_PORT", None)
        else:
            os.environ["RPYC_PORT"] = prev
