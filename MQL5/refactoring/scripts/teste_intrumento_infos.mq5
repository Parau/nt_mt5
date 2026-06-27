//+------------------------------------------------------------------+
//| ProbeBrokerSymbolCapabilities.mq5                                |
//| One-shot broker ground truth: SymbolInfo* + MarketBookAdd        |
//| Target symbols: USTEC, BTCUSD (edit SYMBOLS[] if needed)         |
//+------------------------------------------------------------------+
#property script_show_inputs
#property strict

input string InpSymbols = "USTEC,BTCUSD";   // comma-separated
input bool   InpWriteFile = true;           // also write MQL5/Files/*.txt
input int    InpTickSample = 20;            // recent ticks to sample (0=skip)

//--- helpers
string ServerTag()
  {
   return StringFormat(
      "server=%s login=%I64u company=%s build=%d time=%s",
      AccountInfoString(ACCOUNT_SERVER),
      AccountInfoInteger(ACCOUNT_LOGIN),
      AccountInfoString(ACCOUNT_COMPANY),
      (int)TerminalInfoInteger(TERMINAL_BUILD),
      TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS)
   );
  }

string TradeCalcModeName(const long mode)
  {
   switch((ENUM_SYMBOL_CALC_MODE)mode)
     {
      case SYMBOL_CALC_MODE_FOREX:           return "FOREX";
      case SYMBOL_CALC_MODE_FUTURES:         return "FUTURES";
      case SYMBOL_CALC_MODE_CFD:             return "CFD";
      case SYMBOL_CALC_MODE_CFDINDEX:        return "CFDINDEX";
      case SYMBOL_CALC_MODE_CFDLEVERAGE:     return "CFDLEVERAGE";
      case SYMBOL_CALC_MODE_FOREX_NO_LEVERAGE: return "FOREX_NO_LEVERAGE";
      case SYMBOL_CALC_MODE_EXCH_STOCKS:     return "EXCH_STOCKS";
      case SYMBOL_CALC_MODE_EXCH_FUTURES:    return "EXCH_FUTURES";
      case SYMBOL_CALC_MODE_EXCH_FUTURES_FORTS: return "EXCH_FUTURES_FORTS";
      case SYMBOL_CALC_MODE_EXCH_OPTIONS_MARGIN: return "EXCH_OPTIONS_MARGIN";
      case SYMBOL_CALC_MODE_EXCH_BONDS:      return "EXCH_BONDS";
      case SYMBOL_CALC_MODE_EXCH_STOCKS_MOEX: return "EXCH_STOCKS_MOEX";
      case SYMBOL_CALC_MODE_EXCH_BONDS_MOEX: return "EXCH_BONDS_MOEX";
      case SYMBOL_CALC_MODE_SERV_COLLATERAL: return "SERV_COLLATERAL";
      default:                               return "UNKNOWN";
     }
  }

string TradeModeName(const long mode)
  {
   switch((ENUM_SYMBOL_TRADE_MODE)mode)
     {
      case SYMBOL_TRADE_MODE_DISABLED:     return "DISABLED";
      case SYMBOL_TRADE_MODE_LONGONLY:     return "LONGONLY";
      case SYMBOL_TRADE_MODE_SHORTONLY:    return "SHORTONLY";
      case SYMBOL_TRADE_MODE_CLOSEONLY:    return "CLOSEONLY";
      case SYMBOL_TRADE_MODE_FULL:         return "FULL";
      default:                             return "UNKNOWN";
     }
  }

string BookTypeName(const ENUM_BOOK_TYPE t)
  {
   switch(t)
     {
      case BOOK_TYPE_SELL:       return "SELL";
      case BOOK_TYPE_BUY:        return "BUY";
      case BOOK_TYPE_SELL_MARKET: return "SELL_MARKET";
      case BOOK_TYPE_BUY_MARKET:  return "BUY_MARKET";
      default:                   return "UNKNOWN";
     }
  }

