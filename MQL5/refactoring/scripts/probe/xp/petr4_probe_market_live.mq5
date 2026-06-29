//+------------------------------------------------------------------+
//| petr4_probe_market_live.mq5                                      |
//| XP PETR4 — run during B3 cash session.                           |
//+------------------------------------------------------------------+
#property script_show_inputs
#property strict

#include "../ProbeBroker.mqh"

input bool   InpWriteFile  = true;
input int    InpTickSample = 20;
input bool   InpSkipClosed = true;

void OnStart()
  {
   RunMarketLiveProbe("XP/PETR4", "PETR4", InpWriteFile, InpTickSample,
                      true, "PETR4", "probe_xp_petr4_live", InpSkipClosed);
  }
//+------------------------------------------------------------------+
