"""Symbol-aware order quantity and price helpers for live homologation."""
from __future__ import annotations

import os

import rpyc
from nautilus_trader.model.objects import Quantity

from homologation.config import HomologationConfig


def _symbol_fields(host: str, port: int, symbol: str) -> dict[str, float]:
    conn = rpyc.connect(host, port)
    try:
        info = conn.root.symbol_info(symbol)
        if info is None:
            raise RuntimeError(f"symbol_info({symbol}) returned None")
        if isinstance(info, dict):
            return {
                "volume_min": float(info.get("volume_min") or 0.01),
                "volume_step": float(info.get("volume_step") or 0.01),
                "trade_tick_size": float(info.get("trade_tick_size") or info.get("point") or 0.01),
                "digits": int(info.get("digits") or 2),
            }
        return {
            "volume_min": float(getattr(info, "volume_min", 0.01) or 0.01),
            "volume_step": float(getattr(info, "volume_step", 0.01) or 0.01),
            "trade_tick_size": float(
                getattr(info, "trade_tick_size", None)
                or getattr(info, "point", 0.01)
                or 0.01
            ),
            "digits": int(getattr(info, "digits", 2) or 2),
        }
    finally:
        conn.close()


def _fmt_qty(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return f"{value:g}"


def homolog_order_qty_str(cfg: HomologationConfig) -> str:
    override = os.environ.get("HOMOLOG_ORDER_QTY", "").strip()
    if override:
        return override
    fields = _symbol_fields(cfg.host, cfg.port, cfg.symbol)
    return _fmt_qty(fields["volume_min"])


def homolog_order_qty(cfg: HomologationConfig) -> Quantity:
    return Quantity.from_str(homolog_order_qty_str(cfg))


def homolog_order_qty_modify_str(cfg: HomologationConfig) -> str:
    fields = _symbol_fields(cfg.host, cfg.port, cfg.symbol)
    return _fmt_qty(fields["volume_min"] + fields["volume_step"])


def homolog_invalid_volume_str(cfg: HomologationConfig) -> str:
    fields = _symbol_fields(cfg.host, cfg.port, cfg.symbol)
    step = fields["volume_step"]
    vmin = fields["volume_min"]
    if vmin > step:
        return _fmt_qty(vmin - step)
    if step < 1.0:
        return _fmt_qty(step / 10.0)
    return "0.001"


def homolog_price_tick(cfg: HomologationConfig) -> float:
    return _symbol_fields(cfg.host, cfg.port, cfg.symbol)["trade_tick_size"]


def align_to_tick(price: float, tick: float) -> float:
    if tick <= 0.0:
        return round(price, 2)
    return round(round(price / tick) * tick, 10)


def passive_limit_price(bid: float, tick: float, *, factor: float = 0.95) -> float:
    return align_to_tick(bid * factor, tick)


def away_buy_stop(ask: float, tick: float, *, factor: float = 1.02) -> float:
    return align_to_tick(ask * factor, tick)


def away_sell_stop(bid: float, tick: float, *, factor: float = 0.98) -> float:
    return align_to_tick(bid * factor, tick)


def format_price(price: float, tick: float) -> str:
    aligned = align_to_tick(price, tick)
    decimals = max(0, min(8, len(_fmt_qty(tick).split(".")[-1]) if "." in _fmt_qty(tick) else 0))
    return f"{aligned:.{decimals}f}"