void Append(string &buf, const string line)
  {
   Print(line);
   buf += line + "\r\n";
  }

bool EnsureSelected(const string symbol)
  {
   if(SymbolInfoInteger(symbol, SYMBOL_SELECT))
      return true;
   if(!SymbolSelect(symbol, true))
     {
      Print("SymbolSelect failed: ", symbol, " err=", GetLastError());
      return false;
     }
   return true;
  }

void DumpSymbolInfo(const string symbol, string &buf)
  {
   Append(buf, "");
   Append(buf, "========== SYMBOL: " + symbol + " ==========");

   if(!EnsureSelected(symbol))
     {
      Append(buf, "RESULT: symbol not available on this account/server");
      return;
     }

   if(!SymbolInfoInteger(symbol, SYMBOL_EXIST))
     {
      Append(buf, "RESULT: SYMBOL_EXIST=false");
      return;
     }

   // --- integers (adapter-relevant + DOM)
   Append(buf, "--- SymbolInfoInteger ---");
   Append(buf, StringFormat("SYMBOL_EXIST=%d", (int)SymbolInfoInteger(symbol, SYMBOL_EXIST)));
   Append(buf, StringFormat("SYMBOL_SELECT=%d", (int)SymbolInfoInteger(symbol, SYMBOL_SELECT)));
   Append(buf, StringFormat("SYMBOL_VISIBLE=%d", (int)SymbolInfoInteger(symbol, SYMBOL_VISIBLE)));
   Append(buf, StringFormat("SYMBOL_CUSTOM=%d", (int)SymbolInfoInteger(symbol, SYMBOL_CUSTOM)));
   Append(buf, StringFormat("SYMBOL_DIGITS=%d", (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS)));
   Append(buf, StringFormat("SYMBOL_SPREAD=%d", (int)SymbolInfoInteger(symbol, SYMBOL_SPREAD)));
   Append(buf, StringFormat("SYMBOL_SPREAD_FLOAT=%d", (int)SymbolInfoInteger(symbol, SYMBOL_SPREAD_FLOAT)));
   Append(buf, StringFormat("SYMBOL_TICKS_BOOKDEPTH=%d  <-- 0 means no DOM",
                            (int)SymbolInfoInteger(symbol, SYMBOL_TICKS_BOOKDEPTH)));
   Append(buf, StringFormat("SYMBOL_TRADE_CALC_MODE=%d (%s)",
                            (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_CALC_MODE),
                            TradeCalcModeName(SymbolInfoInteger(symbol, SYMBOL_TRADE_CALC_MODE))));
   Append(buf, StringFormat("SYMBOL_TRADE_MODE=%d (%s)",
                            (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_MODE),
                            TradeModeName(SymbolInfoInteger(symbol, SYMBOL_TRADE_MODE))));
   Append(buf, StringFormat("SYMBOL_TRADE_EXEMODE=%d", (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_EXEMODE)));
   Append(buf, StringFormat("SYMBOL_FILLING_MODE=%d", (int)SymbolInfoInteger(symbol, SYMBOL_FILLING_MODE)));
   Append(buf, StringFormat("SYMBOL_ORDER_MODE=%d", (int)SymbolInfoInteger(symbol, SYMBOL_ORDER_MODE)));
   Append(buf, StringFormat("SYMBOL_ORDER_GTC_MODE=%d", (int)SymbolInfoInteger(symbol, SYMBOL_ORDER_GTC_MODE)));
   Append(buf, StringFormat("SYMBOL_SWAP_MODE=%d", (int)SymbolInfoInteger(symbol, SYMBOL_SWAP_MODE)));
   Append(buf, StringFormat("SYMBOL_TRADE_STOPS_LEVEL=%d", (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_STOPS_LEVEL)));
   Append(buf, StringFormat("SYMBOL_TRADE_FREEZE_LEVEL=%d", (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_FREEZE_LEVEL)));
   Append(buf, StringFormat("SYMBOL_TIME=%s", TimeToString((datetime)SymbolInfoInteger(symbol, SYMBOL_TIME), TIME_DATE | TIME_SECONDS)));

   // --- doubles
   Append(buf, "--- SymbolInfoDouble ---");
   Append(buf, StringFormat("SYMBOL_BID=%.10f", SymbolInfoDouble(symbol, SYMBOL_BID)));
   Append(buf, StringFormat("SYMBOL_ASK=%.10f", SymbolInfoDouble(symbol, SYMBOL_ASK)));
   Append(buf, StringFormat("SYMBOL_LAST=%.10f", SymbolInfoDouble(symbol, SYMBOL_LAST)));
   Append(buf, StringFormat("SYMBOL_POINT=%.10f", SymbolInfoDouble(symbol, SYMBOL_POINT)));
   Append(buf, StringFormat("SYMBOL_TRADE_TICK_SIZE=%.10f", SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_SIZE)));
   Append(buf, StringFormat("SYMBOL_TRADE_TICK_VALUE=%.10f", SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_VALUE)));
   Append(buf, StringFormat("SYMBOL_TRADE_CONTRACT_SIZE=%.2f", SymbolInfoDouble(symbol, SYMBOL_TRADE_CONTRACT_SIZE)));
   Append(buf, StringFormat("SYMBOL_VOLUME_MIN=%.4f", SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN)));
   Append(buf, StringFormat("SYMBOL_VOLUME_MAX=%.4f", SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX)));
   Append(buf, StringFormat("SYMBOL_VOLUME_STEP=%.4f", SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP)));
   Append(buf, StringFormat("SYMBOL_VOLUME_LIMIT=%.4f", SymbolInfoDouble(symbol, SYMBOL_VOLUME_LIMIT)));

   // --- strings
   Append(buf, "--- SymbolInfoString ---");
   Append(buf, StringFormat("SYMBOL_CURRENCY_BASE=%s", SymbolInfoString(symbol, SYMBOL_CURRENCY_BASE)));
   Append(buf, StringFormat("SYMBOL_CURRENCY_PROFIT=%s", SymbolInfoString(symbol, SYMBOL_CURRENCY_PROFIT)));
   Append(buf, StringFormat("SYMBOL_CURRENCY_MARGIN=%s", SymbolInfoString(symbol, SYMBOL_CURRENCY_MARGIN)));
   Append(buf, StringFormat("SYMBOL_DESCRIPTION=%s", SymbolInfoString(symbol, SYMBOL_DESCRIPTION)));
   Append(buf, StringFormat("SYMBOL_PATH=%s", SymbolInfoString(symbol, SYMBOL_PATH)));
   Append(buf, StringFormat("SYMBOL_BASIS=%s", SymbolInfoString(symbol, SYMBOL_BASIS)));
   Append(buf, StringFormat("SYMBOL_ISIN=%s", SymbolInfoString(symbol, SYMBOL_ISIN)));
  }

