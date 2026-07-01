"""Quick AMP container health probe via RPyC."""
from __future__ import annotations

import sys
import time

import rpyc


def main() -> int:
    host = "127.0.0.1"
    port = 18814
    symbol = "MESU26"
    t0 = time.perf_counter()
    try:
        conn = rpyc.connect(host, port, config={"sync_request_timeout": 15})
    except Exception as exc:
        print(f"FAIL connect {host}:{port} -> {exc}")
        return 1

    try:
        root = conn.root
        ai = root.account_info()
        ti = root.terminal_info()
        tick = root.symbol_info_tick(symbol)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        def _as_dict(obj):
            if obj is None:
                return None
            if isinstance(obj, dict):
                return obj
            return {k: getattr(obj, k) for k in dir(obj) if not k.startswith("_") and not callable(getattr(obj, k, None))}

        ai_d = _as_dict(ai) or {}
        ti_d = _as_dict(ti) or {}
        tick_d = _as_dict(tick) or {}

        print(f"OK RPyC {host}:{port} in {elapsed_ms:.0f}ms")
        print(f"  login={ai_d.get('login')} server={ai_d.get('server')} margin_mode={ai_d.get('margin_mode')}")
        print(f"  terminal_connected={ti_d.get('connected')} trade_allowed={ti_d.get('trade_allowed')}")
        bid = float(tick_d.get("bid", 0) or 0)
        ask = float(tick_d.get("ask", 0) or 0)
        print(f"  {symbol} bid={bid} ask={ask}")
        if bid <= 0 and ask <= 0:
            print("WARN: no live quote — market closed or terminal stuck")
            return 2
        return 0
    except Exception as exc:
        print(f"FAIL RPyC call -> {exc}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
