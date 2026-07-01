//+------------------------------------------------------------------+
//| probe_amp_market_live.mq5                                        |
//| AMP Global USA — run during CME futures trade session.           |
//| OrderCheck filling/TIF probes. Does NOT call OrderSend.          |
//+------------------------------------------------------------------+
#property script_show_inputs
#property strict

#include "ProbeBroker.mqh"

input string InpSymbols    = "EPU26,MESU26,ENQU26,MNQU26";
input bool   InpWriteFile  = true;
input int    InpTickSample = 20;
input bool   InpSkipClosed = true;

void OnStart()
  {
   RunMarketLiveProbe(
      "AMP",
      InpSymbols,
      InpWriteFile,
      InpTickSample,
      false,
      "EPU26",
      "probe_amp_live",
      InpSkipClosed
   );
  }
//+------------------------------------------------------------------+
