//+------------------------------------------------------------------+
//| btcusd_probe_market_off_hours.mq5                                |
//| Tickmill BTCUSD — off-hours SymbolInfo probe (~24/7 symbol).     |
//+------------------------------------------------------------------+
#property script_show_inputs
#property strict

#include "../ProbeBroker.mqh"

input bool   InpWriteFile  = true;
input int    InpTickSample = 20;

void OnStart()
  {
   RunMarketOffHoursProbe("Tickmill/BTCUSD", "BTCUSD", InpWriteFile, InpTickSample,
                          false, "BTCUSD", "probe_tickmill_btcusd_off");
  }
//+------------------------------------------------------------------+
