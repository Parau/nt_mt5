"""Quick probe: XP Docker bridge (port 18813)."""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import rpyc


def main() -> None:
    host = os.environ.get("MT5_HOST", "127.0.0.1")
    port = int(os.environ.get("MT5_PORT", "18813"))
    symbol = os.environ.get("MT5_SYMBOL", "WDON26")

    conn = rpyc.connect(host, port)
    try:
        info = conn.root.account_info()
        if isinstance(info, dict):
            login, server = info.get("login"), info.get("server")
        else:
            login, server = info.login, info.server
        print(f"login={login} server={server}")

        tick = conn.root.symbol_info_tick(symbol)
        if tick is None:
            print(f"{symbol}: no tick")
        elif isinstance(tick, dict):
            print(f"{symbol}: bid={tick.get('bid')} ask={tick.get('ask')} last={tick.get('last')}")
        else:
            print(f"{symbol}: bid={tick.bid} ask={tick.ask} last={getattr(tick, 'last', None)}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
