# MQL5 refactoring — staging area

Código gerado pelo agente para **deploy manual** no terminal MT5 e na bridge RPyC.

Spec: `res/especificacao_novo_adaptador_nautilus_mt5.md`

---

## Estrutura

| Pasta | Conteúdo |
|-------|----------|
| `Services/` | MQL5 Services (`#property service`) |
| `Include/` | Includes partilhados (`NT5FeedWire.mqh`, `WebSocket/`) |
| `tools/` | Utilitários Python (teste WS no host) |
| `bridge/` | Versões futuras de `mt5_bridge.py` (vazio na Fase 1) |

---

## Revisão MQL5 (v1.02)

| Problema | Correcção |
|----------|-----------|
| Loop hello ↔ subscribe (test server + Service) | Test server **não** reenvia `subscribe`; Service só `hello` se subscrição **mudou** |
| v1.01 | Ver histórico abaixo |

### v1.01

| Problema | Correcção |
|----------|-----------|
| `new`/`delete` a cada reconnect | Uma instância `g_ws`; reconnect = `close()` + `open()` |
| Ticks no mesmo `time_msc` perdidos | `last_sent` + filtro antes de enviar |
| `InpBatchSize=1000` → JSON enorme | Default **100** |

### Config MT5 (erro 4014)

Se `WS open failed ... err=4014`:

1. **Tools → Options → Expert Advisors**
   - Allow algorithmic trading = ligado
   - Allow WebRequest for listed URL = ligado
   - Adicionar **`http://127.0.0.1:8765`** (MT5 nativo Windows; sockets usam a mesma lista)
2. Reiniciar o Service após guardar opções.

---

### Ficheiros novos

