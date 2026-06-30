//+------------------------------------------------------------------+
//| ProbeBroker.mqh — shared broker ground-truth probes (nt_mt5)     |
//| Self-contained under scripts/probe/ (not part of deploy sync).   |
//| market_off_hours: SymbolInfo*, sessions, DOM — no OrderSend.     |
//| market_live: session open + OrderCheck filling/TIF probes.       |
//+------------------------------------------------------------------+
#ifndef PROBE_BROKER_MQH
#define PROBE_BROKER_MQH

// Probe magic — identifies probe requests in the terminal journal.
#define PROBE_MAGIC 20260628

//+------------------------------------------------------------------+
string ProbeServerTag()
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

//+------------------------------------------------------------------+
string ProbeTradeCalcModeName(const long mode)
  {
   switch((ENUM_SYMBOL_CALC_MODE)mode)
     {
      case SYMBOL_CALC_MODE_FOREX:             return "FOREX";
      case SYMBOL_CALC_MODE_FUTURES:           return "FUTURES";
      case SYMBOL_CALC_MODE_CFD:               return "CFD";
      case SYMBOL_CALC_MODE_CFDINDEX:          return "CFDINDEX";
      case SYMBOL_CALC_MODE_CFDLEVERAGE:       return "CFDLEVERAGE";
      case SYMBOL_CALC_MODE_FOREX_NO_LEVERAGE: return "FOREX_NO_LEVERAGE";
      case SYMBOL_CALC_MODE_EXCH_STOCKS:       return "EXCH_STOCKS";
      case SYMBOL_CALC_MODE_EXCH_FUTURES:     return "EXCH_FUTURES";
      case SYMBOL_CALC_MODE_EXCH_FUTURES_FORTS: return "EXCH_FUTURES_FORTS";
      case SYMBOL_CALC_MODE_EXCH_OPTIONS_MARGIN: return "EXCH_OPTIONS_MARGIN";
      case SYMBOL_CALC_MODE_EXCH_BONDS:        return "EXCH_BONDS";
      case SYMBOL_CALC_MODE_EXCH_STOCKS_MOEX:  return "EXCH_STOCKS_MOEX";
      case SYMBOL_CALC_MODE_EXCH_BONDS_MOEX:   return "EXCH_BONDS_MOEX";
      case SYMBOL_CALC_MODE_SERV_COLLATERAL:   return "SERV_COLLATERAL";
      default: return StringFormat("UNKNOWN(%d)", (int)mode);
     }
  }

//+------------------------------------------------------------------+
string ProbeMarginModeName(const long mode)
  {
   switch((ENUM_ACCOUNT_MARGIN_MODE)mode)
     {
      case ACCOUNT_MARGIN_MODE_RETAIL_NETTING: return "RETAIL_NETTING";
      case ACCOUNT_MARGIN_MODE_EXCHANGE:       return "EXCHANGE";
      case ACCOUNT_MARGIN_MODE_RETAIL_HEDGING: return "RETAIL_HEDGING";
      default: return StringFormat("UNKNOWN(%d)", (int)mode);
     }
  }

//+------------------------------------------------------------------+
string ProbeAccountTradeModeName(const long mode)
  {
   switch((ENUM_ACCOUNT_TRADE_MODE)mode)
     {
      case ACCOUNT_TRADE_MODE_DEMO:    return "DEMO";
      case ACCOUNT_TRADE_MODE_CONTEST: return "CONTEST";
      case ACCOUNT_TRADE_MODE_REAL:    return "REAL";
      default: return StringFormat("UNKNOWN(%d)", (int)mode);
     }
  }

//+------------------------------------------------------------------+
string ProbeDayName(const ENUM_DAY_OF_WEEK d)
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

//+------------------------------------------------------------------+
string ProbeTradeModeName(const long mode)
  {
   switch((ENUM_SYMBOL_TRADE_MODE)mode)
     {
      case SYMBOL_TRADE_MODE_DISABLED:  return "DISABLED";
      case SYMBOL_TRADE_MODE_LONGONLY:  return "LONGONLY";
      case SYMBOL_TRADE_MODE_SHORTONLY: return "SHORTONLY";
      case SYMBOL_TRADE_MODE_CLOSEONLY: return "CLOSEONLY";
      case SYMBOL_TRADE_MODE_FULL:      return "FULL";
      default:                          return "UNKNOWN";
     }
  }

//+------------------------------------------------------------------+
string ProbeBookTypeName(const ENUM_BOOK_TYPE t)
  {
   switch(t)
     {
      case BOOK_TYPE_SELL:        return "SELL";
      case BOOK_TYPE_BUY:         return "BUY";
      case BOOK_TYPE_SELL_MARKET: return "SELL_MARKET";
      case BOOK_TYPE_BUY_MARKET:  return "BUY_MARKET";
      default:                    return "UNKNOWN";
     }
  }