void ProbeMarketBook(const string symbol, string &buf)
  {
   Append(buf, "--- MarketBookAdd / MarketBookGet ---");

   const int bookdepth = (int)SymbolInfoInteger(symbol, SYMBOL_TICKS_BOOKDEPTH);
   ResetLastError();
   const bool added = MarketBookAdd(symbol);
   const int err_add = GetLastError();

   Append(buf, StringFormat("MarketBookAdd(%s) => %s  err=%d  ticks_bookdepth=%d",
                            symbol, added ? "TRUE" : "FALSE", err_add, bookdepth));

   if(!added)
     {
      Append(buf, "DOM verdict: NOT AVAILABLE (subscription failed)");
      return;
     }

   MqlBookInfo book[];
   ResetLastError();
   const bool got = MarketBookGet(symbol, book);
   const int err_get = GetLastError();
   const int n = got ? ArraySize(book) : 0;

   Append(buf, StringFormat("MarketBookGet(%s) => %s  levels=%d  err=%d",
                            symbol, got ? "TRUE" : "FALSE", n, err_get));

   const int show = MathMin(n, 10);
   for(int i = 0; i < show; i++)
      Append(buf, StringFormat("  [%d] type=%s price=%.10f volume=%.4f",
                               i,
                               BookTypeName(book[i].type),
                               book[i].price,
                               (double)book[i].volume));

   if(n == 0)
      Append(buf, "DOM verdict: subscription OK but book EMPTY (broker may not publish depth)");
   else
      Append(buf, StringFormat("DOM verdict: AVAILABLE (%d levels at snapshot)", n));

   if(!MarketBookRelease(symbol))
      Append(buf, StringFormat("MarketBookRelease failed err=%d", GetLastError()));
  }

