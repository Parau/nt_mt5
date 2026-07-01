//+------------------------------------------------------------------+
//| mnqu26_probe_market_off_hours.mq5                                |
//| AMP MNQU26 (Micro E-mini Nasdaq Sep 2026) — off-hours probe.     |
//+------------------------------------------------------------------+
#property script_show_inputs
#property strict

#include "../ProbeBroker.mqh"

input bool   InpWriteFile  = true;
input int    InpTickSample = 20;

void OnStart()
  {
   RunMarketOffHoursProbe("AMP/MNQU26", "MNQU26", InpWriteFile, InpTickSample,
                          false, "MNQU26", "probe_amp_mnqu26_off");
  }
//+------------------------------------------------------------------+