//+------------------------------------------------------------------+
string ProbeFillingEnumName(const ENUM_ORDER_TYPE_FILLING f)
  {
   switch(f)
     {
      case ORDER_FILLING_FOK:    return "FOK";
      case ORDER_FILLING_IOC:    return "IOC";
      case ORDER_FILLING_RETURN: return "RETURN";
      default:                   return StringFormat("UNKNOWN(%d)", (int)f);
     }
  }

//+------------------------------------------------------------------+
string ProbeRetcodeName(const uint retcode)
  {
   switch(retcode)
     {
      case TRADE_RETCODE_REQUOTE:           return "REQUOTE";
      case TRADE_RETCODE_REJECT:            return "REJECT";
      case TRADE_RETCODE_CANCEL:            return "CANCEL";
      case TRADE_RETCODE_PLACED:            return "PLACED";
      case TRADE_RETCODE_DONE:              return "DONE";
      case TRADE_RETCODE_DONE_PARTIAL:      return "DONE_PARTIAL";
      case TRADE_RETCODE_ERROR:             return "ERROR";
      case TRADE_RETCODE_TIMEOUT:           return "TIMEOUT";
      case TRADE_RETCODE_INVALID:           return "INVALID";
      case TRADE_RETCODE_INVALID_VOLUME:    return "INVALID_VOLUME";
      case TRADE_RETCODE_INVALID_PRICE:     return "INVALID_PRICE";
      case TRADE_RETCODE_INVALID_STOPS:     return "INVALID_STOPS";
      case TRADE_RETCODE_TRADE_DISABLED:    return "TRADE_DISABLED";
      case TRADE_RETCODE_MARKET_CLOSED:     return "MARKET_CLOSED";
      case TRADE_RETCODE_NO_MONEY:          return "NO_MONEY";
      case TRADE_RETCODE_PRICE_CHANGED:     return "PRICE_CHANGED";
      case TRADE_RETCODE_PRICE_OFF:         return "PRICE_OFF";
      case TRADE_RETCODE_INVALID_EXPIRATION: return "INVALID_EXPIRATION";
      case TRADE_RETCODE_ORDER_CHANGED:     return "ORDER_CHANGED";
      case TRADE_RETCODE_TOO_MANY_REQUESTS: return "TOO_MANY_REQUESTS";
      case TRADE_RETCODE_NO_CHANGES:        return "NO_CHANGES";
      case TRADE_RETCODE_SERVER_DISABLES_AT: return "SERVER_DISABLES_AT";
      case TRADE_RETCODE_CLIENT_DISABLES_AT: return "CLIENT_DISABLES_AT";
      case TRADE_RETCODE_LOCKED:            return "LOCKED";
      case TRADE_RETCODE_FROZEN:            return "FROZEN";
      case TRADE_RETCODE_INVALID_FILL:      return "INVALID_FILL";
      case TRADE_RETCODE_CONNECTION:        return "CONNECTION";
      case TRADE_RETCODE_ONLY_REAL:         return "ONLY_REAL";
      case TRADE_RETCODE_LIMIT_ORDERS:      return "LIMIT_ORDERS";
      case TRADE_RETCODE_LIMIT_VOLUME:      return "LIMIT_VOLUME";
      case TRADE_RETCODE_INVALID_ORDER:     return "INVALID_ORDER";
      case TRADE_RETCODE_POSITION_CLOSED:   return "POSITION_CLOSED";
      default: return StringFormat("CODE_%u", retcode);
     }
  }

//+------------------------------------------------------------------+
void ProbeAppend(string &buf, const string line)
  {
   Print(line);
   buf += line + "\r\n";
  }

//+------------------------------------------------------------------+
bool ProbeEnsureSelected(const string symbol)
  {
   if(SymbolInfoInteger(symbol, SYMBOL_SELECT))
      return true;
   ResetLastError();
   if(!SymbolSelect(symbol, true))
     {
      Print("SymbolSelect failed: ", symbol, " err=", GetLastError());
      return false;
     }
   return true;
  }

//+------------------------------------------------------------------+
void ProbeSplitSymbols(const string csv, string &out[], const string fallback)
  {
   string tmp = csv;
   StringReplace(tmp, " ", "");
   const int n = StringSplit(tmp, ',', out);
   if(n <= 0)
     {
      ArrayResize(out, 1);
      out[0] = fallback;
     }
  }

//+------------------------------------------------------------------+
//| Session time-of-day from SymbolInfoSession* from/to datetimes.   |
//| MT5 stores a reference date on from/to; only hour/min/sec matter.|
//| Never compare raw datetime seconds — reference days can differ for |
//| overnight sessions (e.g. from=1970.01.01 21:00, to=1970.01.02 08:00).|
//+------------------------------------------------------------------+
int ProbeTimeOfDaySeconds(const datetime t)
  {
   MqlDateTime dt;
   TimeToStruct(t, dt);
   return dt.hour * 3600 + dt.min * 60 + dt.sec;
  }

