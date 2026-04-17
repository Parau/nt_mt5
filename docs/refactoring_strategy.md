# Refactoring Strategy: Nautilus MT5 Adapter

## Current State Analysis
The current codebase in `nautilus_mt5` has an architecture intended to support multiple connection modes (IPC natively on Windows, IPC via RPyC on Linux, and a custom EA using sockets).
The data provider (`nautilus_mt5/data.py`) and execution client (`nautilus_mt5/execution.py`) rely heavily on an internal `MetaTrader5Client` component (`nautilus_mt5/client/client.py`) which inherits from several mixins (`Connection`, `Account`, `Symbol`, `MarketData`, `Order`).
This internal client abstraction adds immense complexity, trying to wrap both `mt5` and `EAClient`.

## Our Goal
The objective is to simplify and robustify the `metatrader5` library integration (specifically the IPC approach, utilizing RPyC to bridge the sandbox to the Windows host).
Since the user requested to prioritize **Market Data** and **Execution** using **IPC no Windows** (and the RPyC bridge for testing), we should strip out or bypass the overly complex EA socket code and ensure the RPyC connection natively behaves as the `mt5` module.

## Strategy

1. **Fix connection strings/config:**
   - Modify the initialization so it relies entirely on the RPyC bridge. We will use the `TerminalConnectionMode.IPC` but force it to use `rpyc` because our tests run on Linux (Sandbox) targeting the Windows host via ngrok.
   - Specifically, we will adjust `nautilus_mt5/client/connection.py` or the configuration to use the `0.tcp.sa.ngrok.io:18526` URL natively.

2. **Refactor Market Data (`nautilus_mt5/data.py` & `nautilus_mt5/client/market_data.py`):**
   - Ensure that fetching historical ticks (`copy_ticks_range` or `copy_ticks_from`) uses `asyncio.to_thread` and correctly parses the returned tuples into `QuoteTick` and `TradeTick` events.
   - Implement polling for live market data if the stream socket is not available or if the EA is disabled. Alternatively, use MT5's `symbol_info_tick` polled periodically.

3. **Refactor Execution (`nautilus_mt5/execution.py` & `nautilus_mt5/client/order.py`):**
   - Translate Nautilus `SubmitOrder` into MT5's `order_send` dictionary format.
   - Implement `generate_order_status_report` and `generate_position_status_reports` using MT5's `positions_get` and `history_orders_get`.
   - Implement polling to detect order fills and position changes, publishing `OrderFilled` and `OrderAccepted` events to the message bus.

4. **Iterative approach:**
   - First, write a test script that instantiates the Data Provider and Execution Client directly with our ngrok config.
   - Run it, observe errors, and refactor the underlying code in `nautilus_mt5` to resolve them, ensuring we conform to the Nautilus Trader adapter guidelines (documented in step 1).
