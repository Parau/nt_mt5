# Project Decisions

This document records stable local decisions for `nt_mt5`.
These are project-level choices made while implementing the adapter against the NautilusTrader adapter contract.

## Source of truth

Official upstream references:
- Published docs: https://nautilustrader.io/docs/latest/developer_guide/adapters
- Published docs: https://nautilustrader.io/docs/latest/developer_guide/testing
- Published docs: https://nautilustrader.io/docs/latest/developer_guide/spec_data_testing
- Published docs: https://nautilustrader.io/docs/latest/developer_guide/spec_exec_testing

Optional upstream source references:
- GitHub source: https://github.com/nautechsystems/nautilus_trader/blob/develop/docs/developer_guide/adapters.md
- GitHub source: https://github.com/nautechsystems/nautilus_trader/blob/develop/docs/developer_guide/testing.md
- GitHub source: https://github.com/nautechsystems/nautilus_trader/blob/develop/docs/developer_guide/spec_data_testing.md
- GitHub source: https://github.com/nautechsystems/nautilus_trader/blob/develop/docs/developer_guide/spec_exec_testing.md

Upstream NautilusTrader documentation defines the adapter framework and testing expectations.
This file records only local decisions needed to implement `nt_mt5` consistently.

## Stable decisions

### 1. Venue identity
- The canonical venue is always `METATRADER_5`.
- Broker, server, and account metadata do not become the structural venue.
- Broker/server/account details belong in metadata or instrument/account info, not in venue identity.

### 2. Account validation
- `config.account_id` is the source of truth for validating the MT5 login.
- Nautilus `AccountId` is a structural engine identity.
- Do not parse Nautilus `AccountId` to recover the MT5 login.

### 3. Bridge shape
- The bridge stays MT5-native.
- Do not wrap MT5 behavior in Interactive Brokers terminology or flow shape.
- Keep MT5-native request/response semantics explicit in the adapter.

### 4. Execution semantics
- Order transformation must be based on MT5-native fields and behavior.
- Infer order side and order type from the correct MT5-native fields.
- Preserve explicit, tested rules for time-in-force and filling behavior.
- Do not keep hybrid order models once the MT5-native model is established.

### 5. Interface contract
- Use the modern NautilusTrader typed message contracts for data and execution clients.
- Do not keep legacy or hybrid method signatures once the typed path exists.

### 6. Unsupported operations
- Unsupported operational paths must fail safely.
- Prefer warnings or controlled empty/unsupported results.
- Do not raise raw `NotImplementedError` in operational paths.

### 7. Lifecycle and readiness
- Ready state must reflect real bootstrap success, not manually forced state.
- Connection and execution/account validation are related but distinct concerns.
- Do not mark the adapter as ready before transport/bootstrap state is genuinely established.

### 8. Tests versus production code
- Do not add production logic only to make tests pass.
- If tests need more realistic objects, improve the fake/fixture/test setup instead.
- Integration tests should prefer real adapter flows over manually injected final state.

### 9. Examples and public API
- Examples must use the real public API exactly.
- README, configs, factories, examples, and exported names must stay mutually consistent.

### 10. Terminal Access Model
- The adapter adopts `EXTERNAL_RPYC`, `LOCAL_PYTHON`, and `MANAGED_TERMINAL` as public access modes.
- `EXTERNAL_RPYC` is for existing/external terminals accessed via RPyC gateway.
- `LOCAL_PYTHON` is for direct local access using the official `MetaTrader5` Python package installed on the local machine.
- `MANAGED_TERMINAL` is for when the adapter controls the terminal lifecycle.
- Internally, `DOCKERIZED` is a backend for `MANAGED_TERMINAL`, not a top-level access mode.

### 11. Python/RPyC low-level layer
- Although the official NautilusTrader adapter guide describes a Rust-first architecture for new high-performance adapters, `nt_mt5` intentionally uses a Python/RPyC low-level boundary because the MetaTrader5 Python package and terminal availability dictate the integration boundary.
- This decision does not change the Nautilus layering principles used by the project:
  - keep the low-level boundary venue-native;
  - keep adapter responsibilities in the Python adapter layer;
  - expose typed configs, factories, provider, data client, and execution client;
  - use deterministic fake bridge tests for regression;
  - use optional live smoke tests only as supplementary validation.
