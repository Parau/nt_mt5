//+------------------------------------------------------------------+
//| wdon26_probe_market_off_hours.mq5                                |
//| XP WDON26 — off-hours SymbolInfo (update name on rollover).      |
//+------------------------------------------------------------------+
#property script_show_inputs
#property strict

#include "../ProbeBroker.mqh"

input bool   InpWriteFile  = true;
input int    InpTickSample = 20;

void OnStart()
  {
   RunMarketOffHoursProbe("XP/WDON26", "WDON26", InpWriteFile, InpTickSample,
                          true, "WDON26", "probe_xp_wdon26_off");
  }
//+------------------------------------------------------------------+
