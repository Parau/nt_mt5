//+------------------------------------------------------------------+
//| probe_xp_market_off_hours.mq5                                    |
//| XP / B3 — SymbolInfo* and sessions (no OrderSend).               |
//| Verify exact symbol names in Market Watch (rollover contracts).  |
//+------------------------------------------------------------------+
#property script_show_inputs
#property strict

#include "ProbeBroker.mqh"

input string InpSymbols    = "WIN$,WDO$,WINQ26,WDON26,PETR4,DI1F27";
input bool   InpWriteFile  = true;
input int    InpTickSample = 20;

void OnStart()
  {
   RunMarketOffHoursProbe(
      "XP/B3",
      InpSymbols,
      InpWriteFile,
      InpTickSample,
      true,
      "WIN$",
      "probe_xp_off"
   );
  }
//+------------------------------------------------------------------+
