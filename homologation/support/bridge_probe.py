"""Bridge helpers for homologation exec/data probes."""
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


def feed_bar_stream_ready(feed_enabled: bool) -> tuple[bool, str]:
    """Return whether live bars use the MQL5 WS feed path (Phase 2)."""
    if feed_enabled:
        return True, "ws_feed subscribe_bars"
    return False, "Set MT5_FEED_ENABLED=1 for WS bar streaming"


def rpyc_positions_count(host: str, port: int, symbol: str) -> int:
    return len(rpyc_positions_snapshot(host, port, symbol))


def rpyc_positions_snapshot(host: str, port: int, symbol: str) -> list[dict]:
    """Open positions for ``symbol`` as plain dicts (ticket, volume, type)."""
    conn = rpyc.connect(host, port, config={"allow_all_attrs": True})
    try:
        if not hasattr(conn.root, "exposed_positions_get"):
            return []
        raw = conn.root.exposed_positions_get(symbol=symbol)
        if raw is None:
            return []
        out: list[dict] = []
        for pos in list(raw):
            if isinstance(pos, dict):
                ticket = pos.get("ticket")
                volume = float(pos.get("volume", 0.0) or 0.0)
                pos_type = int(pos.get("type", 0) or 0)
            else:
                ticket = getattr(pos, "ticket", None)
                volume = float(getattr(pos, "volume", 0.0) or 0.0)
                pos_type = int(getattr(pos, "type", 0) or 0)
            if ticket is None or volume <= 0:
                continue
            out.append({"ticket": int(ticket), "volume": volume, "type": pos_type})
        return out
    finally:
        conn.close()


def rpyc_positions_volume_summary(host: str, port: int, symbol: str) -> tuple[int, float, float]:
    """Return (count, long_volume, short_volume) for ``symbol``."""
    snap = rpyc_positions_snapshot(host, port, symbol)
    long_vol = sum(p["volume"] for p in snap if p["type"] == 0)
    short_vol = sum(p["volume"] for p in snap if p["type"] == 1)
    return len(snap), long_vol, short_vol


def _normalize_order_row(order) -> dict:
    if isinstance(order, dict):
        ticket = order.get("ticket")
        volume = float(order.get("volume_current") or order.get("volume") or 0.0)
        price_open = float(order.get("price_open") or order.get("price") or 0.0)
    else:
        ticket = getattr(order, "ticket", None)
        volume = float(getattr(order, "volume_current", None) or getattr(order, "volume", 0) or 0.0)
        price_open = float(getattr(order, "price_open", None) or getattr(order, "price", 0) or 0.0)
    return {
        "ticket": int(ticket) if ticket is not None else None,
        "volume": volume,
        "price_open": price_open,
    }


def rpyc_pending_orders(host: str, port: int, symbol: str) -> list | None:
    """Return open pending orders, or None when the bridge exposes no orders API."""
    conn = rpyc.connect(host, port, config={"allow_all_attrs": True})
    try:
        root = conn.root
        if hasattr(root, "exposed_orders_get"):
            orders = root.exposed_orders_get(symbol=symbol)
            if orders is None:
                return []
            return [_normalize_order_row(order) for order in list(orders)]
        mt5 = MetaTrader5(host=host, port=port)
        try:
            orders = mt5.orders_get(symbol=symbol)
        except RuntimeError:
            return None
        finally:
            mt5.disconnect()
        if orders is None:
            return []
        return [_normalize_order_row(order) for order in list(orders)]
    finally:
        conn.close()


def rpyc_order_volume(order) -> float:
    if isinstance(order, dict):
        return float(order.get("volume_current") or order.get("volume") or 0.0)
    return float(getattr(order, "volume_current", None) or getattr(order, "volume", 0) or 0.0)


def rpyc_order_ticket(order) -> int | None:
    if isinstance(order, dict):
        ticket = order.get("ticket")
    else:
        ticket = getattr(order, "ticket", None)
    return int(ticket) if ticket is not None else None


def rpyc_cancel_all_pending(host: str, port: int, symbol: str) -> int:
    """Cancel all open pending orders for ``symbol``; return count cancelled."""
    pending = rpyc_pending_orders(host, port, symbol)
    if not pending:
        return 0
    cancelled = 0
    for order in pending:
        ticket = rpyc_order_ticket(order)
        if ticket is None:
            continue
        rpyc_cancel_order(host, port, ticket)
        cancelled += 1
    return cancelled


def rpyc_cancel_order(host: str, port: int, ticket: int) -> dict | object | None:
    """Cancel via the MetaTrader5 RPyC wrapper (not raw exposed_order_send)."""
    mt5 = MetaTrader5(host=host, port=port)
    return mt5.order_send({"action": 8, "order": int(ticket)})
