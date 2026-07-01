//+------------------------------------------------------------------+
//| epu26_probe_market_live.mq5                                      |
//| AMP EPU26 — run during CME trade session.                         |
//+------------------------------------------------------------------+
#property script_show_inputs
#property strict

#include "../ProbeBroker.mqh"

input bool   InpWriteFile  = true;
input int    InpTickSample = 20;
input bool   InpSkipClosed = true;

void OnStart()
  {
   RunMarketLiveProbe("AMP/EPU26", "EPU26", InpWriteFile, InpTickSample,
                      false, "EPU26", "probe_amp_epu26_live", InpSkipClosed);
  }
//+------------------------------------------------------------------+
