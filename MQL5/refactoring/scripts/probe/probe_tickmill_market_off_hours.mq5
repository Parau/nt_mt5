//+------------------------------------------------------------------+
//| probe_tickmill_market_off_hours.mq5                              |
//| Tickmill — safe outside trade session (SymbolInfo*, no orders).  |
//| USTEC: Mon–Fri US cash hours. BTCUSD: ~24/7 (ticks may still flow).|
//+------------------------------------------------------------------+
#property script_show_inputs
#property strict

#include "ProbeBroker.mqh"

input string InpSymbols    = "USTEC,BTCUSD";  // comma-separated
input bool   InpWriteFile  = true;
input int    InpTickSample = 20;              // 0 = skip CopyTicks

void OnStart()
  {
   RunMarketOffHoursProbe(
      "Tickmill",
      InpSymbols,
      InpWriteFile,
      InpTickSample,
      false,
      "USTEC",
      "probe_tickmill_off"
   );
  }
//+------------------------------------------------------------------+