void ProbeTickFlags(const string symbol, const int count, string &buf)
  {
   if(count <= 0)
      return;

   Append(buf, "--- CopyTicks sample (recent) ---");

   MqlTick ticks[];
   const int copied = CopyTicks(symbol, ticks, COPY_TICKS_ALL, 0, count);
   Append(buf, StringFormat("CopyTicks copied=%d", copied));

   if(copied <= 0)
      return;

   int bid_only = 0, ask_only = 0, last_flag = 0, vol_flag = 0;
   for(int i = 0; i < copied; i++)
     {
      const uint f = ticks[i].flags;
      if((f & TICK_FLAG_BID) != 0 && (f & TICK_FLAG_ASK) == 0) bid_only++;
      if((f & TICK_FLAG_ASK) != 0 && (f & TICK_FLAG_BID) == 0) ask_only++;
      if((f & TICK_FLAG_LAST) != 0) last_flag++;
      if((f & TICK_FLAG_VOLUME) != 0) vol_flag++;

      if(i < MathMin(copied, 5))
         Append(buf, StringFormat("  tick[%d] time=%s bid=%.5f ask=%.5f last=%.5f vol=%I64u flags=%u",
                                  i,
                                  TimeToString(ticks[i].time_msc / 1000, TIME_DATE | TIME_SECONDS),
                                  ticks[i].bid, ticks[i].ask, ticks[i].last, ticks[i].volume, f));
     }

   Append(buf, StringFormat("flags summary: last=%d volume=%d (of %d ticks)",
                            last_flag, vol_flag, copied));
   Append(buf, "Note: MT5 UI export flags often differ by 128 from API tick flags.");
  }

void SplitSymbols(const string csv, string &out[])
  {
   string tmp = csv;
   StringReplace(tmp, " ", "");
   int n = StringSplit(tmp, ',', out);
   if(n <= 0)
     {
      ArrayResize(out, 1);
      out[0] = "USTEC";
     }
  }

void OnStart()
  {
   string report = "";
   Append(report, "===== ProbeBrokerSymbolCapabilities =====");
   Append(report, ServerTag());

   string symbols[];
   SplitSymbols(InpSymbols, symbols);

   for(int i = 0; i < ArraySize(symbols); i++)
     {
      const string sym = symbols[i];
      if(StringLen(sym) == 0)
         continue;

      DumpSymbolInfo(sym, report);
      ProbeMarketBook(sym, report);
      ProbeTickFlags(sym, InpTickSample, report);
     }

   Append(report, "===== END =====");

   if(InpWriteFile)
     {
      const string fname = StringFormat("probe_broker_%s_%I64u.txt",
                                        AccountInfoString(ACCOUNT_SERVER),
                                        AccountInfoInteger(ACCOUNT_LOGIN));
      const int h = FileOpen(fname, FILE_WRITE | FILE_TXT | FILE_ANSI);
      if(h != INVALID_HANDLE)
        {
         FileWriteString(h, report);
         FileClose(h);
         Print("Report written to MQL5/Files/", fname);
        }
      else
         Print("FileOpen failed err=", GetLastError());
     }
  }
//+------------------------------------------------------------------+