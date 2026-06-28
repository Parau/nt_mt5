"""Lightweight RPyC bridge capability probes for homologation."""
from __future__ import annotations

import rpyc

from nautilus_mt5.metatrader5.MetaTrader5 import MetaTrader5


def bridge_exposes(host: str, port: int, method: str) -> bool:
    conn = rpyc.connect(host, port, config={"allow_all_attrs": True})
    try:
        return hasattr(conn.root, method)
    finally:
        conn.close()


def bridge_bar_stream_ready(host: str, port: int) -> tuple[bool, str]:
    """Return whether live bar subscribe/unsubscribe can reach the bridge."""
    required = (
        "exposed_req_real_time_bars",
        "exposed_cancel_real_time_bars",
        "exposed_cancel_historical_data",
    )
    missing = [name for name in required if not bridge_exposes(host, port, name)]
    if missing:
        return False, f"bridge missing: {', '.join(missing)}"
    return True, "ok"


def rpyc_positions_count(host: str, port: int, symbol: str) -> int:
    conn = rpyc.connect(host, port, config={"allow_all_attrs": True})
    try:
        positions = conn.root.exposed_positions_get(symbol=symbol)
        if positions is None:
            return 0
        return len(positions)
    finally:
        conn.close()


def rpyc_cancel_order(host: str, port: int, ticket: int) -> dict | object | None:
    """Cancel via the MetaTrader5 RPyC wrapper (not raw exposed_order_send)."""
    mt5 = MetaTrader5(host=host, port=port)
    return mt5.order_send({"action": 8, "order": int(ticket)})
