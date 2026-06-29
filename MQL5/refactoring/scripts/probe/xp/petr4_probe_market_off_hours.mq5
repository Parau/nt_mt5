//+------------------------------------------------------------------+
//| petr4_probe_market_off_hours.mq5                                 |
//| XP PETR4 — off-hours SymbolInfo (B3 equity).                     |
//+------------------------------------------------------------------+
#property script_show_inputs
#property strict

#include "../ProbeBroker.mqh"

input bool   InpWriteFile  = true;
input int    InpTickSample = 20;

void OnStart()
  {
   RunMarketOffHoursProbe("XP/PETR4", "PETR4", InpWriteFile, InpTickSample,
                          true, "PETR4", "probe_xp_petr4_off");
  }
//+------------------------------------------------------------------+
