//+------------------------------------------------------------------+
//| probe_amp_market_off_hours.mq5                                   |
//| AMP Global USA — safe outside trade session (SymbolInfo*, no orders).|
//| CME micro/mini futures: confirm exact symbol names in Market Watch.|
//+------------------------------------------------------------------+
#property script_show_inputs
#property strict

#include "ProbeBroker.mqh"

input string InpSymbols    = "EPU26,MESU26,ENQU26,MNQU26";
input bool   InpWriteFile  = true;
input int    InpTickSample = 20;

void OnStart()
  {
   RunMarketOffHoursProbe(
      "AMP",
      InpSymbols,
      InpWriteFile,
      InpTickSample,
      false,
      "EPU26",
      "probe_amp_off"
   );
  }
//+------------------------------------------------------------------+
