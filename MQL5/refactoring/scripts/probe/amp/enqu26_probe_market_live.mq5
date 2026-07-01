//+------------------------------------------------------------------+
//| enqu26_probe_market_live.mq5                                     |
//| AMP ENQU26 — run during CME trade session.                       |
//+------------------------------------------------------------------+
#property script_show_inputs
#property strict

#include "../ProbeBroker.mqh"

input bool   InpWriteFile  = true;
input int    InpTickSample = 20;
input bool   InpSkipClosed = true;

void OnStart()
  {
   RunMarketLiveProbe("AMP/ENQU26", "ENQU26", InpWriteFile, InpTickSample,
                      false, "ENQU26", "probe_amp_enqu26_live", InpSkipClosed);
  }
//+------------------------------------------------------------------+
