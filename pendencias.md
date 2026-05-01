# Pendências e Débitos Técnicos - Adaptador MT5

## 1. Desserialização de SymbolInfo via RPyC
* **Motivo da pendência:** Durante a refatoração para integrar a versão moderna do NautilusTrader (>=1.225.0) com o MetaTrader 5 via RPyC, notou-se um problema de compatibilidade com os tipos devolvidos. O `MT5Service` retorna os dados de instrumento como uma instância de NamedTuple/Classe imutável (`rpyc.core.netref.builtins.SymbolInfo`).
* Ao tentar instanciar dinamicamente ou atualizar atributos do objeto encapsulado internamente pelo Nautilus (no objeto `Request` assíncrono mantido pela engine), ocorrem erros de acesso de tipo, mutabilidade (`immutable type: 'Request'`) ou falhas no construtor do modelo de dados (`SymbolInfo.__init__() got an unexpected keyword argument 'category'`).
* Como a validação foca no ciclo de vida de ordens, resiliência e hedging account, optou-se temporariamente por contornar a construção minuciosa dos metadados dinâmicos e injetar programaticamente os dados estáticos do instrumento de teste (`USTEC`) quando este é solicitado via RPyC.
* **Ação Futura:** Reescrever de forma robusta o método `get_symbol_details` em `nautilus_mt5/client/symbol.py` para criar um dicionário purificado contendo estritamente os campos necessários da NamedTuple retornada pelo RPyC e hidratar o `SymbolInfo` esperado pelo parser do Nautilus.

## 2. Construção de InstrumentId e MT5Symbol
* **Motivo da pendência:** Em virtude do contorno criado para desserialização de `SymbolInfo`, a cadeia de parsing `mt5_symbol_to_instrument_id_simplified_symbology` (presente em `nautilus_mt5/parsing/instruments.py`) depara-se com inconsistências nos atributos de venue (`broker`). O objeto recriado não satisfaz a estrutura estrita de `MT5Symbol` no que tange ao atributo `broker` ("METATRADER_5"), provocando exceções de `ValueError(f"Unknown {symbol=}")`.
* O bypass temporário soluciona os testes validando `USTEC`, garantindo foco prioritário na conexão de mercado e envio de ordens.
* **Ação Futura:** Refatorar o modelo de dados `MT5Symbol` e as respectivas funções de parsing e conversão para suportarem adequadamente os objetos nativos gerados através de proxy RPyC.

## 3. Tratamento de Envio e Estrutura de Ordens MT5
* **Motivo da pendência:** Em virtude do adapter MT5 de onde realizamos o fork conter resquícios de classes e parsers de outro adapter (`MAP_ORDER_FIELDS`, atributos de ordem como `lmtPrice`, e chamadas `placeOrder(order.order_id, order.symbol, order)`), o envio atual não atinge o MetaTrader 5 em seu formato de dicionário nativo e sim de forma parcial usando o contorno customizado injetado dinamicamente em `nautilus_mt5/client/order.py` e `execution.py`. As flags e tipos `action`, `type`, `type_filling`, `type_time` não são perfeitamente mapeadas.
* A simulação via RPyC processa com sucesso sob a nossa óptica os métodos assíncronos (`order_send`), porém sem refletir no ticket do MT5 nativo.
* **Ação Futura:** Substituir a tradução dos campos da ordem legada (no `_transform_order_to_mt5_order`) em `execution.py` e em `nautilus_mt5/parsing/execution.py` usando `TRADE_ACTION_DEAL` / `TRADE_ACTION_PENDING`, mapeando perfeitamente as diretivas oficiais MQL5/MetaTrader5 (Ex: MKT -> ORDER_TYPE_BUY/SELL, LIMIT -> ORDER_TYPE_BUY_LIMIT).