//+------------------------------------------------------------------+
bool ProbeIsSessionSlotPlaceholder(const datetime from, const datetime to)
  {
   return (ProbeTimeOfDaySeconds(from) == 0 && ProbeTimeOfDaySeconds(to) == 0);
  }

//+------------------------------------------------------------------+
bool ProbeIsSessionSlotActive(const datetime now, const datetime from, const datetime to)
  {
   const ulong day_secs = 86400;
   const ulong now_tod = (ulong)now % day_secs;
   const ulong from_tod = (ulong)ProbeTimeOfDaySeconds(from);
   const ulong to_tod = (ulong)ProbeTimeOfDaySeconds(to);

   if(from_tod == 0 && to_tod == 0)
      return false;

   // Broker pattern: 01:00-00:00 = from start through end of calendar day.
   if(from_tod > 0 && to_tod == 0)
      return (now_tod >= from_tod);

   const bool cross_midnight =
      ((ulong)from / day_secs != (ulong)to / day_secs) || (from_tod > to_tod);

   if(!cross_midnight)
      return (now_tod >= from_tod && now_tod <= to_tod);

   return (now_tod >= from_tod || now_tod <= to_tod);
  }

//+------------------------------------------------------------------+
bool ProbeCheckSessionsForDay(const string symbol,
                              const ENUM_DAY_OF_WEEK day,
                              const bool trade_sessions,
                              bool &had_informative_slot,
                              bool &open_now)
  {
   had_informative_slot = false;
   open_now = false;

   const datetime now = TimeCurrent();
   datetime from = 0, to = 0;

   for(int s = 0;
       (trade_sessions
           ? SymbolInfoSessionTrade(symbol, day, s, from, to)
           : SymbolInfoSessionQuote(symbol, day, s, from, to));
       s++)
     {
      if(ProbeIsSessionSlotPlaceholder(from, to))
         continue;

      had_informative_slot = true;
      if(ProbeIsSessionSlotActive(now, from, to))
         open_now = true;
     }

   return had_informative_slot;
  }

//+------------------------------------------------------------------+
bool ProbeInferSessionOpenFromQuotes(const string symbol)
  {
   const long mode = SymbolInfoInteger(symbol, SYMBOL_TRADE_MODE);
   if(mode == SYMBOL_TRADE_MODE_DISABLED)
      return false;

   const double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
   const double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
   if(bid <= 0.0 || ask <= 0.0 || ask < bid)
      return false;

   const datetime sym_time = (datetime)SymbolInfoInteger(symbol, SYMBOL_TIME);
   if(sym_time > 0 && (TimeCurrent() - sym_time) > 300)
      return false;

   return true;
  }

//+------------------------------------------------------------------+
bool ProbeIsTradeSessionOpen(const string symbol)
  {
   if(!ProbeEnsureSelected(symbol))
      return false;

   MqlDateTime now_dt;
   TimeToStruct(TimeCurrent(), now_dt);
   const ENUM_DAY_OF_WEEK day = (ENUM_DAY_OF_WEEK)now_dt.day_of_week;

   bool trade_informative = false, trade_open = false;
   ProbeCheckSessionsForDay(symbol, day, true, trade_informative, trade_open);
   if(trade_open)
      return true;
   if(trade_informative)
      return false;

   bool quote_informative = false, quote_open = false;
   ProbeCheckSessionsForDay(symbol, day, false, quote_informative, quote_open);
   if(quote_open)
      return true;
   if(quote_informative)
      return false;

   // XP/B3 often publishes Q/T[00:00-00:00] placeholders — infer from live quotes.
   return ProbeInferSessionOpenFromQuotes(symbol);
  }