- Do not introduce a second low-level architecture unless a future decision explicitly supersedes this one.

### 12. Live tests are supplementary
- Live tests with real MT5/RPyC are useful for validation, but they are not the source of truth for regression.
- The deterministic fake bridge suite remains the main correctness guard.
- Live tests must be optional, explicitly marked, and skipped when required environment variables are absent.
- Live execution tests must require explicit opt-in, such as `MT5_ENABLE_LIVE_EXECUTION=1`.

### 13. Capability support definition
- A capability is only `Supported` when it has production implementation, Nautilus-level flow coverage, deterministic tests, and updated docs.
- Gateway method availability alone is not sufficient.
- Wrapper-level routing tests are valuable, but they do not by themselves prove that a Nautilus-level capability is supported.
- If gateway/wrapper/wiring exists but Nautilus-level flow or tester coverage is incomplete, the capability should be marked `Partial`.
- Unsupported capabilities must be denied, rejected, or reported safely and documented clearly.

### 14. Fill reports source
- When fill reports are implemented, the preferred source is MT5 deal history through `history_deals_get` / `history_deals_total`, unless a better MT5-native source is explicitly adopted.
- `history_deals_get` existing in the gateway or wrapper does not, by itself, mean that Nautilus `FillReport` generation is supported.
- Fill-report support must include MT5 payload normalization, Nautilus report generation, deterministic tests, and execution capability matrix updates.

### 15. Trade tick decision point
- Trade tick support must be decided explicitly.
- If MT5/gateway data can provide last-trade semantics suitable for Nautilus `TradeTick`, the adapter should implement and test that mapping before declaring trade ticks supported.
- If the available MT5 data is quote-only or does not provide a reliable trade-tick semantic for a given asset class, the limitation must be documented in `docs/data_capability_matrix.md` and related docs.
- Do not treat quote ticks as trade ticks without an explicit documented mapping decision.

### 16. LOCAL_PYTHON terminal access
- `LOCAL_PYTHON` is a third public access mode alongside `EXTERNAL_RPYC` and `MANAGED_TERMINAL`.
- It uses the official `MetaTrader5` Python package installed directly on the local machine (normally Windows).
- It calls MT5-native functions (`initialize`, `login`, `terminal_info`, `account_info`, `symbol_info`, `symbol_info_tick`, `copy_rates_*`, `copy_ticks_*`, `order_send`, `positions_get`, `history_orders_get`, `history_deals_get`) on the locally imported module.
- It does not manage an external gateway process, RPyC connection, or Docker container.
- The only lifecycle it controls is the normal `MetaTrader5.initialize()` / `shutdown()` cycle.
- It must fail with a controlled, explicit error when used on an incompatible platform or when the `MetaTrader5` package is not installed.
- This mode is intentionally separate from `EXTERNAL_RPYC` and must not silently fall back to RPyC behavior.
- `DOCKERIZED` is not affected by this decision; it remains an internal backend of `MANAGED_TERMINAL` only.

### 17. Live quote tick transport (WS feed)
- Live quote ticks for `EXTERNAL_RPYC` deployments use an **MQL5 Service** (`CopyTicks` + cursor) pushing batches over **WebSocket** to an **InboundFeedGateway** in the Python adapter (`feed.enabled=True`).
- RPyC **`symbol_info_tick` polling** is the legacy live path when `feed.enabled=False`; it returns snapshots (~1 Hz) and must not be used for homologation of tick-a-tick streaming (TC-HOM-D02).
- Historical quote requests (`_request_quote_ticks`, `copy_ticks_*`) remain on-demand via RPyC regardless of feed mode.
- Homologation **TC-HOM-D02** validates the WS feed path only; it requires `MT5_FEED_ENABLED=1` and a running `NT5TickFeedService`. **Operational gate:** `homologation/run_feed_smoke.py` (run before open-market suites). Multi-scenario runners skip D02 unless `HOMOLOG_RUN_D02_IN_SUITE=1`.

