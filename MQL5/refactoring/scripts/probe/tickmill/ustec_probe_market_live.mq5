//+------------------------------------------------------------------+
//| ustec_probe_market_live.mq5                                      |
//| Tickmill USTEC — run Mon–Fri during US cash session.             |
//+------------------------------------------------------------------+
#property script_show_inputs
#property strict

#include "../ProbeBroker.mqh"

input bool   InpWriteFile  = true;
input int    InpTickSample = 20;
input bool   InpSkipClosed = true;

void OnStart()
  {
   RunMarketLiveProbe("Tickmill/USTEC", "USTEC", InpWriteFile, InpTickSample,
                      false, "USTEC", "probe_tickmill_ustec_live", InpSkipClosed);
  }
//+------------------------------------------------------------------+
