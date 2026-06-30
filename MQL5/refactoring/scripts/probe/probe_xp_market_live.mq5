//+------------------------------------------------------------------+
//| probe_xp_market_live.mq5                                         |
//| XP / B3 — run during B3 session. OrderCheck filling probes.      |
//| Does NOT call OrderSend.                                         |
//+------------------------------------------------------------------+
#property script_show_inputs
#property strict

#include "ProbeBroker.mqh"

input string InpSymbols    = "WIN$,WDO$,WINQ26,WDON26,PETR4,DI1F27";
input bool   InpWriteFile  = true;
input int    InpTickSample = 20;
input bool   InpSkipClosed = true;

void OnStart()
  {
   RunMarketLiveProbe(
      "XP/B3",
      InpSymbols,
      InpWriteFile,
      InpTickSample,
      true,
      "WIN$",
      "probe_xp_live",
      InpSkipClosed
   );
  }
//+------------------------------------------------------------------+
