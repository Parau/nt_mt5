"""RPyC MT5 bridge v0.7 — staging copy for manual deploy.

Adds ``exposed_orders_get`` (MT5 ``orders_get``) required by homologation E07
and ``generate_order_status_reports`` on EXTERNAL_RPYC.

Deploy: copy to production path (e.g. ``E:\\dev\\TradingUltimate\\mt5_bridge.py``)
and restart the bridge process on port 18812.
"""
import rpyc
import MetaTrader5 as mt5

class MT5Service(rpyc.Service):
    
    # Esta linha vai resolver o problema do 'getmodule' e o timeout!
    exposed_getmodule = None

    def _is_mt5_ready(self) -> bool:
        try:
            info = mt5.terminal_info()
            return info is not None and getattr(info, "connected", False)
        except Exception:
            return False

    def exposed_initialize(self, *args, **kwargs):
        print(f"[DEBUG] initialize | args={args} kwargs={kwargs}")
        if self._is_mt5_ready():
            print("[DEBUG] initialize | already connected, returning True")
            return True
        result = mt5.initialize(*args, **kwargs)
        print(f"[DEBUG] initialize | return={result}")
        return result

    def exposed_login(self, login, password, server):
        print(f"[DEBUG] login | login={login} password=*** server={server}")
        result = mt5.login(login, password, server)
        print(f"[DEBUG] login | return={result}")
        return result

    def exposed_last_error(self):
        print(f"[DEBUG] last_error | (no params)")
        result = mt5.last_error()
        print(f"[DEBUG] last_error | return={result}")
        return result

    def exposed_version(self):
        print(f"[DEBUG] version | (no params)")
        result = mt5.version()
        print(f"[DEBUG] version | return={result}")
        return result
        
    def exposed_terminal_info(self):
        print(f"[DEBUG] terminal_info | (no params)")
        result = mt5.terminal_info()
        print(f"[DEBUG] terminal_info | return={result}")
        return result

    def exposed_account_info(self):
        print(f"[DEBUG] account_info | (no params)")
        result = mt5.account_info()
        print(f"[DEBUG] account_info | return={result}")
        return result

    def exposed_symbols_get(self, *args, **kwargs):
        print(f"[DEBUG] symbols_get | args={args} kwargs={kwargs}")
        result = mt5.symbols_get(*args, **kwargs)
        print(f"[DEBUG] symbols_get | return count={len(result) if result is not None else None}")
        return result

    def exposed_symbol_info(self, symbol):
        print(f"[DEBUG] symbol_info | symbol={symbol}")
        result = mt5.symbol_info(symbol)
        print(f"[DEBUG] symbol_info | return={result}")
        return result
        
    def exposed_symbol_info_tick(self, symbol):
        print(f"[DEBUG] symbol_info_tick | symbol={symbol}")
        result = mt5.symbol_info_tick(symbol)
        print(f"[DEBUG] symbol_info_tick | return={result}")
        return result
        
    def exposed_symbol_select(self, symbol, enable):
        print(f"[DEBUG] symbol_select | symbol={symbol} enable={enable}")
        result = mt5.symbol_select(symbol, enable)
        print(f"[DEBUG] symbol_select | return={result}")
        return result

    def exposed_copy_rates_from_pos(self, symbol, timeframe, start_pos, count):
        print(f"[DEBUG] copy_rates_from_pos | symbol={symbol} timeframe={timeframe} start_pos={start_pos} count={count}")
        result = mt5.copy_rates_from_pos(symbol, timeframe, start_pos, count)
        print(f"[DEBUG] copy_rates_from_pos | return count={len(result) if result is not None else None}")
        return result
        
    def exposed_copy_ticks_range(self, symbol, date_from, date_to, flags):
        print(f"[DEBUG] copy_ticks_range | symbol={symbol} date_from={date_from} date_to={date_to} flags={flags}")
        result = mt5.copy_ticks_range(symbol, date_from, date_to, flags)
        print(f"[DEBUG] copy_ticks_range | return count={len(result) if result is not None else None}")
        return result
        
    def exposed_copy_ticks_from(self, symbol, date_from, count, flags):
        print(f"[DEBUG] copy_ticks_from | symbol={symbol} date_from={date_from} count={count} flags={flags}")
        result = mt5.copy_ticks_from(symbol, date_from, count, flags)
        print(f"[DEBUG] copy_ticks_from | return count={len(result) if result is not None else None}")
        return result

    def exposed_order_send(self, request):
        print(f"[DEBUG] order_send | request={dict(request)}")
        result = mt5.order_send(dict(request))
        print(f"[DEBUG] order_send | return={result}")
        return result
        
    def exposed_positions_get(self, *args, **kwargs):
        print(f"[DEBUG] positions_get | args={args} kwargs={kwargs}")
        result = mt5.positions_get(*args, **kwargs)
        print(f"[DEBUG] positions_get | return count={len(result) if result is not None else None}")
        return result

    def exposed_orders_get(self, *args, **kwargs):
        print(f"[DEBUG] orders_get | args={args} kwargs={kwargs}")
        result = mt5.orders_get(*args, **kwargs)
        print(f"[DEBUG] orders_get | return count={len(result) if result is not None else None}")
        return result
        
    def exposed_history_orders_total(self, *args, **kwargs):
        print(f"[DEBUG] history_orders_total | args={args} kwargs={kwargs}")
        result = mt5.history_orders_total(*args, **kwargs)
        print(f"[DEBUG] history_orders_total | return={result}")
        return result
        
    def exposed_history_orders_get(self, *args, **kwargs):
        print(f"[DEBUG] history_orders_get | args={args} kwargs={kwargs}")
        result = mt5.history_orders_get(*args, **kwargs)
        print(f"[DEBUG] history_orders_get | return count={len(result) if result is not None else None}")
        return result

    def exposed_history_deals_total(self, *args, **kwargs):
        print(f"[DEBUG] history_deals_total | args={args} kwargs={kwargs}")
        result = mt5.history_deals_total(*args, **kwargs)
        print(f"[DEBUG] history_deals_total | return={result}")
        return result

    def exposed_history_deals_get(self, *args, **kwargs):
        print(f"[DEBUG] history_deals_get | args={args} kwargs={kwargs}")
        result = mt5.history_deals_get(*args, **kwargs)
        print(f"[DEBUG] history_deals_get | return count={len(result) if result is not None else None}")
        return result
        
    def exposed_shutdown(self):
        # Client disconnect must NOT tear down the shared terminal.
        print("[DEBUG] shutdown | no-op (shared gateway — MT5 stays alive)")
        return True

    def exposed_get_constant(self, name):
        print(f"[DEBUG] get_constant | name={name}")
        result = getattr(mt5, name)
        print(f"[DEBUG] get_constant | return={result}")
        return result

if __name__ == "__main__":
    from rpyc.utils.server import ThreadedServer
    
    if not mt5.initialize():
        print("initialize() failed, error code =", mt5.last_error())
        quit()
        
    print("MT5 initialized successfully. Starting RPyC server on port 18812...")
    print("Bridge V 0.7")
    server = ThreadedServer(
        MT5Service,
        port=18812,
        protocol_config={"allow_public_attrs": True, "allow_all_attrs": True},
    )
    try:
        server.start()
    finally:
        print("[INFO] Bridge stopping — calling mt5.shutdown()")
        mt5.shutdown()