//+------------------------------------------------------------------+
void ProbeDumpAccountCapabilities(string &buf, const bool xp_profile)
  {
   ProbeAppend(buf, "");
   ProbeAppend(buf, "========== ACCOUNT CAPABILITIES ==========");
   ProbeAppend(buf, "--- AccountInfoInteger ---");

   const long margin_mode = AccountInfoInteger(ACCOUNT_MARGIN_MODE);
   ProbeAppend(buf, StringFormat("ACCOUNT_MARGIN_MODE=%d (%s)  <-- netting=0 exchange=1 hedging=2",
                                 (int)margin_mode, ProbeMarginModeName(margin_mode)));
   ProbeAppend(buf, StringFormat("ACCOUNT_TRADE_MODE=%d (%s)",
                                 (int)AccountInfoInteger(ACCOUNT_TRADE_MODE),
                                 ProbeAccountTradeModeName(AccountInfoInteger(ACCOUNT_TRADE_MODE))));
   ProbeAppend(buf, StringFormat("ACCOUNT_TRADE_ALLOWED=%d", (int)AccountInfoInteger(ACCOUNT_TRADE_ALLOWED)));
   ProbeAppend(buf, StringFormat("ACCOUNT_TRADE_EXPERT=%d", (int)AccountInfoInteger(ACCOUNT_TRADE_EXPERT)));
   ProbeAppend(buf, StringFormat("ACCOUNT_LEVERAGE=%d", (int)AccountInfoInteger(ACCOUNT_LEVERAGE)));
   ProbeAppend(buf, StringFormat("ACCOUNT_LIMIT_ORDERS=%d", (int)AccountInfoInteger(ACCOUNT_LIMIT_ORDERS)));
   ProbeAppend(buf, StringFormat("ACCOUNT_MARGIN_SO_MODE=%d", (int)AccountInfoInteger(ACCOUNT_MARGIN_SO_MODE)));

   ProbeAppend(buf, "--- AccountInfoDouble ---");
   ProbeAppend(buf, StringFormat("ACCOUNT_BALANCE=%.2f", AccountInfoDouble(ACCOUNT_BALANCE)));
   ProbeAppend(buf, StringFormat("ACCOUNT_EQUITY=%.2f", AccountInfoDouble(ACCOUNT_EQUITY)));
   ProbeAppend(buf, StringFormat("ACCOUNT_MARGIN_FREE=%.2f", AccountInfoDouble(ACCOUNT_MARGIN_FREE)));

   ProbeAppend(buf, "--- AccountInfoString ---");
   ProbeAppend(buf, StringFormat("ACCOUNT_NAME=%s", AccountInfoString(ACCOUNT_NAME)));
   ProbeAppend(buf, StringFormat("ACCOUNT_CURRENCY=%s", AccountInfoString(ACCOUNT_CURRENCY)));
   ProbeAppend(buf, StringFormat("ACCOUNT_SERVER=%s", AccountInfoString(ACCOUNT_SERVER)));
   ProbeAppend(buf, StringFormat("ACCOUNT_COMPANY=%s", AccountInfoString(ACCOUNT_COMPANY)));

   ProbeAppend(buf, "--- TerminalInfo ---");
   ProbeAppend(buf, StringFormat("TERMINAL_CONNECTED=%d", (int)TerminalInfoInteger(TERMINAL_CONNECTED)));
   ProbeAppend(buf, StringFormat("TERMINAL_TRADE_ALLOWED=%d", (int)TerminalInfoInteger(TERMINAL_TRADE_ALLOWED)));
   ProbeAppend(buf, StringFormat("TERMINAL_BUILD=%d", (int)TerminalInfoInteger(TERMINAL_BUILD)));
   ProbeAppend(buf, "Note: symbol session hours below use SERVER TIME (not UTC/BRT).");
   if(xp_profile)
      ProbeAppend(buf, "B3: server time is often UTC-3 (BRT) — confirm against exchange calendar.");
  }

//+------------------------------------------------------------------+
void ProbeDumpSymbolSessions(const string symbol, string &buf)
  {
   ProbeAppend(buf, "--- Symbol sessions (Quote=Q / Trade=T) ---");

   if(!ProbeEnsureSelected(symbol))
     {
      ProbeAppend(buf, "RESULT: symbol not selected — sessions unavailable");
      return;
     }

   datetime from = 0, to = 0;
   for(int d = SUNDAY; d <= SATURDAY; d++)
     {
      string line = ProbeDayName((ENUM_DAY_OF_WEEK)d) + ": ";
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
      ProbeAppend(buf, line);
     }

   ProbeAppend(buf, StringFormat("Trade session OPEN now: %s",
                                 ProbeIsTradeSessionOpen(symbol) ? "YES" : "NO"));
  }

//+------------------------------------------------------------------+
void ProbeDumpSymbolContractDates(const string symbol, string &buf)
  {
   ProbeAppend(buf, "--- Contract lifecycle (B3 futures / listed) ---");

   const datetime start = (datetime)SymbolInfoInteger(symbol, SYMBOL_START_TIME);
   const datetime expiry = (datetime)SymbolInfoInteger(symbol, SYMBOL_EXPIRATION_TIME);
   ProbeAppend(buf, StringFormat("SYMBOL_START_TIME=%s", TimeToString(start, TIME_DATE | TIME_SECONDS)));
   ProbeAppend(buf, StringFormat("SYMBOL_EXPIRATION_TIME=%s", TimeToString(expiry, TIME_DATE | TIME_SECONDS)));
   ProbeAppend(buf, StringFormat("SYMBOL_EXPIRATION_MODE=%d", (int)SymbolInfoInteger(symbol, SYMBOL_EXPIRATION_MODE)));

   if(start == 0 && expiry == 0)
      ProbeAppend(buf, "Note: zero dates — common for spot equities; check path/description for futures rollover.");
  }

