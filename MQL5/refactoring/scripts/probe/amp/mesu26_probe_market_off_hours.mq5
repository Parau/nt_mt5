//+------------------------------------------------------------------+
//| mesu26_probe_market_off_hours.mq5                                |
//| AMP MESU26 (Micro E-mini S&P Sep 2026) — off-hours probe.        |
//+------------------------------------------------------------------+
#property script_show_inputs
#property strict

#include "../ProbeBroker.mqh"

input bool   InpWriteFile  = true;
input int    InpTickSample = 20;

void OnStart()
  {
   RunMarketOffHoursProbe("AMP/MESU26", "MESU26", InpWriteFile, InpTickSample,
                          false, "MESU26", "probe_amp_mesu26_off");
  }
//+------------------------------------------------------------------+
