//+------------------------------------------------------------------+
//| NT5FeedWire.mqh — wire JSON helpers (Service ↔ adapter)          |
//| Protocol: res/especificacao_novo_adaptador_nautilus_mt5.md §9    |
//+------------------------------------------------------------------+
#ifndef NT5_FEED_WIRE_MQH
#define NT5_FEED_WIRE_MQH

//+------------------------------------------------------------------+
string NT5JsonEscape(const string value)
  {
   string out = value;
   StringReplace(out, "\\", "\\\\");
   StringReplace(out, "\"", "\\\"");
   return out;
  }

//+------------------------------------------------------------------+
string NT5TickToJson(const MqlTick &tick)
  {
   return StringFormat(
      "{\"time_msc\":%I64d,\"bid\":%.8f,\"ask\":%.8f,\"last\":%.8f,\"volume\":%I64d,\"flags\":%u}",
      tick.time_msc,
      tick.bid,
      tick.ask,
      tick.last,
      (long)tick.volume,
      tick.flags
   );
  }

//+------------------------------------------------------------------+
string NT5BuildHelloJson(
   const string session,
   string &symbols[]
)
  {
   string symbols_json = "[";
   const int count = ArraySize(symbols);
   for(int i = 0; i < count; i++)
     {
      if(i > 0)
         symbols_json += ",";
      symbols_json += StringFormat("\"%s\"", NT5JsonEscape(symbols[i]));
     }
   symbols_json += "]";

   return StringFormat(
      "{\"op\":\"hello\",\"session\":\"%s\",\"terminal\":\"%s\",\"account\":\"%I64d\",\"symbols\":%s}",
      NT5JsonEscape(session),
      NT5JsonEscape(TerminalInfoString(TERMINAL_NAME)),
      AccountInfoInteger(ACCOUNT_LOGIN),
      symbols_json
   );
  }

//+------------------------------------------------------------------+
string NT5BuildTicksJson(
   const string symbol,
   const long cursor,
   const MqlTick &ticks[],
   const int count
)
  {
   string data = "[";
   for(int i = 0; i < count; i++)
     {
      if(i > 0)
         data += ",";
      data += NT5TickToJson(ticks[i]);
     }
   data += "]";

   return StringFormat(
      "{\"op\":\"ticks\",\"symbol\":\"%s\",\"cursor\":%I64d,\"data\":%s}",
      NT5JsonEscape(symbol),
      cursor,
      data
   );
  }

//+------------------------------------------------------------------+
string NT5BuildHeartbeatJson()
  {
   // Wall-clock ms (MQL5 datetime is seconds; multiply for wire ts_msc field).
   return StringFormat("{\"op\":\"heartbeat\",\"ts_msc\":%I64d}", (long)((ulong)TimeGMT() * 1000));
  }

//+------------------------------------------------------------------+
string NT5BuildPongJson()
  {
   return "{\"op\":\"pong\"}";
  }

//+------------------------------------------------------------------+
string NT5BuildErrorJson(const string code, const string message)
  {
   return StringFormat(
      "{\"op\":\"error\",\"code\":\"%s\",\"message\":\"%s\"}",
      NT5JsonEscape(code),
      NT5JsonEscape(message)
   );
  }

//+------------------------------------------------------------------+
bool NT5ExtractJsonStringField(const string json, const string field, string &value)
  {
   value = "";
   const string needle = StringFormat("\"%s\"", field);
   int pos = StringFind(json, needle);
   if(pos < 0)
      return false;

   pos = StringFind(json, ":", pos);
   if(pos < 0)
      return false;

   pos = StringFind(json, "\"", pos + 1);
   if(pos < 0)
      return false;

   const int end = StringFind(json, "\"", pos + 1);
   if(end < 0)
      return false;

   value = StringSubstr(json, pos + 1, end - pos - 1);
   return true;
  }

//+------------------------------------------------------------------+
bool NT5ParseWireOp(const string json, string &op)
  {
   return NT5ExtractJsonStringField(json, "op", op);
  }

//+------------------------------------------------------------------+
void NT5SplitCsvSymbols(const string csv, string &out[])
  {
   ArrayResize(out, 0);
   if(StringLen(csv) == 0)
      return;

   string parts[];
   const int n = StringSplit(csv, ',', parts);
   for(int i = 0; i < n; i++)
     {
      StringTrimLeft(parts[i]);
      StringTrimRight(parts[i]);
      if(StringLen(parts[i]) == 0)
         continue;

      const int m = ArraySize(out);
      ArrayResize(out, m + 1);
      out[m] = parts[i];
     }
  }

//+------------------------------------------------------------------+
bool NT5ExtractJsonStringArray(const string json, const string field, string &out[])
  {
   ArrayResize(out, 0);
   const string needle = StringFormat("\"%s\"", field);
   int pos = StringFind(json, needle);
   if(pos < 0)
      return false;

   pos = StringFind(json, "[", pos);
   if(pos < 0)
      return false;

   const int end = StringFind(json, "]", pos);
   if(end < 0)
      return false;

   string inner = StringSubstr(json, pos + 1, end - pos - 1);
   StringReplace(inner, " ", "");
   if(StringLen(inner) == 0)
      return true;

   string parts[];
   const int n = StringSplit(inner, ',', parts);
   for(int i = 0; i < n; i++)
     {
      StringReplace(parts[i], "\"", "");
      if(StringLen(parts[i]) == 0)
         continue;

      const int m = ArraySize(out);
      ArrayResize(out, m + 1);
      out[m] = parts[i];
     }
   return true;
  }

#endif