//+------------------------------------------------------------------+
void ProbeDumpSymbolInfo(const string symbol, string &buf, const bool xp_profile)
  {
   ProbeAppend(buf, "");
   ProbeAppend(buf, "========== SYMBOL: " + symbol + " ==========");

   if(!ProbeEnsureSelected(symbol))
     {
      ProbeAppend(buf, "RESULT: symbol not available on this account/server");
      if(xp_profile)
         ProbeAppend(buf, "Hint: open Market Watch on XP, copy exact symbol name (e.g. WINJ25, WDOQ25).");
      return;
     }

   if(!SymbolInfoInteger(symbol, SYMBOL_EXIST))
     {
      ProbeAppend(buf, "RESULT: SYMBOL_EXIST=false");
      return;
     }

   ProbeAppend(buf, "--- SymbolInfoInteger ---");
   ProbeAppend(buf, StringFormat("SYMBOL_EXIST=%d", (int)SymbolInfoInteger(symbol, SYMBOL_EXIST)));
   ProbeAppend(buf, StringFormat("SYMBOL_SELECT=%d", (int)SymbolInfoInteger(symbol, SYMBOL_SELECT)));
   ProbeAppend(buf, StringFormat("SYMBOL_VISIBLE=%d", (int)SymbolInfoInteger(symbol, SYMBOL_VISIBLE)));
   ProbeAppend(buf, StringFormat("SYMBOL_CUSTOM=%d", (int)SymbolInfoInteger(symbol, SYMBOL_CUSTOM)));
   ProbeAppend(buf, StringFormat("SYMBOL_DIGITS=%d", (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS)));
   ProbeAppend(buf, StringFormat("SYMBOL_SPREAD=%d", (int)SymbolInfoInteger(symbol, SYMBOL_SPREAD)));
   ProbeAppend(buf, StringFormat("SYMBOL_SPREAD_FLOAT=%d", (int)SymbolInfoInteger(symbol, SYMBOL_SPREAD_FLOAT)));
   ProbeAppend(buf, StringFormat("SYMBOL_TICKS_BOOKDEPTH=%d  <-- 0 means no DOM",
                                 (int)SymbolInfoInteger(symbol, SYMBOL_TICKS_BOOKDEPTH)));
   ProbeAppend(buf, StringFormat("SYMBOL_TRADE_CALC_MODE=%d (%s)",
                                 (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_CALC_MODE),
                                 ProbeTradeCalcModeName(SymbolInfoInteger(symbol, SYMBOL_TRADE_CALC_MODE))));
   ProbeAppend(buf, StringFormat("SYMBOL_TRADE_MODE=%d (%s)",
                                 (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_MODE),
                                 ProbeTradeModeName(SymbolInfoInteger(symbol, SYMBOL_TRADE_MODE))));
   ProbeAppend(buf, StringFormat("SYMBOL_TRADE_EXEMODE=%d", (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_EXEMODE)));
   const int fill = (int)SymbolInfoInteger(symbol, SYMBOL_FILLING_MODE);
   ProbeAppend(buf, StringFormat("SYMBOL_FILLING_MODE=%d", fill));
   string fill_dec = "";
   // Bitmask: 1=FOK, 2=IOC, 4=RETURN — distinct from ORDER_FILLING_* enum values.
   if((fill & 1) != 0) fill_dec += "FOK ";
   if((fill & 2) != 0) fill_dec += "IOC ";
   if((fill & 4) != 0) fill_dec += "RETURN ";
   if(StringLen(fill_dec) == 0) fill_dec = "none ";
   ProbeAppend(buf, StringFormat("SYMBOL_FILLING_MODE decode: %s(bitmask=%d)", fill_dec, fill));
   ProbeAppend(buf, StringFormat("SYMBOL_ORDER_MODE=%d", (int)SymbolInfoInteger(symbol, SYMBOL_ORDER_MODE)));
   ProbeAppend(buf, StringFormat("SYMBOL_ORDER_GTC_MODE=%d", (int)SymbolInfoInteger(symbol, SYMBOL_ORDER_GTC_MODE)));
   ProbeAppend(buf, StringFormat("SYMBOL_SWAP_MODE=%d", (int)SymbolInfoInteger(symbol, SYMBOL_SWAP_MODE)));
   ProbeAppend(buf, StringFormat("SYMBOL_TRADE_STOPS_LEVEL=%d", (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_STOPS_LEVEL)));
   ProbeAppend(buf, StringFormat("SYMBOL_TRADE_FREEZE_LEVEL=%d", (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_FREEZE_LEVEL)));
   ProbeAppend(buf, StringFormat("SYMBOL_TIME=%s",
                                 TimeToString((datetime)SymbolInfoInteger(symbol, SYMBOL_TIME),
                                              TIME_DATE | TIME_SECONDS)));

   if(xp_profile)
      ProbeDumpSymbolContractDates(symbol, buf);

   ProbeAppend(buf, "--- SymbolInfoDouble ---");
   ProbeAppend(buf, StringFormat("SYMBOL_BID=%.10f", SymbolInfoDouble(symbol, SYMBOL_BID)));
   ProbeAppend(buf, StringFormat("SYMBOL_ASK=%.10f", SymbolInfoDouble(symbol, SYMBOL_ASK)));
   ProbeAppend(buf, StringFormat("SYMBOL_LAST=%.10f", SymbolInfoDouble(symbol, SYMBOL_LAST)));
   ProbeAppend(buf, StringFormat("SYMBOL_POINT=%.10f", SymbolInfoDouble(symbol, SYMBOL_POINT)));
   ProbeAppend(buf, StringFormat("SYMBOL_TRADE_TICK_SIZE=%.10f", SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_SIZE)));
   ProbeAppend(buf, StringFormat("SYMBOL_TRADE_TICK_VALUE=%.10f", SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_VALUE)));
   ProbeAppend(buf, StringFormat("SYMBOL_TRADE_CONTRACT_SIZE=%.2f", SymbolInfoDouble(symbol, SYMBOL_TRADE_CONTRACT_SIZE)));
   ProbeAppend(buf, StringFormat("SYMBOL_VOLUME_MIN=%.4f", SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN)));
   ProbeAppend(buf, StringFormat("SYMBOL_VOLUME_MAX=%.4f", SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX)));
   ProbeAppend(buf, StringFormat("SYMBOL_VOLUME_STEP=%.4f", SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP)));
   ProbeAppend(buf, StringFormat("SYMBOL_VOLUME_LIMIT=%.4f", SymbolInfoDouble(symbol, SYMBOL_VOLUME_LIMIT)));

   ProbeAppend(buf, "--- SymbolInfoString ---");
   ProbeAppend(buf, StringFormat("SYMBOL_CURRENCY_BASE=%s", SymbolInfoString(symbol, SYMBOL_CURRENCY_BASE)));
   ProbeAppend(buf, StringFormat("SYMBOL_CURRENCY_PROFIT=%s", SymbolInfoString(symbol, SYMBOL_CURRENCY_PROFIT)));
   ProbeAppend(buf, StringFormat("SYMBOL_CURRENCY_MARGIN=%s", SymbolInfoString(symbol, SYMBOL_CURRENCY_MARGIN)));
   ProbeAppend(buf, StringFormat("SYMBOL_DESCRIPTION=%s", SymbolInfoString(symbol, SYMBOL_DESCRIPTION)));
   ProbeAppend(buf, StringFormat("SYMBOL_PATH=%s", SymbolInfoString(symbol, SYMBOL_PATH)));
   ProbeAppend(buf, StringFormat("SYMBOL_BASIS=%s", SymbolInfoString(symbol, SYMBOL_BASIS)));
   ProbeAppend(buf, StringFormat("SYMBOL_ISIN=%s", SymbolInfoString(symbol, SYMBOL_ISIN)));
   if(xp_profile)
     {
      ProbeAppend(buf, StringFormat("SYMBOL_SECTOR=%d", (int)SymbolInfoInteger(symbol, SYMBOL_SECTOR)));
      ProbeAppend(buf, StringFormat("SYMBOL_SECTOR_NAME=%s", SymbolInfoString(symbol, SYMBOL_SECTOR_NAME)));
      ProbeAppend(buf, StringFormat("SYMBOL_COUNTRY=%s", SymbolInfoString(symbol, SYMBOL_COUNTRY)));
     }
  }

