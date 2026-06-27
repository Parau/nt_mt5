O pedido está **claro**. Assumo: deploy **Docker+Wine**, adaptador **Python-only** (sem fase Rust como BitMEX/Deribit), modo **`EXTERNAL_RPYC`**, e “evitar polling” = **sem poll de live ticks** (requests históricos/exec via RPyC on-demand continuam aceitáveis).

---

## 1. Claridade do pedido

| Elemento | Claro? |
|----------|--------|
| Comparar 3 arquitecturas (vossa, BitMEX, Deribit) | Sim |
| Pros/cons + limitações MQL5 Service + Docker/Wine | Sim |
| Melhor proposta: facilidade + robustez, sem poll live | Sim |
| Alinhar com práticas Nautilus | Sim |

Única ambiguidade residual (não bloqueia): se “sem polling” inclui **reconciliação periódica de ordens** que o Nautilus pode fazer no ExecClient — trato isso à parte no fim.

---

## 2. Três arquitecturas lado a lado

### Visão geral

| | **Vossa (Opção B)** | **BitMEX** | **Deribit** |
|--|---------------------|------------|-------------|
| **Papel do adaptador WS** | **Server** (inbound) | **Client** → exchange | **Client** → exchange |
| **Live data** | Push MQL5 Service → adapter | Push exchange → adapter | Idem |
| **Histórico / snapshots** | RPyC (`copy_rates`, `copy_ticks_range`) | HTTP REST | HTTP + WS RPC |
| **Exec** | RPyC | WS (+ HTTP auxiliar) | WS separado (data vs exec) |
| **Core transport** | Python + MQL5 Service | Rust/pyo3 + WS client | Rust/pyo3 + WS client |
| **Two-layer handler** | Proposto (`FeedGateway` + `FeedHandler`) | `BitmexWebSocketClient` + `BitmexWsFeedHandler` | `DeribitWebSocketClient` + `DeribitWsFeedHandler` |

BitMEX e Deribit são **simétricos**: venue = server, adaptador = client. MT5 **inverte** isto porque MQL5Book só permite WS **client**.

---

## 3. Pros e cons por arquitectura

### A) Vossa proposta (Service + CopyTicks + WS server no adaptador + bridge RPyC mínima)

**Prós**
- Única forma **sem EA/DLL** de obter tick-a-tick fiel (`CopyTicks` + cursor).
- Bridge no container **colada ao terminal** (Wine IPC) — correcto para Docker.
- Adaptador no Linux leva parse, dedup, `QuoteTick`, subs — alinhado com [`adapter_contract.md`](docs/adapter_contract.md) (traduzir na fronteira).
- Separação **data push (WS)** vs **exec/hist (RPyC)** espelha BitMEX (WS live + HTTP histórico), adaptado ao MT5.
- Bridge mínima = menos código Wine/Python a manter.

**Contras**
- WS **server inbound** não existe nos adaptadores Nautilus oficiais — não há clone; haveis de desenhar protocolo + lifecycle.
- **Uma ligação** MQL5 Service → adapter: reconexão e cursor `time_msc` têm de ser robustos nos dois lados.
- Rede container→host (`host.docker.internal`, whitelist URL MT5).
- Dois canais (WS + RPyC) = duas superfícies de falha (mas separação clara de responsabilidades).

---

### B) BitMEX ([`data.py`](https://github.com/nautechsystems/nautilus_trader/blob/develop/nautilus_trader/adapters/bitmex/data.py), [`websocket/handler.rs`](https://github.com/nautechsystems/nautilus_trader/blob/develop/crates/adapters/bitmex/src/websocket/handler.rs))

