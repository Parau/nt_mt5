//+------------------------------------------------------------------+
//| probe_tickmill_market_live.mq5                                   |
//| Tickmill — run during trade session. OrderCheck filling probes.  |
//| Does NOT call OrderSend (no positions opened).                   |
//+------------------------------------------------------------------+
#property script_show_inputs
#property strict

#include "ProbeBroker.mqh"

input string InpSymbols    = "USTEC,BTCUSD";
input bool   InpWriteFile  = true;
input int    InpTickSample = 20;
input bool   InpSkipClosed = true;            // skip symbol if session closed now

void OnStart()
  {
   RunMarketLiveProbe(
      "Tickmill",
      InpSymbols,
      InpWriteFile,
      InpTickSample,
      false,
      "USTEC",
      "probe_tickmill_live",
      InpSkipClosed
   );
  }
//+------------------------------------------------------------------+