### 18. Live bar transport (WS feed)
- Live bar subscriptions (`SubscribeBars`) for supported timeframes (M1, M5, M15, M30, H1, H4, D1) use the same **MQL5 Service WebSocket** as quote ticks: adapter sends `subscribe_bars` / `unsubscribe_bars`; Service polls `CopyRates(shift=1)` and pushes closed bars as `op:bar`.
- Requires `feed.enabled=True` on `MetaTrader5DataClientConfig`. Without the feed, live bar subscribe logs a warning and is ignored (no IB `req_real_time_bars` fallback).
- Sub-second bar specs (e.g. 5s) are not on the WS wire and are rejected with a warning.
- On-demand historical bars (`RequestBars` / `_request_bars`) use MT5-native **`copy_rates_*`** via RPyC (`copy_rates_from_pos` when `limit` is set; `copy_rates_range` when `start` is set). Legacy IB `req_historical_data` / `cancel_historical_data` removed from this path (D04b, 2026-06-27).
- Homologation **TC-HOM-D03** validates live M1 bars via WS; run `homologation/run_bar_smoke.py` with `MT5_FEED_ENABLED=1`.
- Homologation **TC-HOM-D04b** validates on-demand `RequestBars` via `_request_bars` → `copy_rates_from_pos` in `closed_market_suite.py`.
- After WS disconnect, the MQL5 Service clears **bar** subscription state (`active=false`); quote symbol subs remain until explicit `unsubscribe`. The adapter replays pending quote and bar subs on the next `hello` after reconnect.

### 19. RPyC bridge open orders (`orders_get`)
- `EXTERNAL_RPYC` gateways must expose `exposed_orders_get` forwarding to MT5 `orders_get`.
- Required for homologation **TC-HOM-E07** (modify volume verification) and for `generate_order_status_reports` when open pending orders exist.
- Staging reference: `MQL5/refactoring/bridge/mt5_bridge_v007.py` (bridge v0.7).

### 20. Multi-broker support via VenueProfile (Tickmill + XP/B3)
- One adapter (`METATRADER_5`); broker differences are expressed only through **`VenueProfile` + config** (`MT5_VENUE_PROFILE`, symbols, `account_id`). No `if broker == "XP"` branches in core adapter code.
- Live terminals on build 5833 report **`trade_calc_mode` 32/33** for B3 stocks/futures (not legacy 6/7). `XP_B3_PROFILE` declares both v2 and legacy aliases; `normalize_trade_calc_mode()` resolves lookups.
- Quote vs `TradeTick` routing for B3 uses **`tick_routing`** (tick shape, `TRADE_MODE`, `$` continuous suffix) — not broker name.
- Continuous B3 series (`WIN$`, `WDO$`) are **data-only** (`TRADE_MODE=DISABLED`); execution targets nominal contracts (`WINQ26`, `WDOQ26`).
- Homologation runners: `run_closed_market.py` (Tickmill) and `run_xp_closed_market.py` (XP). **MT5 login must be switched manually** between brokers — the RPyC bridge binds to whichever terminal session is open.

### 21. Historical quote ticks — MT5-native path (D21, 2026-06-28)
- On-demand historical `QuoteTick` requests (`_request_quote_ticks`) must use MT5-native **`copy_ticks_from`** via `MetaTrader5Client.get_historical_ticks`.
- Legacy Interactive Brokers **`req_historical_ticks`** / `cancel_historical_data` paths are removed from this adapter; do not reintroduce them.
- RPyC payloads may be numpy structured tuples — parse by field name / index, not only `getattr`.
- When `RequestQuoteTicks.limit > 0` and `start is None`, honor **`limit`** (do not always substitute `tick_capacity`). Use `tick_capacity` only when `limit=0`.
- Homologation: **TC-HOM-D21** (`closed_market_suite.py`, `run_wave4_homologation.py`, `run_open_market.py`).

