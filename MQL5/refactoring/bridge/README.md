# Bridge staging (`MQL5/refactoring/bridge`)

**Fase 1:** produção em `E:\dev\TradingUltimate\mt5_bridge.py` (fora do repo).

| Versão | Ficheiro | Alteração |
|--------|----------|-----------|
| **v0.8** | `mt5_bridge_v008.py` + `history_args.py` | Normaliza `datetime` → Unix em `history_*` e `copy_ticks_*`; log + retry positional em `history_deals_get(ticket=…)` |
| v0.7 | `mt5_bridge_v007.py` | `exposed_orders_get` → MT5 `orders_get` (E07, reconciliação de pendentes) |
| v0.6 | (produção anterior) | baseline homologação wave 1–3 |

Deploy v0.8: copiar **`mt5_bridge_v008.py`** e **`history_args.py`** para o mesmo diretório de produção (ex. `E:\dev\TradingUltimate\`), renomear o bridge para `mt5_bridge.py` (ou ajustar import se mantiver o nome v008), e **reiniciar** o processo RPyC.

| Lado | Variável | Default | Notas |
|------|----------|---------|-------|
| Bridge (servidor) | `RPYC_PORT` | `18812` | Bind TCP do RPyC |
| Adaptador / homolog (cliente) | `MT5_PORT` | `18812` | Mesma porta exposta no host |
| Docker XP | `RPYC_PORT=18813` | — | Compose define; homolog XP usa `MT5_PORT=18813` |

Sync para `MT5-Docker`: `./scripts/sync_vendor_from_nt_mt5.sh` copia `mt5_bridge.py` + `history_args.py` para `vendor/bridge/` (seguro após v0.8+ com `RPYC_PORT`).

**Nota:** `history_deals_get(ticket=…)` continua a falhar em alguns brokers (Tickmill-Demo → `Invalid params`); o adaptador usa intervalo Unix + `group`. A bridge regista o erro e tenta overload positional.
