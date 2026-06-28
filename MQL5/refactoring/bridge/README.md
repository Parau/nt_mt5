# Bridge staging (`MQL5/refactoring/bridge`)

**Fase 1:** produção em `E:\dev\TradingUltimate\mt5_bridge.py` (fora do repo).

| Versão | Ficheiro | Alteração |
|--------|----------|-----------|
| **v0.8** | `mt5_bridge_v008.py` + `history_args.py` | Normaliza `datetime` → Unix em `history_*` e `copy_ticks_*`; log + retry positional em `history_deals_get(ticket=…)` |
| v0.7 | `mt5_bridge_v007.py` | `exposed_orders_get` → MT5 `orders_get` (E07, reconciliação de pendentes) |
| v0.6 | (produção anterior) | baseline homologação wave 1–3 |

Deploy v0.8: copiar **`mt5_bridge_v008.py`** e **`history_args.py`** para o mesmo diretório de produção (ex. `E:\dev\TradingUltimate\`), renomear o bridge para `mt5_bridge.py` (ou ajustar import se mantiver o nome v008), e **reiniciar** o processo RPyC na porta 18812.

**Nota:** `history_deals_get(ticket=…)` continua a falhar em alguns brokers (Tickmill-Demo → `Invalid params`); o adaptador usa intervalo Unix + `group`. A bridge regista o erro e tenta overload positional.