//+------------------------------------------------------------------+
void ProbeMarketBook(const string symbol, string &buf)
  {
   ProbeAppend(buf, "--- MarketBookAdd / MarketBookGet ---");

   const int bookdepth = (int)SymbolInfoInteger(symbol, SYMBOL_TICKS_BOOKDEPTH);
   ResetLastError();
   const bool added = MarketBookAdd(symbol);
   const int err_add = GetLastError();

   ProbeAppend(buf, StringFormat("MarketBookAdd(%s) => %s  err=%d  ticks_bookdepth=%d",
                                 symbol, added ? "TRUE" : "FALSE", err_add, bookdepth));

   if(!added)
     {
      ProbeAppend(buf, "DOM verdict: NOT AVAILABLE (subscription failed)");
      return;
     }

   MqlBookInfo book[];
   ResetLastError();
   const bool got = MarketBookGet(symbol, book);
   const int err_get = GetLastError();
   const int n = got ? ArraySize(book) : 0;

   ProbeAppend(buf, StringFormat("MarketBookGet(%s) => %s  levels=%d  err=%d",
                                 symbol, got ? "TRUE" : "FALSE", n, err_get));

   const int show = MathMin(n, 10);
   for(int i = 0; i < show; i++)
      ProbeAppend(buf, StringFormat("  [%d] type=%s price=%.10f volume=%.4f",
                                    i,
                                    ProbeBookTypeName(book[i].type),
                                    book[i].price,
                                    (double)book[i].volume));

   if(n == 0)
      ProbeAppend(buf, "DOM verdict: subscription OK but book EMPTY (broker may not publish depth)");
   else
      ProbeAppend(buf, StringFormat("DOM verdict: AVAILABLE (%d levels at snapshot)", n));

   if(!MarketBookRelease(symbol))
      ProbeAppend(buf, StringFormat("MarketBookRelease failed err=%d", GetLastError()));
  }

