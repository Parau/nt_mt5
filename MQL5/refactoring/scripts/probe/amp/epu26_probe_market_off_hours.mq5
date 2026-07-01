//+------------------------------------------------------------------+
//| epu26_probe_market_off_hours.mq5                                 |
//| AMP EPU26 (E-mini S&P Sep 2026) — off-hours SymbolInfo probe.    |
//+------------------------------------------------------------------+
#property script_show_inputs
#property strict

#include "../ProbeBroker.mqh"

input bool   InpWriteFile  = true;
input int    InpTickSample = 20;

void OnStart()
  {
   RunMarketOffHoursProbe("AMP/EPU26", "EPU26", InpWriteFile, InpTickSample,
                          false, "EPU26", "probe_amp_epu26_off");
  }
//+------------------------------------------------------------------+
