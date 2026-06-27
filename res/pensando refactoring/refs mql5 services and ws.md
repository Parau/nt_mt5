

# https://www.mql5.com/en/code
Não achei no [MQL5 Code Base](https://www.mql5.com/en/code) um exemplo **completo** igual ao vosso desenho (**Service + CopyTicks + cursor + WebSocket push para fora**). O que existe são **peças** que cobrem partes do problema.

### 1. **CopyTicks + cursor em loop** — melhor referência
**[Download all ticks of a symbol's history](https://www.mql5.com/en/code/56324)** (LoRio, 2025)

- Usa `CopyTicks(..., COPY_TICKS_ALL, cursorMSC, ...)` em batches
- Atualiza cursor com `time_msc` do último tick
- Padrão de **catch-up** exatamente como vocês querem

Limitação: é **EA** (precisa de chart), foco em **download histórico**, não export live via rede. A lógica de cursor é reutilizável num Service.

---

### 2. **Exportar ticks em tempo real para app externo**
**[Working with sockets in MQL5](https://www.mql5.com/en/code/169)** (avoitenko, 2010)

- Exporta ticks **em tempo real** do MT5 → servidor TCP externo
- Caso de uso mais parecido com “push para Nautilus/bridge”

Limitação: **EA + DLL** (`socket_mql5.dll`), TCP não WebSocket, provavelmente `OnTick`/`SymbolInfoTick`, não `CopyTicks` com cursor.

---

### 3. **Service como programa de background** — padrão estrutural
Services publicados no Code Base são **monitoramento/UI**, não tick streaming:

| Código | O que faz |
|--------|-----------|
| [Swap Monitor](https://www.mql5.com/en/code/53007) | Service, loop periódico, grava CSV |
| [ShowTradeLines Service](https://www.mql5.com/en/code/68713) | Service, monitora conta, `OnStart` + intervalo |
| [Symbol Summary](https://www.mql5.com/en/code/71686) | Service, UI em background |

Úteis como **modelo de `#property service` + loop + inputs**, não de ticks.

O autor do Swap Monitor até nota que o Code Base trata Services de forma limitada — publica como script/service híbrido.

---

### 4. **Ticks em tempo real sem rede (export local)**
| Código | Relevância |
|--------|------------|
| [Ask Bid Ticks](https://www.mql5.com/en/code/820) | Coleta tick-a-tick → CSV; comenta perda de ticks se handler lento |
| [Quotes Monitoring (memory-mapped file)](https://www.mql5.com/en/code/817) | EA → memória compartilhada (IPC local, sem WS) |
| [RenkoChart](https://www.mql5.com/en/code/21920) | EA usa **histórico de ticks** + custom symbol em tempo real |

---

### 5. **WebSocket no MQL5 Code Base**
Quase nada pronto. Só utilitários como [Sec-WebSocket-Key Generator](https://www.mql5.com/en/code/47982). WS completo costuma estar **fora** do Code Base (MQL5Book `ws/`, GitHub tipo tarasyyyk/mql5-websocket) — alinhado com o vosso `t.md`.

---

## Conclusão prática

| Peça do vosso design | Referência no Code Base |
|----------------------|-------------------------|
| Service background | [Swap Monitor](https://www.mql5.com/en/code/53007), [ShowTradeLines](https://www.mql5.com/en/code/68713) |
| **CopyTicks + cursor** | **[LoRio #56324](https://www.mql5.com/en/code/56324)** ← principal |
| Push para processo externo | [Sockets #169](https://www.mql5.com/en/code/169) (TCP+DLL) ou vosso `MT5Ext` (TCP nativo em `socket-library-mt4-mt5.mqh`) |
| WebSocket | **Não no Code Base** — MQL5Book / libs externas |

**Não há clone pronto.** O caminho natural é combinar:
- loop/cursor de **#56324**
- shell de **Service** de **#53007**
- transporte WS do **MQL5Book** (ou TCP do **MT5Ext**, que já têm no repo)

Artigo oficial complementar (direção oposta — feed **para dentro** do MT5): [MQL5 Cookbook — Services](https://www.mql5.com/en/articles/11826).

# Referencias no GitHub


Critério aplicado: **fora** tudo que depende de **EA no chart** ou **DLL externa** (`libzmq`, `libsodium`, `socket_mql5.dll`, etc.). Mantive só o que serve como **peça reutilizável** no vosso desenho (`Service + CopyTicks + cursor + WS pure MQL5`).

---

## Mantém (alinhado com o objetivo)

### Bibliotecas / transporte (pure MQL5, sem DLL)

| Ref | Porquê fica |
|-----|-------------|
| [tarasyyyk/mql5-websocket](https://github.com/tarasyyyk/mql5-websocket) | WS client em MQL5 puro; encaixa no Service com loop + `checkMessages()` |
| MQL5Book `ws/` ([doc oficial](https://www.mql5.com/en/book/advanced/project/project_websocket_mql5)) | Base da lib acima; mesma stack, sem DLL |
| [fxe — Socket library blog](https://www.mql5.com/en/blogs/post/706665) | **Só a lib** `socket-library-mt4-mt5.mqh`: Winsock via `.mqh`, sem DLL externa. Útil se quiserem TCP em vez de WS — mas teriam de adaptar para **Service**, não copiar o padrão EA |

### Lógica de ticks (não é stack pronta, mas reutilizável)

| Ref | Porquê fica |
|-----|-------------|
| [LoRio #56324](https://www.mql5.com/en/code/56324) | Melhor ref de **CopyTicks + cursor `time_msc`**. É EA, mas a **lógica de catch-up** copia-se para um Service |
| [MQL5 Book — ticks + CopyTicks catch-up](https://www.mql5.com/en/book/applications/timeseries/timeseries_ticks_mqltick) | Pseudocódigo oficial do padrão cursor |

### Shell de Service (Code Base, não GitHub)

| Ref | Porquê fica |
|-----|-------------|
| [Swap Monitor #53007](https://www.mql5.com/en/code/53007) | `#property service` + loop |
| [ShowTradeLines #68713](https://www.mql5.com/en/code/68713) | Idem |

---

## Fora (EA ou DLL externa) - não é o que queremos usar no projeto

### WebSocket / push

| Ref | Motivo |
|-----|--------|
| [polyclick/metatrader5-websocket-tickers](https://github.com/polyclick/metatrader5-websocket-tickers) | EA no chart |
| [mainpclab/metatrader5-websocket-tickers](https://github.com/mainpclab/metatrader5-websocket-tickers) | EA no chart |
| [mobjoy0/mt5-bridge](https://github.com/mobjoy0/mt5-bridge) | EA com HTTP+WS embutido |

### TCP / sockets

| Ref | Motivo |
|-----|--------|
| [JafferWilson/MT4-Ticks-To-MT5](https://github.com/JafferWilson/MT4-Ticks-To-MT5) | EA |
| [Seburath/Python-MT4](https://github.com/Seburath/Python-MT4) | EA socket server |
| [TheSnowGuru/PyTrader-...](https://github.com/TheSnowGuru/PyTrader-python-mt4-mt5-trading-api-connector-drag-n-drop) | EA (+ versão completa comercial) |
| `MT5Ext` (repo local) | EA + `OnTick` — útil como legado, **não** como modelo novo |

### ZeroMQ (todos com DLL)

| Ref | Motivo |
|-----|--------|
| [Gunther-Schulz/MQL5-JSON-API-2](https://github.com/Gunther-Schulz/MQL5-JSON-API-2) | EA + `libzmq.dll` / `libsodium.dll` |
| [luciotato/MQL5-JSON-API](https://github.com/luciotato/MQL5-JSON-API) | Idem |
| [darwinex/DarwinexLabs](https://github.com/darwinex/DarwinexLabs/tree/master/tools/dwx_zeromq_connector/v2.0.1) | EA + ZMQ DLLs |
| [EricSchles/bindings-mql4-5](https://github.com/EricSchles/bindings-mql4-5) | ZMQ + DLLs |
| [avoitenko #169](https://www.mql5.com/en/code/169) (Code Base) | EA + `socket_mql5.dll` |

---

## Fora por outro motivo (nem EA/DLL — camada errada)

Estes não usam EA/DLL no sentido MQL5, mas **não ajudam** no desenho Service+CopyTicks porque são poll Python/RPyC:

- [BigMitchGit/mt5_remote](https://github.com/BigMitchGit/mt5_remote)
- [ehsash/mt5linux](https://github.com/ehsash/mt5linux)
- [akivajp/mt5-bridge](https://github.com/akivajp/mt5-bridge)
- [ariadng/metatrader-mcp-server](https://github.com/ariadng/metatrader-mcp-server)

---

## Mapa filtrado (só o que vale a pena ler)

```
LoRio #56324          → lógica CopyTicks + cursor (copiar para Service)
Swap Monitor #53007   → shell #property service + loop
tarasyyyk/mql5-websocket (ou MQL5Book ws/) → transporte WS client
```

**Nota sobre polyclick:** descartado como **implementação** (EA), mas o padrão de **batch JSON + reconnect + intervalo curto** no loop do Service continua válido como ideia — não como repo a clonar.

---

## Lista curta final (prioridade de leitura)

1. [tarasyyyk/mql5-websocket](https://github.com/tarasyyyk/mql5-websocket)
2. [LoRio #56324](https://www.mql5.com/en/code/56324) — só algoritmo de cursor
3. [Swap Monitor #53007](https://www.mql5.com/en/code/53007) — shell Service
4. [MQL5 Book — WebSocket](https://www.mql5.com/en/book/advanced/project/project_websocket_mql5) — se quiserem a lib “canónica” em vez do fork

Conclusão: depois do filtro, **no GitHub só sobra mesmo a lib WS** (`tarasyyyk`). O resto do vosso stack vem do **Code Base** (LoRio + Services) + **MQL5Book**. Nada pronto com Service + CopyTicks + WS.

# Livro https://www.mql5.com/en/book
Sim — o [MQL5 Book](https://www.mql5.com/en/book) tem **exactamente as três peças** do vosso desenho, mas **não num exemplo único**. É documentação oficial, não um clone pronto.

---

## O que o livro cobre (e encaixa no vosso objetivo)

### 1. **Services** — Parte 5, “Creating application programs”

| Capítulo | Link | Conteúdo |
|----------|------|----------|
| [Services](https://www.mql5.com/en/book/applications/script_service/services) | `#property service`, `OnStart`, instância via Navigator → Add Service |
| [OnStart](https://www.mql5.com/en/book/applications/runtime/runtime_onstart) | Loop `for(; !IsStopped(); )` + `Sleep()` — padrão de background |
| [Program types](https://www.mql5.com/en/book/applications/runtime/runtime_features_by_progtype) | Service = `OnStart` + `#property service` (não EA) |

Exemplo do livro: monitorização de conta em loop — **shell do Service**, sem ticks.

---

### 2. **CopyTicks + cursor** — a ref mais importante

Capítulo: [Working with real tick arrays in MqlTick structures](https://www.mql5.com/en/book/applications/timeseries/timeseries_ticks_mqltick)

O livro explica explicitamente:

- **`OnTick` não garante todos os ticks** — vários ticks podem chegar, mas só um evento é gerado
- **Solução:** `CopyTicks` desde o último `time_msc` processado
- **Pseudocódigo oficial** com cursor `prev` e `prev + 1` para não reprocessar

Isto é a **justificação teórica** do vosso desenho — melhor que LoRio para entender o *porquê*.

Também documenta:
- `MqlTick`, `flags`, `COPY_TICKS_*`
- `CopyTicksRange` para intervalos
- Services/scripts podem **esperar até 45s** por sync de ticks (EA/script têm thread própria)

**Nota:** o pseudocódigo usa `OnTick`/primeiro tick via `SymbolInfoTick`; num Service adaptam para loop contínuo com `CopyTicks(symbol, ticks, COPY_TICKS_ALL, last_msc + 1, count)`.

---

### 3. **WebSocket client (pure MQL5, sem DLL)** — Parte 7

Projeto end-to-end em vários capítulos:

| Capítulo | Link |
|----------|------|
| [Plano do projeto](https://www.mql5.com/en/book/advanced/project/project_web_service_plan) | Trade copier via WS; **servidor WS externo** (Node.js) |
| [Fundamentos WebSocket](https://www.mql5.com/en/book/advanced/project/project_websockets) | RFC6455, handshake |
| [WebSocket protocol in MQL5](https://www.mql5.com/en/book/advanced/project/project_websocket_mql5) | Lib em `MQL5/Include/MQL5Book/ws/` |
| [Client echo/chat](https://www.mql5.com/en/book/advanced/project/project_websocket_client) | Exemplos de cliente |
| [Signal service client](https://www.mql5.com/en/book/advanced/project/project_trade_signal_client) | Cliente MQL5 + JSON |

A lib `ws/` inclui:
- `WebSocketClient` — `open()`, `send()`, `checkMessages()`, `onMessage()`
- Transporte via **sockets nativos MQL5** (`wstransport.mqh`) — **sem DLL externa**
- MQL5 é **só client**; o servidor WS fica fora (Node.js no livro → Python/bridge no vosso caso)

O projeto do livro é **copy-trade/sinais**, não tick streaming — mas o **transporte WS** é reutilizável tal como está.

---

## O que o livro **não** tem

| Gap | Detalhe |
|-----|---------|
| **Stack completa** | Não junta Service + CopyTicks + WS push de ticks |
| **Tick streaming** | WS no livro = trades/sinais/chat, não mercado |
| **Servidor WS em MQL5** | Impossível como server nativo; livro usa Node.js |
| **Exemplo pronto** | Só peças + projeto de trade copier |

---

## Mapa: livro → vosso desenho

```
MQL5 Book
├── Services (Part 5)           → #property service + OnStart + loop
├── CopyTicks (Part 5)          → cursor time_msc + catch-up (fundamento)
└── MQL5Book/ws/ (Part 7)       → WS client push para bridge Python
         ↓
    Service loop:
      CopyTicks(from=last_msc+1)
      → JSON
      → WebSocketClient.send()
      → checkMessages()  // comandos da bridge
```

---

## Prioridade de leitura no livro

1. [timeseries_ticks_mqltick](https://www.mql5.com/en/book/applications/timeseries/timeseries_ticks_mqltick) — **obrigatório** (algoritmo de cursor)
2. [services](https://www.mql5.com/en/book/applications/script_service/services) — shell Service
3. [project_websocket_mql5](https://www.mql5.com/en/book/advanced/project/project_websocket_mql5) — lib WS
4. [runtime_onstart](https://www.mql5.com/en/book/applications/runtime/runtime_onstart) — loop + `IsStopped()`

Opcional: [project_web_service_plan](https://www.mql5.com/en/book/advanced/project/project_web_service_plan) — arquitetura client/server e JSON.

---

## Conclusão

O livro é **mais completo que o GitHub** para o vosso objetivo (sem EA/DLL):

- **Service** → capítulo dedicado  
- **CopyTicks + cursor** → capítulo dedicado com pseudocódigo oficial  
- **WebSocket** → lib canónica `MQL5Book/ws/`  

Falta só **montar** as três peças — o livro não faz isso por vocês. Para implementação, a ordem natural é: Services → CopyTicks → integrar `ws/` no loop do Service.

O PDF/CHM está disponível na [página principal do livro](https://www.mql5.com/en/book) se quiserem consulta offline.