//+------------------------------------------------------------------+
void ProbeTickFlags(const string symbol, const int count, string &buf, const bool xp_profile)
  {
   if(count <= 0)
      return;

   ProbeAppend(buf, "--- CopyTicks sample (recent) ---");

   MqlTick ticks[];
   ResetLastError();
   const int copied = CopyTicks(symbol, ticks, COPY_TICKS_ALL, 0, count);
   ProbeAppend(buf, StringFormat("CopyTicks copied=%d  err=%d", copied, GetLastError()));

   if(copied <= 0)
     {
      if(xp_profile)
         ProbeAppend(buf, "Tick verdict: NO SAMPLES (market closed or no history — re-run during B3 session)");
      return;
     }

   int bid_only = 0, ask_only = 0, last_flag = 0, vol_flag = 0, both_ba = 0;
   for(int i = 0; i < copied; i++)
     {
      const uint f = ticks[i].flags;
      if((f & TICK_FLAG_BID) != 0 && (f & TICK_FLAG_ASK) == 0) bid_only++;
      if((f & TICK_FLAG_ASK) != 0 && (f & TICK_FLAG_BID) == 0) ask_only++;
      if((f & TICK_FLAG_BID) != 0 && (f & TICK_FLAG_ASK) != 0) both_ba++;
      if((f & TICK_FLAG_LAST) != 0) last_flag++;
      if((f & TICK_FLAG_VOLUME) != 0) vol_flag++;

      if(i < MathMin(copied, 5))
         ProbeAppend(buf, StringFormat("  tick[%d] time_msc=%I64d bid=%.5f ask=%.5f last=%.5f vol=%I64u flags=%u",
                                      i,
                                      ticks[i].time_msc,
                                      ticks[i].bid, ticks[i].ask, ticks[i].last,
                                      ticks[i].volume, f));
     }

   ProbeAppend(buf, StringFormat("flags summary: bid+ask=%d bid_only=%d ask_only=%d last=%d volume=%d (of %d)",
                                 both_ba, bid_only, ask_only, last_flag, vol_flag, copied));
   ProbeAppend(buf, "Note: MT5 UI export flags often differ by 128 from API tick flags.");

   if(xp_profile)
     {
      if(last_flag > 0 || vol_flag > 0)
         ProbeAppend(buf, "Adapter hint: TradeTick may be viable — confirm SYMBOL_LAST and TICK_FLAG_LAST.");
      else
         ProbeAppend(buf, "Adapter hint: QuoteTick-only sample — compare with SYMBOL_LAST field above.");
     }
  }

//+------------------------------------------------------------------+
void ProbeSymbolInfoTick(const string symbol, string &buf)
  {
   ProbeAppend(buf, "--- SymbolInfoTick (live snapshot) ---");

   MqlTick tick;
   ResetLastError();
   if(!SymbolInfoTick(symbol, tick))
     {
      ProbeAppend(buf, StringFormat("SymbolInfoTick failed err=%d", GetLastError()));
      return;
     }

   ProbeAppend(buf, StringFormat("time_msc=%I64d bid=%.10f ask=%.10f last=%.10f vol=%I64u flags=%u",
                                 tick.time_msc, tick.bid, tick.ask, tick.last, tick.volume, tick.flags));
  }

//+------------------------------------------------------------------+
void ProbeOrderCheckMarket(const string symbol,
                           const ENUM_ORDER_TYPE order_type,
                           const ENUM_ORDER_TYPE_FILLING filling,
                           string &buf)
  {
   MqlTradeRequest request;
   MqlTradeCheckResult check;
   ZeroMemory(request);
   ZeroMemory(check);

   const double vol_min = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   const double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
   const double bid = SymbolInfoDouble(symbol, SYMBOL_BID);

   request.action = TRADE_ACTION_DEAL;
   request.symbol = symbol;
   request.volume = vol_min;
   request.type = order_type;
   request.price = (order_type == ORDER_TYPE_BUY) ? ask : bid;
   request.deviation = 20;
   request.type_filling = filling;
   request.type_time = ORDER_TIME_GTC;
   request.magic = PROBE_MAGIC;
   request.comment = "nt_mt5_probe";

   ResetLastError();
   const bool ok = OrderCheck(request, check);
   const int err = GetLastError();

   ProbeAppend(buf, StringFormat("OrderCheck %s %s vol=%.4f price=%.10f => check=%s retcode=%u (%s) comment=%s err=%d",
                                 (order_type == ORDER_TYPE_BUY) ? "BUY" : "SELL",
                                 ProbeFillingEnumName(filling),
                                 vol_min,
                                 request.price,
                                 ok ? "OK" : "FAIL",
                                 check.retcode,
                                 ProbeRetcodeName(check.retcode),
                                 check.comment,
                                 err));
  }

