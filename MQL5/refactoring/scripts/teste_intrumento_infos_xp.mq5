//+------------------------------------------------------------------+
//| teste_intrumento_infos_xp.mq5                                   |
//| One-shot broker ground truth probe for nt_mt5 — XP / B3.         |
//| Account capabilities + SymbolInfo* + sessions + MarketBookAdd   |
//| Default symbols: WIN$, WDO$, PETR4, DI1F27 (edit InpSymbols)     |
//| Run during B3 session for meaningful tick/DOM samples.            |
//+------------------------------------------------------------------+
#property script_show_inputs
#property strict

// Verify exact names in Market Watch (XP may use WINJ25, WDOQ25, etc.).
input string InpSymbols = "WIN$,WDO$,WINQ26,WDON26,PETR4,DI1F27";  // comma-separated
input bool   InpWriteFile = true;              // also write MQL5/Files/*.txt
input int    InpTickSample = 20;               // recent ticks to sample (0=skip)

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
      default:                               return StringFormat("UNKNOWN(%d)", (int)mode);
     }
  }

string MarginModeName(const long mode)
  {
   switch((ENUM_ACCOUNT_MARGIN_MODE)mode)
     {
      case ACCOUNT_MARGIN_MODE_RETAIL_NETTING: return "RETAIL_NETTING";
      case ACCOUNT_MARGIN_MODE_EXCHANGE:       return "EXCHANGE";
      case ACCOUNT_MARGIN_MODE_RETAIL_HEDGING: return "RETAIL_HEDGING";
      default:                                 return StringFormat("UNKNOWN(%d)", (int)mode);
     }
  }

string AccountTradeModeName(const long mode)
  {
   switch((ENUM_ACCOUNT_TRADE_MODE)mode)
     {
      case ACCOUNT_TRADE_MODE_DEMO:    return "DEMO";
      case ACCOUNT_TRADE_MODE_CONTEST: return "CONTEST";
      case ACCOUNT_TRADE_MODE_REAL:    return "REAL";
      default:                          return StringFormat("UNKNOWN(%d)", (int)mode);
     }
  }