- `Services/NT5TickFeedService.mq5`
- `Include/NT5FeedWire.mqh`
- `Include/WebSocket/*.mqh` — [tarasyyyk/mql5-websocket](https://github.com/tarasyyyk/mql5-websocket) (MQL5Book, pure MQL5)

---

## STOP — acção tua (deploy MT5)

1. **Copiar includes** do repo para a pasta de dados do MT5 (ou correr o script):

   ```cmd
   MQL5\refactoring\sync_to_mt5_data.bat
   ```

   Destino default: `C:\Users\Parau\AppData\Roaming\MetaQuotes\Terminal\FB9A56D617EDDDFE29EE54EBEFFE96C1\MQL5\`. Para outro terminal: `set MT5_DATA=...` antes de correr o `.bat`.

   Manualmente:
   - `MQL5/refactoring/Include/WebSocket/` → `<MT5_DATA>/MQL5/Include/WebSocket/`
   - `MQL5/refactoring/Include/NT5FeedWire.mqh` → `<MT5_DATA>/MQL5/Include/`

2. **Copiar Service** (incluído no `.bat` acima, ou manualmente):
   - `MQL5/refactoring/Services/NT5TickFeedService.mq5` → `<MT5_DATA>/MQL5/Services/`

3. **Compilar** `NT5TickFeedService.mq5` no MetaEditor (F7). Corrigir erros se houver e avisar.

4. **Whitelist de rede** (obrigatório — inclui sockets MQL5, não só WebRequest):
   - MetaTrader → Tools → Options → Expert Advisors
   - Allow algorithmic trading + Allow WebRequest for listed URL
   - MT5 **Windows nativo:** `http://127.0.0.1:8765`
   - MT5 **Docker:** `http://host.docker.internal:8765` (ou IP do host)

5. **Subir servidor WS de teste no host** (antes do Service):

   ```cmd
   set MT5_HOST=127.0.0.1 && set MT5_PORT=18812 && E:\miniconda\envs\trading\python.exe MQL5\refactoring\tools\ws_feed_test_server.py --host 0.0.0.0 --port 8765 -v
   ```

   Requer `websockets` no env `trading`.

6. **Configurar inputs do Service** (Properties ao Add/Start):
   - `InpWsUrl` — **Windows nativo:** `ws://127.0.0.1:8765/mt5-feed` · **Docker:** `ws://host.docker.internal:8765/mt5-feed`
   - `InpSymbols` — ex. `BTCUSD`
   - `InpDebug` — `true` na primeira corrida

7. **Arrancar Service:** Navigator → Services → `NT5TickFeedService` → Add → Start.

8. **Verificar (Fase 1 OK):**
   - **Um** `HELLO` no test server (sem flood)
   - Linhas **`TICKS symbol=BTCUSD cursor=... count=N`**
   - Journal MT5: `[NT5Feed] sent N ticks for BTCUSD...`

9. **Bridge RPyC:** não alterar nesta fase. Manter a correr como hoje (`18812`).

---

## Quando voltar aqui

Responde com:

- `feito` — se compilou e vês `hello` + `ticks` no test server, ou
- logs/erros do MetaEditor ou do terminal (Experts/Journal).

Continuamos com homologação end-to-end (Service + DataClient com `feed.enabled=True`).

---

## Fase 3 — DataClient + QuoteTick (branch cursor01-fase2)

Activar no `MetaTrader5DataClientConfig`:

```python
feed=FeedGatewayConfig(
    enabled=True,
    host="0.0.0.0",
    port=8765,
    path="/mt5-feed",
    hello_timeout_secs=30.0,
)
```

Ordem: TradingNode sobe → DataClient `_connect` (RPyC + gateway WS) → Start Service MT5 → `hello` + `ticks` → `QuoteTick` no MessageBus.

**Nota:** com `feed.enabled=True`, live quotes **não** usam poll RPyC; histórico (`_request_*`) continua via RPyC.

## Fase 4 — desactivar poll RPyC live

Com `feed.enabled=True`:

- `MetaTrader5DataClient` usa só o gateway WS para quote ticks live.
- `MetaTrader5Client.subscribe_ticks(BidAsk)` é ignorado (`live_quote_feed_enabled`).
- O loop `symbol_info_tick` no client **não** corre para subscrições BidAsk.
- RPyC continua activo para exec, instrumentos, barras e `_request_*` on-demand.

### Smoke test Phase 3 (TradingNode + QuoteTick)

1. Bridge RPyC a correr (`18812`)
2. Start `NT5TickFeedService` no MT5 (`InpWsUrl=ws://127.0.0.1:8765/mt5-feed`, `InpSymbols=BTCUSD`)
3. Correr:

```cmd
MQL5\refactoring\tools\run_feed_smoke.bat
```

Ou manualmente:

```cmd
set MT5_HOST=127.0.0.1 && set MT5_PORT=18812 && set MT5_FEED_ENABLED=1 && set MT5_SYMBOL=BTCUSD && set HOMOLOG_STREAM_SECS=30 && set HOMOLOG_STREAM_MIN_TICKS=3 && E:\miniconda\envs\trading\python.exe homologation\run_feed_smoke.py
```

Sucesso: `TC-HOM-D02` PASS com ticks via `QuoteTick` (logs `Stream tick #N: bid=... ask=...`).

## Fase 5 — homologação + capability matrix

- **TC-HOM-D02** valida stream real via WS feed (`MT5_FEED_ENABLED=1` + Service MT5).
- Sem feed activo, D02 faz **SKIP** no harness completo (`run_homologation.py`).
- Smoke dedicado: `MQL5\refactoring\tools\run_feed_smoke.bat`
- Matriz actualizada: `docs/data_capability_matrix.md` (Quote ticks, live WS path).
- Decisão arquitectural: `docs/decisions.md` §17.

Harness completo com feed:

```cmd
set MT5_FEED_ENABLED=1
set MT5_SYMBOL=BTCUSD
E:\miniconda\envs\trading\python.exe homologation\run_homologation.py
```

---

## Notas técnicas

- **Cursor:** `CopyTicks(..., last_msc + 1, ...)`. Primeiro batch usa `SymbolInfoTick` para seed.
- **Compressão WS:** desactivada (`useCompression=false`) para compatibilidade com test server simples.
- **Subscribe:** o adaptador envia `subscribe` quando o DataClient subscrever; o test server **só regista**, não ecoa.