//+------------------------------------------------------------------+
void ProbeFillingModes(const string symbol, string &buf)
  {
   ProbeAppend(buf, "--- OrderCheck filling probe (market deal, no OrderSend) ---");
   ProbeAppend(buf, "Declared SYMBOL_FILLING_MODE bitmask vs broker acceptance at OrderCheck time.");

   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))
     {
      ProbeAppend(buf, "SKIP: TERMINAL_TRADE_ALLOWED=0");
      return;
     }
   if(!AccountInfoInteger(ACCOUNT_TRADE_ALLOWED))
     {
      ProbeAppend(buf, "SKIP: ACCOUNT_TRADE_ALLOWED=0");
      return;
     }
   if(!ProbeIsTradeSessionOpen(symbol))
     {
      ProbeAppend(buf, "SKIP: trade session closed for this symbol right now");
      return;
     }

   // Unrolled — avoids const enum-array init quirks across MT5 builds.
   ProbeOrderCheckMarket(symbol, ORDER_TYPE_BUY, ORDER_FILLING_FOK, buf);
   ProbeOrderCheckMarket(symbol, ORDER_TYPE_SELL, ORDER_FILLING_FOK, buf);
   ProbeOrderCheckMarket(symbol, ORDER_TYPE_BUY, ORDER_FILLING_IOC, buf);
   ProbeOrderCheckMarket(symbol, ORDER_TYPE_SELL, ORDER_FILLING_IOC, buf);
   ProbeOrderCheckMarket(symbol, ORDER_TYPE_BUY, ORDER_FILLING_RETURN, buf);
   ProbeOrderCheckMarket(symbol, ORDER_TYPE_SELL, ORDER_FILLING_RETURN, buf);
  }

//+------------------------------------------------------------------+
void ProbeWriteReport(const string file_prefix, const string report)
  {
   const string fname = StringFormat("%s_%s_%I64u.txt",
                                     file_prefix,
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

//+------------------------------------------------------------------+
void RunMarketOffHoursProbe(const string broker_label,
                            const string symbols_csv,
                            const bool write_file,
                            const int tick_sample,
                            const bool xp_profile,
                            const string fallback_symbol,
                            const string file_prefix)
  {
   string report = "";
   ProbeAppend(report, "===== ProbeBroker market_off_hours: " + broker_label + " =====");
   ProbeAppend(report, ProbeServerTag());
   ProbeAppend(report, "Mode: read-only (SymbolInfo*, sessions, DOM). No OrderSend/OrderCheck.");
   ProbeDumpAccountCapabilities(report, xp_profile);

   string symbols[];
   ProbeSplitSymbols(symbols_csv, symbols, fallback_symbol);

   for(int i = 0; i < ArraySize(symbols); i++)
     {
      const string sym = symbols[i];
      if(StringLen(sym) == 0)
         continue;

      ProbeDumpSymbolInfo(sym, report, xp_profile);
      ProbeDumpSymbolSessions(sym, report);
      ProbeMarketBook(sym, report);
      ProbeTickFlags(sym, tick_sample, report, xp_profile);
     }

   ProbeAppend(report, "===== END =====");

   if(write_file)
      ProbeWriteReport(file_prefix, report);
  }

//+------------------------------------------------------------------+
void RunMarketLiveProbe(const string broker_label,
                        const string symbols_csv,
                        const bool write_file,
                        const int tick_sample,
                        const bool xp_profile,
                        const string fallback_symbol,
                        const string file_prefix,
                        const bool skip_if_session_closed)
  {
   string report = "";
   ProbeAppend(report, "===== ProbeBroker market_live: " + broker_label + " =====");
   ProbeAppend(report, ProbeServerTag());
   ProbeAppend(report, "Mode: live session — SymbolInfoTick, CopyTicks, OrderCheck (no OrderSend).");
   ProbeDumpAccountCapabilities(report, xp_profile);

   string symbols[];
   ProbeSplitSymbols(symbols_csv, symbols, fallback_symbol);

   for(int i = 0; i < ArraySize(symbols); i++)
     {
      const string sym = symbols[i];
      if(StringLen(sym) == 0)
         continue;

      if(skip_if_session_closed && !ProbeIsTradeSessionOpen(sym))
        {
         ProbeAppend(report, "");
         ProbeAppend(report, "========== SYMBOL: " + sym + " ==========");
         ProbeAppend(report, "SKIP: trade session closed — run during market hours.");
         continue;
        }

      ProbeDumpSymbolInfo(sym, report, xp_profile);
      ProbeDumpSymbolSessions(sym, report);
      ProbeSymbolInfoTick(sym, report);
      ProbeTickFlags(sym, tick_sample, report, xp_profile);
      ProbeFillingModes(sym, report);
     }

   ProbeAppend(report, "===== END =====");

   if(write_file)
      ProbeWriteReport(file_prefix, report);
  }

#endif // PROBE_BROKER_MQH
//+------------------------------------------------------------------+
