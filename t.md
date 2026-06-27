## MQL5 Services
void OnStart()
{
   while(!IsStopped())
   {
      ler_comandos_do_websocket();
      buscar_ticks_novos_no_terminal();
      enviar_ticks_novos_para_o_nautilus();
      Sleep(10);
   }
}
## Websockets
MetaQuotes / MQL5Book WebSocket
MQL5/Include/MQL5Book/ws/
    wsclient.mqh
    wsframe.mqh
    wsinterfaces.mqh
    wsmessage.mqh
    wsprotocol.mqh
    wstools.mqh
    wstransport.mqh

https://github.com/tarasyyyk/mql5-websocket
tarasyyyk/mql5-websocket

## Trades
#include <Trade/Trade.mqh>
#include <Trade/PositionInfo.mqh>
#include <Trade/OrderInfo.mqh>
#include <Trade/HistoryOrderInfo.mqh>
#include <Trade/DealInfo.mqh>
#include <Trade/AccountInfo.mqh>
#include <Trade/SymbolInfo.mqh>

Acima do CTrade original
MQL_Easy	Boa inspiração de API
EA31337-classes	Boa referência de arquitetura/edge cases, mas pesado