### 22. Execution reconciliation and modify fixes (Wave 4, 2026-06-28)
- **`get_open_orders`** must call MT5 `orders_get` synchronously (same pattern as `positions_get`) and normalize dict rows to `MT5Order` for `generate_order_status_reports`.
- **`_parse_mt5_order_to_order_status_report`** resolves instruments by **symbol name**, not `find_with_symbol_id(symbol_string)`. Use `orderRef` or fall back to `str(order_id)` for `ClientOrderId` when `orderRef` is empty.
- **`_modify_order`** uses `TRADE_ACTION_MODIFY` (`action=7`) via `MetaTrader5Client.modify_order`, not a new `place_order` submit.
- **Stop trigger amend:** for `STOP_MARKET`, `ModifyOrder.trigger_price` maps to MT5 pending **`price`** (trigger), not `stoplimit`.
- **`MAP_TIME_IN_FORCE`** must be applied on submit (`type_time`); do not hardcode GTC for all pending orders (required for **DAY** limit homologation **E06e**).
- Homologation evidence: **E05b** fill reports, **E43** cancel rejection (10013), **E06de** FOK/DAY, **E07b** stop amend, **E81** open-on-start reconcile — see `res/proximos testes adaptador.md`.

### 23. A05 bounded historical TradeTicks (warmup primitive)
- Bounded `RequestTradeTicks(start, end, limit=0)` uses dedicated
  `get_historical_trade_ticks_range` → `copy_ticks_range` + `COPY_TICKS_TRADE`.
- Empty exact local ndarray → successful `DataResponse([])`; provider `None` /
  materialization / structural failures → `MT5HistoricalDataError` (no response).
- Rows reuse live `route_wire_tick` / `wire_tick_to_trade_tick`; filter by inclusive
  `ts_event`. Legacy count-based / QuoteTick fetch paths unchanged.
- Successful TradeTick responses use Nautilus 1.227 six-arg `_handle_trade_ticks`
  with `request.id`.
- EXTERNAL_RPYC transports ticks as brine-safe `MT5_TICKS_V1` frames
  `(tag, row_count, bytes)` reconstructed to an exact local ndarray; RPyC
  `allow_pickle` must remain disabled. LOCAL_PYTHON still returns the official
  local ndarray directly.
- Live trade emission must follow MT5 change flags (`TICK_FLAG_LAST` /
  `TICK_FLAG_VOLUME`), not stale `last > 0`. That aligns live with
  `COPY_TICKS_TRADE` and prevents Bid/Ask-only updates from inventing trades.
- Live quote emission must follow `TICK_FLAG_BID` / `TICK_FLAG_ASK` (aligned with
  `COPY_TICKS_INFO`); residual Bid/Ask on trade-only rows must not invent quotes.
- Historical QuoteTick (`get_historical_ticks` / BID_ASK) uses `COPY_TICKS_INFO`
  and the same live routing/conversion for QuoteTick emission. A05 TradeTick
  bounded path remains separate (`COPY_TICKS_TRADE`).
- Full historical↔live stream parity on AMP ENQU26: **PASS** after the flags-based
  live routing fix (`homologation/run_a05_trade_tick_parity.py`).
- **Warmup certification runtime:** A05 warmup is certified for **EXTERNAL_RPYC**
  on homologated profiles/providers only. `LOCAL_PYTHON` remains
  *implementation-compatible* (shared A05 helper + native ndarray path) but is
  **not warmup-certified** until it completes the same real-provider bounded
  request and live↔historical parity homologation. Do not enable LOCAL_PYTHON
  for production warmup until that certification exists.

## How to use this file

When changing the adapter, ask:
1. Is this required by NautilusTrader upstream behavior?
2. Is this already settled by a local decision here?
3. Is the supported/unsupported capability status already captured in `docs/data_capability_matrix.md` or `docs/execution_capability_matrix.md`?
4. Is there a real bug that justifies changing the local decision?

If the answer to (2) is yes and (4) is no, keep the existing decision.
If the answer to (3) is yes, keep the capability matrices aligned with the implementation and tests.

When an implementation task requires changing one of these decisions, update this file in the same task and explain why the previous decision no longer applies.
