# Bridge staging (`MQL5/refactoring/bridge`)

**Fase 1:** produção em `E:\dev\TradingUltimate\mt5_bridge.py` (fora do repo).

| Versão | Ficheiro | Alteração |
|--------|----------|-----------|
| **v0.7** | `mt5_bridge_v007.py` | `exposed_orders_get` → MT5 `orders_get` (E07, reconciliação de pendentes) |
| v0.6 | (produção anterior) | baseline homologação wave 1–3 |

Deploy v0.7: copiar para `mt5_bridge.py` e **reiniciar** o processo RPyC na porta 18812.
