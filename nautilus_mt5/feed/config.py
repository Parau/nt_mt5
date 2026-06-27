from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeedGatewayConfig:
    """
    Inbound WebSocket feed gateway (MQL5 Service → adapter).

    Spec: res/especificacao_novo_adaptador_nautilus_mt5.md §12.1
    """

    enabled: bool = False
    host: str = "0.0.0.0"
    port: int = 8765
    path: str = "/mt5-feed"
    hello_timeout_secs: float = 30.0
    reconnect_notify: bool = True
