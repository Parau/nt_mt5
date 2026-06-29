//+------------------------------------------------------------------+
//| wdon26_probe_market_live.mq5                                     |
//| XP WDON26 — run during B3 session (09:00–18:00 BRT typical).     |
//+------------------------------------------------------------------+
#property script_show_inputs
#property strict

#include "../ProbeBroker.mqh"

input bool   InpWriteFile  = true;
input int    InpTickSample = 20;
input bool   InpSkipClosed = true;

void OnStart()
  {
   RunMarketLiveProbe("XP/WDON26", "WDON26", InpWriteFile, InpTickSample,
                      true, "WDON26", "probe_xp_wdon26_live", InpSkipClosed);
  }
//+------------------------------------------------------------------+
