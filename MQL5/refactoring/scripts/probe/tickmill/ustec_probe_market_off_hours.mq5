//+------------------------------------------------------------------+
//| ustec_probe_market_off_hours.mq5                                 |
//| Tickmill USTEC — off-hours SymbolInfo probe (US index session).  |
//+------------------------------------------------------------------+
#property script_show_inputs
#property strict

#include "../ProbeBroker.mqh"

input bool   InpWriteFile  = true;
input int    InpTickSample = 20;

void OnStart()
  {
   RunMarketOffHoursProbe("Tickmill/USTEC", "USTEC", InpWriteFile, InpTickSample,
                          false, "USTEC", "probe_tickmill_ustec_off");
  }
//+------------------------------------------------------------------+
