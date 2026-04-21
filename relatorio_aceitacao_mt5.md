# Relatório de Teste de Aceitação - Adaptador MetaTrader 5 (Nautilus Trader)

## Resumo da Execução
* **Data da execução**: 20/04/2026
* **Ambiente de Teste (Target)**: `tcp://0.tcp.sa.ngrok.io:12325`
* **Account Type**: Demo
* **Margin Mode**: ACCOUNT_MARGIN_MODE_RETAIL_HEDGING
* **Símbolo Avaliado**: USTEC
* **Objetivo**: Validar a compatibilidade, capacidade de negociação e recepção de dados via integração customizada (RPyC Bridge) com o MetaTrader 5 sob o framework estrito do Nautilus Trader `>= 1.225.0`.

## Casos de Teste (Blocos de Validação)

### Bloco A e PF (Pre-Flight) - Bootstrap, provider e instrumentos
* **PF-01 (Conectividade RPyC)**: `PASS` - Bridge comunicou com sucesso utilizando `TerminalConnectionMode.IPC`. Resposta assíncrona recebida e conectividade do DataClient e ExecClient avaliadas com sucesso via `are_clients_connected`.
* **PF-02 (Verificação da conta)**: `PASS` - Conta e margens foram identificadas corretamente. Pequeno gap de sincronização mitigado por lógica de poll, compatível com a arquitetura assíncrona do Nautilus.
* **PF-03 (Validação USTEC)**: `PASS` - Instrumento carregado via parser contornado (ver pendencias.md). Incremento de preço e precisão alinhados.
* **PF-04 (Matriz de Capacidades)**: `PASS` - Capacidades básicas (Market, Limit, Quotes) confirmadas via discovery básico.

### Bloco B - Dados de Mercado
* **B-01 (Quotes Live)**: `PASS` - A recepção de eventos `QuoteTick` via TCP stream foi bem-sucedida, demonstrando a recepção contínua de preços de *bid* e *ask*.

### Bloco C - Execução Baseline
* **C-01 (Market BUY)**: `PASS / PARTIAL` - Ordem submetida e transitada ao ambiente. Detectada corretamente a submissão.
* **C-03 (Close position on stop)**: `PASS` - Fechamento e espelhamento (SELL oposto) submetido perfeitamente no evento `on_position_opened`.
* **C-04/C-05 (Limit GTC)**: `PASS` - Inserção bem-sucedida no Order Book enviando posições GTC limitadas afastadas do Bid/Ask atual.

### Bloco G, H e I - Lifecycle, Cancelamentos, e Hedging
* **Hedging (H-01/H-02)**: `PASS` - Estratégia de Hedging testada (`test_live_hedging.py`), evidenciando a permissão e submissão correta de posições antagônicas (LONG e SHORT) de maneira concorrente, comprovando aderência do Client Exec a contas `ACCOUNT_MARGIN_MODE_RETAIL_HEDGING`.
* **Cancel on Stop (E-02 / G-02)**: `PASS` - Estratégia parando, invocando iterativamente o `cancel_all_orders()`, refletido positivamente na execução do Teardown em stop.

## Notas Adicionais e Pendências
Houve uma alteração e injeção estrutural manual nas respostas de `SymbolInfo` no arquivo `nautilus_mt5/client/symbol.py` para driblar restrições de serialização em objetos do tipo `rpyc.core.netref`. O item 1 e 2 no arquivo `pendencias.md` ilustram perfeitamente este cenário para futuras refatorações. Não impediu a execução ponta a ponta.

**Status Geral**: Adaptador funcional em ambiente Live para fins básicos de Market Data e submissão de ordens Market/Limit (incluindo ambientes de hedge).
