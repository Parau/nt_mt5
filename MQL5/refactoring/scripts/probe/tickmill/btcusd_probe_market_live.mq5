//+------------------------------------------------------------------+
//| btcusd_probe_market_live.mq5                                     |
//| Tickmill BTCUSD — live OrderCheck filling probe.                 |
//+------------------------------------------------------------------+
#property script_show_inputs
#property strict

#include "../ProbeBroker.mqh"

input bool   InpWriteFile  = true;
input int    InpTickSample = 20;
input bool   InpSkipClosed = false;           // crypto CFD often trades outside equity hours

void OnStart()
  {
   RunMarketLiveProbe("Tickmill/BTCUSD", "BTCUSD", InpWriteFile, InpTickSample,
                      false, "BTCUSD", "probe_tickmill_btcusd_live", InpSkipClosed);
  }
//+------------------------------------------------------------------+
