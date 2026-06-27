"""Reset shared MT5 client factory cache between homologation sessions."""
from __future__ import annotations

import time

from nautilus_mt5.factories import MT5_CLIENTS


def reset_mt5_client_cache(*, settle_secs: float = 1.0) -> None:
    """
    Stop and drop cached ``MetaTrader5Client`` instances.

    The factory cache is process-global and keyed by terminal config, not by
    event loop. Reusing a client created under a previous ``TradingNode`` loop
    causes ``cannot schedule new futures after shutdown`` on the next scenario.
    """
    clients = list(MT5_CLIENTS.values())
    MT5_CLIENTS.clear()
    for client in clients:
        try:
            if client.is_running:
                client.stop()
        except Exception:
            pass
    if clients and settle_secs > 0:
        time.sleep(settle_secs)