string DayName(const ENUM_DAY_OF_WEEK d)
  {
   switch(d)
     {
      case SUNDAY:    return "SUN";
      case MONDAY:    return "MON";
      case TUESDAY:   return "TUE";
      case WEDNESDAY: return "WED";
      case THURSDAY:  return "THU";
      case FRIDAY:    return "FRI";
      case SATURDAY:  return "SAT";
      default:        return "?";
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

void DumpAccountCapabilities(string &buf)
  {
   Append(buf, "");
   Append(buf, "========== ACCOUNT CAPABILITIES ==========");
   Append(buf, "--- AccountInfoInteger ---");

   const long margin_mode = AccountInfoInteger(ACCOUNT_MARGIN_MODE);
   Append(buf, StringFormat("ACCOUNT_MARGIN_MODE=%d (%s)  <-- netting=0 exchange=1 hedging=2",
                            (int)margin_mode, MarginModeName(margin_mode)));
   Append(buf, StringFormat("ACCOUNT_TRADE_MODE=%d (%s)",
                            (int)AccountInfoInteger(ACCOUNT_TRADE_MODE),
                            AccountTradeModeName(AccountInfoInteger(ACCOUNT_TRADE_MODE))));
   Append(buf, StringFormat("ACCOUNT_TRADE_ALLOWED=%d", (int)AccountInfoInteger(ACCOUNT_TRADE_ALLOWED)));
   Append(buf, StringFormat("ACCOUNT_TRADE_EXPERT=%d", (int)AccountInfoInteger(ACCOUNT_TRADE_EXPERT)));
   Append(buf, StringFormat("ACCOUNT_LEVERAGE=%d", (int)AccountInfoInteger(ACCOUNT_LEVERAGE)));
   Append(buf, StringFormat("ACCOUNT_LIMIT_ORDERS=%d", (int)AccountInfoInteger(ACCOUNT_LIMIT_ORDERS)));
   Append(buf, StringFormat("ACCOUNT_MARGIN_SO_MODE=%d", (int)AccountInfoInteger(ACCOUNT_MARGIN_SO_MODE)));

   Append(buf, "--- AccountInfoDouble ---");
   Append(buf, StringFormat("ACCOUNT_BALANCE=%.2f", AccountInfoDouble(ACCOUNT_BALANCE)));
   Append(buf, StringFormat("ACCOUNT_EQUITY=%.2f", AccountInfoDouble(ACCOUNT_EQUITY)));
   Append(buf, StringFormat("ACCOUNT_MARGIN_FREE=%.2f", AccountInfoDouble(ACCOUNT_MARGIN_FREE)));

   Append(buf, "--- AccountInfoString ---");
   Append(buf, StringFormat("ACCOUNT_NAME=%s", AccountInfoString(ACCOUNT_NAME)));
   Append(buf, StringFormat("ACCOUNT_CURRENCY=%s", AccountInfoString(ACCOUNT_CURRENCY)));
   Append(buf, StringFormat("ACCOUNT_SERVER=%s", AccountInfoString(ACCOUNT_SERVER)));
   Append(buf, StringFormat("ACCOUNT_COMPANY=%s", AccountInfoString(ACCOUNT_COMPANY)));

   Append(buf, "--- TerminalInfo ---");
   Append(buf, StringFormat("TERMINAL_CONNECTED=%d", (int)TerminalInfoInteger(TERMINAL_CONNECTED)));
   Append(buf, StringFormat("TERMINAL_TRADE_ALLOWED=%d", (int)TerminalInfoInteger(TERMINAL_TRADE_ALLOWED)));
   Append(buf, StringFormat("TERMINAL_BUILD=%d", (int)TerminalInfoInteger(TERMINAL_BUILD)));
   Append(buf, "Note: symbol session hours below use SERVER TIME (not UTC/BRT).");
   Append(buf, "B3: server time is often UTC-3 (BRT) — confirm against exchange calendar.");
  }

void DumpSymbolSessions(const string symbol, string &buf)
  {
   Append(buf, "--- Symbol sessions (Quote=Q / Trade=T) ---");

   if(!EnsureSelected(symbol))
     {
      Append(buf, "RESULT: symbol not selected — sessions unavailable");
      return;
     }

   datetime from = 0, to = 0;
   for(int d = SUNDAY; d <= SATURDAY; d++)
     {
      string line = DayName((ENUM_DAY_OF_WEEK)d) + ": ";
      bool any = false;

      if(SymbolInfoSessionQuote(symbol, (ENUM_DAY_OF_WEEK)d, 0, from, to))
        {
         line += StringFormat("Q[%s-%s]",
                              TimeToString(from, TIME_MINUTES),
                              TimeToString(to, TIME_MINUTES));
         any = true;
         for(int s = 1; SymbolInfoSessionQuote(symbol, (ENUM_DAY_OF_WEEK)d, s, from, to); s++)
            line += StringFormat(" Q[%s-%s]",
                                   TimeToString(from, TIME_MINUTES),
                                   TimeToString(to, TIME_MINUTES));
        }

      if(SymbolInfoSessionTrade(symbol, (ENUM_DAY_OF_WEEK)d, 0, from, to))
        {
         line += StringFormat(" T[%s-%s]",
                              TimeToString(from, TIME_MINUTES),
                              TimeToString(to, TIME_MINUTES));
         any = true;
         for(int s = 1; SymbolInfoSessionTrade(symbol, (ENUM_DAY_OF_WEEK)d, s, from, to); s++)
            line += StringFormat(" T[%s-%s]",
                                   TimeToString(from, TIME_MINUTES),
                                   TimeToString(to, TIME_MINUTES));
        }

      if(!any)
         line += "(closed)";
      Append(buf, line);
     }
  }

void DumpSymbolContractDates(const string symbol, string &buf)
  {
   Append(buf, "--- Contract lifecycle (B3 futures / listed) ---");

   const datetime start = (datetime)SymbolInfoInteger(symbol, SYMBOL_START_TIME);
   const datetime expiry = (datetime)SymbolInfoInteger(symbol, SYMBOL_EXPIRATION_TIME);
   Append(buf, StringFormat("SYMBOL_START_TIME=%s", TimeToString(start, TIME_DATE | TIME_SECONDS)));
   Append(buf, StringFormat("SYMBOL_EXPIRATION_TIME=%s", TimeToString(expiry, TIME_DATE | TIME_SECONDS)));
   Append(buf, StringFormat("SYMBOL_EXPIRATION_MODE=%d", (int)SymbolInfoInteger(symbol, SYMBOL_EXPIRATION_MODE)));

   if(start == 0 && expiry == 0)
      Append(buf, "Note: zero dates — common for spot equities; check path/description for futures rollover.");
  }

void DumpSymbolInfo(const string symbol, string &buf)
  {
   Append(buf, "");
   Append(buf, "========== SYMBOL: " + symbol + " ==========");

   if(!EnsureSelected(symbol))
     {
      Append(buf, "RESULT: symbol not available on this account/server");
      Append(buf, "Hint: open Market Watch on XP, copy exact symbol name (e.g. WINJ25, WDOQ25).");
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
   const int fill = (int)SymbolInfoInteger(symbol, SYMBOL_FILLING_MODE);
   Append(buf, StringFormat("SYMBOL_FILLING_MODE=%d", fill));
   string fill_dec = "";
   // Bitmask: 1=FOK, 2=IOC, 4=RETURN (ORDER_FILLING_* semantics)
   if((fill & 1) != 0) fill_dec += "FOK ";
   if((fill & 2) != 0) fill_dec += "IOC ";
   if((fill & 4) != 0) fill_dec += "RETURN ";
   if(StringLen(fill_dec) == 0) fill_dec = "none ";
   Append(buf, StringFormat("SYMBOL_FILLING_MODE decode: %s(bitmask=%d)", fill_dec, fill));
   Append(buf, StringFormat("SYMBOL_ORDER_MODE=%d", (int)SymbolInfoInteger(symbol, SYMBOL_ORDER_MODE)));
   Append(buf, StringFormat("SYMBOL_ORDER_GTC_MODE=%d", (int)SymbolInfoInteger(symbol, SYMBOL_ORDER_GTC_MODE)));
   Append(buf, StringFormat("SYMBOL_SWAP_MODE=%d", (int)SymbolInfoInteger(symbol, SYMBOL_SWAP_MODE)));
   Append(buf, StringFormat("SYMBOL_TRADE_STOPS_LEVEL=%d", (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_STOPS_LEVEL)));
   Append(buf, StringFormat("SYMBOL_TRADE_FREEZE_LEVEL=%d", (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_FREEZE_LEVEL)));
   Append(buf, StringFormat("SYMBOL_TIME=%s", TimeToString((datetime)SymbolInfoInteger(symbol, SYMBOL_TIME), TIME_DATE | TIME_SECONDS)));

   DumpSymbolContractDates(symbol, buf);

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
   Append(buf, StringFormat("SYMBOL_SECTOR=%d", (int)SymbolInfoInteger(symbol, SYMBOL_SECTOR)));
   Append(buf, StringFormat("SYMBOL_SECTOR_NAME=%s", SymbolInfoString(symbol, SYMBOL_SECTOR_NAME)));
   Append(buf, StringFormat("SYMBOL_COUNTRY=%s", SymbolInfoString(symbol, SYMBOL_COUNTRY)));
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
     {
      Append(buf, "Tick verdict: NO SAMPLES (market closed or no history — re-run during B3 session)");
      return;
     }

   int bid_only = 0, ask_only = 0, last_flag = 0, vol_flag = 0;
   int both_ba = 0;
   for(int i = 0; i < copied; i++)
     {
      const uint f = ticks[i].flags;
      if((f & TICK_FLAG_BID) != 0 && (f & TICK_FLAG_ASK) == 0) bid_only++;
      if((f & TICK_FLAG_ASK) != 0 && (f & TICK_FLAG_BID) == 0) ask_only++;
      if((f & TICK_FLAG_BID) != 0 && (f & TICK_FLAG_ASK) != 0) both_ba++;
      if((f & TICK_FLAG_LAST) != 0) last_flag++;
      if((f & TICK_FLAG_VOLUME) != 0) vol_flag++;

      if(i < MathMin(copied, 5))
         Append(buf, StringFormat("  tick[%d] time_msc=%I64u bid=%.5f ask=%.5f last=%.5f vol=%I64u flags=%u",
                                  i,
                                  ticks[i].time_msc,
                                  ticks[i].bid, ticks[i].ask, ticks[i].last, ticks[i].volume, f));
     }

   Append(buf, StringFormat("flags summary: bid+ask=%d bid_only=%d ask_only=%d last=%d volume=%d (of %d)",
                            both_ba, bid_only, ask_only, last_flag, vol_flag, copied));
   Append(buf, "Note: MT5 UI export flags often differ by 128 from API tick flags.");

   if(last_flag > 0 || vol_flag > 0)
      Append(buf, "Adapter hint: TradeTick may be viable — confirm SYMBOL_LAST and TICK_FLAG_LAST in VenueProfile.");
   else
      Append(buf, "Adapter hint: QuoteTick-only sample (no last/volume flags) — compare with SYMBOL_LAST field above.");
  }

void SplitSymbols(const string csv, string &out[])
  {
   string tmp = csv;
   StringReplace(tmp, " ", "");
   int n = StringSplit(tmp, ',', out);
   if(n <= 0)
     {
      ArrayResize(out, 1);
      out[0] = "WIN$";
     }
  }

void OnStart()
  {
   string report = "";
   Append(report, "===== ProbeBrokerSymbolCapabilities (XP / B3) =====");
   Append(report, ServerTag());
   DumpAccountCapabilities(report);

   string symbols[];
   SplitSymbols(InpSymbols, symbols);

   for(int i = 0; i < ArraySize(symbols); i++)
     {
      const string sym = symbols[i];
      if(StringLen(sym) == 0)
         continue;

      DumpSymbolInfo(sym, report);
      DumpSymbolSessions(sym, report);
      ProbeMarketBook(sym, report);
      ProbeTickFlags(sym, InpTickSample, report);
     }

   Append(report, "===== END =====");
   Append(report, "Next: document output in res/xp_b3_restrictions.md (mirror tickmill_restrictions.md).");

   if(InpWriteFile)
     {
      const string fname = StringFormat("probe_xp_%s_%I64u.txt",
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