**Prós**
- **DataClient fino**: `_subscribe_*` delega; `_request_*` vai ao HTTP; `_handle_msg` único.
- **Connect ordenado**: instrumentos → cache → WS connect → `wait_until_active`.
- **HandlerCommand** + **SubscriptionState** + reconexão com replay de subs.
- Histórico **on-demand** (HTTP), zero poll de live quotes.
- Modelo canónico documentado em [adapters.md](https://github.com/nautechsystems/nautilus_trader/blob/develop/docs/developer_guide/adapters.md).

**Contras (para MT5)**
- WS **client** — direcção oposta; não copiável literalmente.
- Rust/pyo3 — esforço desproporcional para vós agora.
- BitMEX tem venue madura (acks de subscribe, heartbeat); o vosso protocolo Service↔adapter é **custom**.

**O que copiar:** estrutura de módulos e lifecycle, **não** a direcção do socket.

---

### C) Deribit (mesmo padrão BitMEX, [docs/integrations/deribit.md](https://github.com/nautechsystems/nautilus_trader/blob/develop/docs/integrations/deribit.md))

**Prós**
- **Dois WS** (data vs exec) — inspira separar **feed WS** de **exec RPyC** no MT5.
- JSON-RPC, auth, retry, `SubscriptionState` — referência de robustez em streaming.
- Handler com `cmd_rx` / `out_tx` — mesmo padrão two-layer.

**Contras (para MT5)**
- Idem BitMEX: client outbound, Rust, venue com API rica.
- Exec via WS na Deribit; vós **devem** manter exec RPyC (bridge MT5-native).

**O que copiar:** separação data/exec e padrão handler; exec continua RPyC, não WS.

---

### D) Estado actual `nt_mt5` (poll RPyC ~1 Hz)

**Prós:** já implementado; homologação Tier 1 com fake bridge.

**Contras:** não cumpre objectivo de streaming; viola espírito “evitar polling” para live data; perde ticks.

**Veredicto:** descartar para live; manter RPyC só exec + histórico.

---

## 4. Restrições que moldam a decisão

| Restrição | Implicação |
|-----------|------------|
| **MQL5 Service** | Só WS **client**; loop `OnStart`; whitelist URL; sem API programática start/stop |
| **CopyTicks** | Cursor `time_msc+1`; batches; dedup no adapter; símbolos no Market Watch |
| **Docker + Wine** | `MT5Service` RPyC **dentro** do container; adapter Linux acede portas expostas |
| **Nautilus layered model** | Low-level = bridge + feed wire; Python = DataClient/ExecClient/Provider |
| **Sem Rust (fase 1)** | Implementar two-layer em **Python asyncio** (`websockets`), não pyo3 |
| **Sem poll live** | Proibido `symbol_info_tick` em loop; OK `copy_rates`/`copy_ticks_range` sob **Request** |

---

## 5. Arquitectura recomendada (melhor equilíbrio facilidade × robustez)

Mantém **Opção B** como base, com **estrutura BitMEX/Deribit em Python** (sem Rust, direcção WS invertida).

```
┌─ Docker: MT5 + Wine ─────────────────────────────┐
│  MQL5 Service     CopyTicks → WS CLIENT          │
│  mt5_bridge.py    RPyC SERVER :18812             │
└──────────── WS push ────────────┬── RPyC RPC ────┘
                                  │
┌─ Linux: nautilus_mt5 ───────────┴────────────────┐
│  feed/                                           │
│    InboundFeedGateway   ← WS SERVER (asyncio)    │
│    InboundFeedHandler   ← parse, dedup, subs     │
│    messages.py          ← protocolo wire JSON    │
│  data.py                ← fino (estilo BitmexDataClient) │
│  client/                ← RPyC só exec + requests│
│  execution.py           ← inalterado na fronteira │
└──────────────────────────────────────────────────┘
```

### Módulos (espelho BitMEX, adaptado)

| Módulo | Responsabilidade | Inspiração |
|--------|------------------|------------|
| `feed/messages.py` | `Hello`, `Subscribe`, `TickBatch`, `Heartbeat`, `Error` | `BitmexWsMessage` / frames |
| `feed/handler.py` | Parse, dedup `time_msc`, `SubscriptionState`, reconexão MQL5 | `BitmexWsFeedHandler` |
| `feed/gateway.py` | `websockets.serve`, 1 conn Service, `cmd` → handler | outer WS client (inverso) |
| `data.py` | `_connect`/`_disconnect`, `_subscribe_*` → gateway, `_handle_msg` → MessageBus | `BitmexDataClient` |
| `client/` (RPyC) | exec + `_request_bars` / `_request_quote_ticks` | `BitmexHttpClient` |
| `factories.py` | DataClient cria feed; ExecClient só RPyC partilhado | BitMEX factories |

### Lifecycle `_connect` (ordem Nautilus)

1. `instrument_provider.initialize()` + `venue_profile`  
2. `feed_gateway.start(host, port)`  
3. Aguardar `Hello` do Service (timeout configurável)  
4. **Não** depender de RPyC para ticks  
5. RPyC connect pode ser lazy no ExecClient ou partilhado no factory  

### Protocolo wire (mínimo robusto, fácil de implementar)

**Service → adapter**

```json
{"op":"hello","session":"...","symbols":["BTCUSD"]}
{"op":"ticks","symbol":"BTCUSD","cursor":1730000000123,"data":[{"time_msc":...,"bid":...,"ask":...,"flags":...}]}
{"op":"heartbeat","ts_msc":...}
```

**Adapter → Service**

```json
{"op":"subscribe","symbols":["BTCUSD"]}
{"op":"unsubscribe","symbols":["EURUSD"]}
{"op":"ping"}
```

Evitar JSON-RPC pesado (Deribit) — desnecessário para 1 cliente MQL5.

### O que **não** fazer (facilidade falsa)

| Atalho | Porquê evitar |
|--------|----------------|
| WS server na bridge | Duplica lógica; bridge deixa de ser mínima |
| Poll RPyC mais rápido | Não resolve fidelidade |
| TCP custom sem handler | Menos subs/reconnect que WS + asyncio maduro |
| Lógica parse no `MetaTrader5Client` mixin | Viola layered model; BitMEX mantém DataClient fino |
| Rust na v1 | Aumenta muito esforço vs ganho imediato |

---

## 6. Comparação final (critérios pedidos)

| Critério | Vossa Opção B + estrutura BitMEX-like | Só BitMEX literal | Só Deribit literal | Poll RPyC actual |
|----------|--------------------------------------|-------------------|--------------------|------------------|
| **Facilidade impl.** | Média (protocolo custom, Python) | Baixa (Rust + venue errada) | Baixa | Alta |
| **Robustez live** | Alta (CopyTicks + handler) | N/A | N/A | Baixa |
| **Alinhamento Nautilus** | Alta | Alta (estrutura) | Alta (estrutura) | Média |
| **Docker+Wine** | Alta | N/A | N/A | Média |
| **Sem poll live** | Sim | Sim | Sim | Não |

---

## 7. Polling: o que fica permitido

| Mecanismo | Poll? | Veredicto |
|-----------|-------|-----------|
| Loop Service `CopyTicks` + push | Não (event-driven no terminal) | OK |
| WS push → adapter | Não | OK |
| `RequestBars` / `RequestQuoteTicks` via RPyC | On-demand | OK (Nautilus spec) |
| `symbol_info_tick` em loop 1 Hz | Sim | **Eliminar** |
| Reconciliação open orders (ExecClient) | Pode ser periódica | OK se for padrão Nautilus exec, não canal de ticks |

---

## 8. Conclusão

A **melhor arquitectura implementável** para o vosso contexto:

1. **Manter Opção B** (Service no container, bridge RPyC mínima, WS server no adaptador Linux).  
2. **Organizar `nautilus_mt5/feed/`** copiando o **padrão two-layer BitMEX/Deribit** em Python (gateway + handler + messages + `SubscriptionState`), com direcção WS **invertida**.  
3. **`MetaTrader5DataClient` fino** como `BitmexDataClient`: subscribe → gateway, `_handle_msg` → MessageBus.  
4. **RPyC só** exec + histórico on-demand — como BitMEX usa HTTP para requests.  
5. **Não** investir em Rust/pyo3 na primeira entrega; **não** pôr WS server na bridge.

Isto maximiza robustez de ticks (CopyTicks) e aderência Nautilus (camadas, lifecycle, subs) com esforço concentrado num protocolo JSON pequeno e ~4 módulos Python novos — em vez de clonar BitMEX/Deribit na íntegra, o que seria incompatível com MQL5 Service + Docker.

Se quiseres, no próximo passo posso detalhar a tabela **método-a-método** (`BitmexDataClient._connect` → `MetaTrader5DataClient._connect`, etc.) como checklist de implementação.