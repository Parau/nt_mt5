//+------------------------------------------------------------------+
//| enqu26_probe_market_off_hours.mq5                                |
//| AMP ENQU26 (E-mini Nasdaq Sep 2026) — off-hours probe.           |
//+------------------------------------------------------------------+
#property script_show_inputs
#property strict

#include "../ProbeBroker.mqh"

input bool   InpWriteFile  = true;
input int    InpTickSample = 20;

void OnStart()
  {
   RunMarketOffHoursProbe("AMP/ENQU26", "ENQU26", InpWriteFile, InpTickSample,
                          false, "ENQU26", "probe_amp_enqu26_off");
  }
//+------------------------------------------------------------------+
