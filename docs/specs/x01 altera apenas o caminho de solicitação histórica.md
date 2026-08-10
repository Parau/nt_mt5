---
ID: 019fecb8-3c88-777a-8da2-d47b24373b52
---

# A05 — Lean bounded historical TradeTick contract in `nt_mt5`

## Status

This document **supersedes**
`a04_spec_nt_mt5_lean_bounded_trade_ticks_for_warmup.md`.

It preserves the lean direction of A04 and incorporates the focused corrections
validated from `06_review_of_a04_b05_lean_simplifications.md`.

## Baselines

- TradingUltimate branch: `511-criando-playground`
- TradingUltimate review baseline:
  `476ea93c0aab34d5cb1c786057578ca758f02722`
- `nt_mt5` branch: `TradingUltimateV1`
- `nt_mt5` source baseline:
  `53a6d839e02fdc5bc2fb18811ffe7ba78df8ce49`
- NautilusTrader target: `v1.227.0`

---

# 1. Adapter responsibility

TradingUltimate needs one adapter primitive:

> Return the TradeTicks belonging to one bounded logical interval, preserving
> event multiplicity and live-equivalent conversion semantics, and distinguish
> a successful empty interval from failure.

The adapter does not own:

- whole warmup pagination;
- cutover;
- live buffering;
- historical visibility synchronization;
- replay orchestration;
- catch-up;
- handoff.

---

# 2. Lean implementation boundary

Keep the existing generic/count-based historical path unchanged.

Route only:

```text
RequestTradeTicks
start != None
end != None
limit == 0
```

to one dedicated internal bounded helper, conceptually:

```python
MetaTrader5ClientMarketDataMixin.get_historical_trade_ticks_range(...)
```

Everything else continues through the existing legacy path.

```text
[LOCK] The bounded warmup primitive must not expand the blast radius of
historical QuoteTick or count-based behavior.
```

---

# 3. Nautilus response contract

For every successful bounded request, including an empty one:

```python
self._handle_trade_ticks(
    request.instrument_id,
    ticks,
    request.id,
    request.start,
    request.end,
    request.params,
)
```

Required invariants:

```text
DataResponse.correlation_id == request.id
DataResponse.start == request.start
DataResponse.end == request.end
DataResponse.params == request.params
```

A successful empty result is:

```python
ticks == []
```

and still completes the Nautilus request/callback.

Do not retain the current bounded-path behavior:

```python
if not ticks:
    return
```

---

# 4. Canonical logical bounds

Accept timezone-aware:

- stdlib `datetime`;
- `pandas.Timestamp` where already accepted by adapter/runtime callers.

Normalize once to UTC and derive:

```text
start_ns: int
end_ns: int
```

Reject:

- naive datetime;
- missing start/end in the bounded helper;
- `start_ns > end_ns`.

Canonical values own provider querying and filtering.

Original `request.start/end` own response identity.

---

# 5. Select bounded path before legacy limit rewriting

The bounded decision must occur before any legacy logic such as:

```python
if not limit:
    limit = self._cache.tick_capacity
```

```text
[LOCK] Bounded `limit=0` is uncapped by `tick_capacity`.
```

---

# 6. Provider operation

Use:

```python
copy_ticks_range(
    symbol,
    fetch_start_seconds,
    fetch_end_seconds,
    COPY_TICKS_TRADE,
)
```

Do not use:

```text
copy_ticks_from
COPY_TICKS_ALL
```

for the bounded primitive.

---

# 7. Safe provider envelope

MetaTrader5 request endpoints are second-resolution while returned event time is
available at millisecond resolution through `time_msc`.

For:

```text
start_ns
end_ns
```

compute:

```python
NS_PER_SECOND = 1_000_000_000

fetch_start_seconds = start_ns // NS_PER_SECOND
fetch_end_seconds = (
    end_ns + NS_PER_SECOND - 1
) // NS_PER_SECOND

if fetch_end_seconds <= fetch_start_seconds:
    fetch_end_seconds = fetch_start_seconds + 1
```

The provider call intentionally overfetches.

Exact logical membership is restored after conversion.

---

# 8. Strict local materialization

The current external RPyC wrapper calls `normalize_rpyc_return()`, which attempts
`rpyc.classic.obtain()` but deliberately swallows obtain failure.

RPyC netrefs are transparent enough that a remote NumPy array can satisfy:

```python
isinstance(remote_array, np.ndarray)
```

Therefore:

```python
isinstance(raw, np.ndarray)
```

is **not** a proof that the object is local.

For this bounded helper use exact local production identity:

```python
if type(raw) is not np.ndarray:
    raise MT5HistoricalDataError(
        "copy_ticks_range did not materialize as an exact local numpy.ndarray"
    )
```

This is the lean operation-specific boundary.

Release homologation must confirm that both supported access modes return exact
local `numpy.ndarray` objects:

```text
LOCAL_PYTHON
EXTERNAL_RPYC
```

If a future supported official package intentionally returns an ndarray
subclass, revise this contract explicitly; do not silently broaden it.

```text
[LOCK] A remote ndarray netref is a failure even when `isinstance(...,
np.ndarray)` returns True.
```

---

# 9. Provider result semantics

```text
raw is None
    -> failure

exact local structured np.ndarray, len == 0
    -> successful []

exact local structured np.ndarray, len > 0
    -> parse/convert

wrong local type / netref
    -> failure
```

For `raw is None`, collect `last_error()` best-effort and raise an adapter
historical-data error.

```text
[LOCK] None must never become empty success.
```

---

# 10. Structured-array contract

Require:

```python
raw.dtype.names is not None
```

The bounded production row must expose the MT5 fields required to reconstruct
the same live routing/conversion semantics:

```text
time_msc
bid
ask
last
volume
volume_real
flags
```

`time` may be retained in the fixture/provider shape for diagnostics, but the
bounded TradeTick conversion must not rely on second-resolution `time` for
event ownership.

Missing required fields fail the whole bounded request.

The test fake must use the same NumPy structured-array shape as a captured or
official MetaTrader5 result.

Do not add dict/tuple/object production parsers merely for tests.

---

# 11. Reuse live tick routing and conversion

A05 tightens A04 by reusing the existing live semantic path per historical row.

For each structured MT5 row:

```python
wire_tick = WireTick(
    time_msc=int(row["time_msc"]),
    bid=float(row["bid"]),
    ask=float(row["ask"]),
    last=float(row["last"]),
    volume=int(row["volume"]),
    volume_real=float(row["volume_real"]),
    flags=int(row["flags"]),
)

decision = route_wire_tick(instrument, wire_tick)

if not decision.emit_trade:
    continue

trade = wire_tick_to_trade_tick(
    instrument,
    wire_tick,
    batch_or_current_ts_init,
    map_tick_flags_to_aggressor=venue_profile.map_tick_flags_to_aggressor,
)

if trade is not None:
    ticks.append(trade)
```

This reuses the same existing logic that live WS TradeTicks use for:

- trade selection from a row;
- price conversion;
- size conversion;
- aggressor conversion;
- event timestamp conversion;
- TradeId policy.

Do not implement a second historical-only conversion formula when the live
converter already expresses the desired semantics.

---

# 12. Valid provider rows versus malformed rows

`COPY_TICKS_TRADE` can select rows because Last and/or Volume changed.

Therefore a structurally valid provider row that the live routing logic decides
does not emit a `TradeTick` is **not** automatically a malformed row.

Semantics:

```text
missing/invalid required structural field
    -> bounded request failure

valid row + route_wire_tick(...).emit_trade == False
    -> valid non-emitted row; skip

valid row + live converter returns TradeTick
    -> include
```

This replaces A04's overly strict rule that every returned
`COPY_TICKS_TRADE` row must itself become a TradeTick.

The goal is historical/live stream equivalence, not "one MT5 row == one
Nautilus TradeTick".

---

# 13. `time_msc` remains mandatory

For every structured provider row entering routing:

```text
time_msc must be present and valid
```

No fallback to second-resolution `time` exists in the bounded path.

Nautilus `ts_event` remains:

```python
int(time_msc) * 1_000_000
```

---

# 14. Exact logical filtering

After live-equivalent conversion:

```python
ticks = [
    tick
    for tick in ticks
    if start_ns <= tick.ts_event <= end_ns
]
```

```text
[LOCK] Logical range ownership is determined only by `ts_event`.
```

Do not use:

- `ts_init`;
- provider-rounded endpoints;
- TradeId.

---

# 15. Multiplicity and stable order

Never deduplicate by:

- timestamp;
- TradeId;
- price/size tuple;
- invented composite key.

Sort only by:

```python
ticks.sort(key=lambda tick: tick.ts_event)
```

Python stable sort preserves provider order among equal timestamps.

---

# 16. `ts_init` remains unchanged

Do not introduce a feature-specific `ts_init` policy.

Warmup ownership is `ts_event` based.

Use the existing converter/runtime behavior unless a separate issue requires
changing it.

---

# 17. Historical/live stream parity is a release gate

Sharing the live conversion code reduces divergence but does not prove provider
stream parity.

The historical provider call uses:

```text
COPY_TICKS_TRADE
```

while the live MQL5 feed observes its own incoming tick stream before
`route_wire_tick()`.

For every runtime that will enable warmup, homologate representative real
intervals:

```text
live feed
    -> route_wire_tick()
    -> wire_tick_to_trade_tick()

versus

same interval after it becomes historical
    -> copy_ticks_range(COPY_TICKS_TRADE)
    -> route_wire_tick()
    -> wire_tick_to_trade_tick()
```

Compare the ordered TradeTick stream by at least:

```text
accepted event count
ts_event sequence
equal-time multiplicity
price.raw
size.raw
aggressor_side
```

Any unexplained mismatch blocks warmup certification.

Do not compensate for a provider selection mismatch inside TradingUltimate.

---

# 18. RPyC/LOCAL parity

Both access modes must satisfy the same bounded helper contract:

```text
LOCAL_PYTHON
EXTERNAL_RPYC
```

Required equivalence:

- exact local ndarray after boundary;
- same accepted TradeTicks;
- same ordering;
- same failure semantics.

No new bridge method is required.

---

# 19. Focused test matrix

## A05-T01 — bounded route isolation

`start/end + limit=0` enters only the dedicated helper.

## A05-T02 — response identity

Verify `request.id/start/end/params`.

## A05-T03 — successful empty ndarray

Produces `DataResponse([])` and completion.

## A05-T04 — provider operation

Verify `copy_ticks_range`, `COPY_TICKS_TRADE`, no `tick_capacity`.

## A05-T05 — provider envelope

Cover same-second, sub-second and exact-point requests.

## A05-T06 — exact logical filter

Before/start/inside/end/after provider events.

## A05-T07 — equal timestamp multiplicity/order

No dedupe and stable order.

## A05-T08 — adjacent millisecond ranges

No adapter-introduced loss/duplicate.

## A05-T09 — failed obtain leaves ndarray netref

Simulate:

```text
normalize_rpyc_return()
    attempts obtain
    obtain fails
    original ndarray netref returned
```

Assert:

```text
isinstance(netref, np.ndarray) may be True
type(netref) is not np.ndarray
bounded helper rejects
```

## A05-T10 — malformed structured result

Fail on:

- unstructured ndarray;
- missing required field;
- invalid required field.

## A05-T11 — None is failure

```text
raw is None -> failure
```

It must never become empty success.

## A05-T12 — provider exception

Failure.

## A05-T13 — live-equivalent row conversion

Feed one structured row and equivalent `WireTick` through historical/live
conversion and compare resulting TradeTick or non-emission decision.

## A05-T14 — result larger than cache capacity

All eligible ticks returned.

## A05-T15 — LOCAL/EXTERNAL parity

Equivalent local arrays produce equivalent TradeTicks.

---

# 20. Integration and DataTester

Still required:

```text
Actor.request_trade_ticks()
    -> DataEngine
    -> MetaTrader5DataClient
    -> DataResponse
    -> historical topic
    -> Actor.on_historical_data()
    -> completion callback
```

Cover:

- non-empty;
- empty;
- sequential requests;
- response identity.

Run TC-D31 for every adapter/provider path that will be used for warmup.

---

# 21. Real-provider homologation

For every candidate runtime record:

```text
adapter commit
Nautilus version
MetaTrader5 package version
terminal build
broker/server
VenueProfile
instrument
normalized calc mode
logical interval
provider envelope
raw row count
accepted TradeTick count
latency
```

Additionally execute the historical/live stream-parity gate from section 17.

Pin the exact MetaTrader5 package version only after the complete matrix passes.

---

# 22. Files expected to change

Primary:

```text
nautilus_mt5/data.py
nautilus_mt5/client/market_data.py
```

Reuse existing:

```text
nautilus_mt5/tick_routing.py
nautilus_mt5/feed/messages.py
nautilus_mt5/feed/converter.py
```

Tests/support:

```text
tests/support/fake_mt5_rpyc_bridge.py
tests/unit/...
tests/integration_tests/adapters/mt5/...
homologation/...
```

No initial need to change:

```text
MQL5/refactoring/bridge/mt5_bridge*.py
nautilus_mt5/metatrader5/MetaTrader5.py
nautilus_mt5/metatrader5/local_python.py
```

unless implementation evidence proves otherwise.

---

# 23. Acceptance criteria

- [ ] dedicated bounded helper leaves legacy count/quote paths unchanged;
- [ ] bounded `limit=0` is uncapped;
- [ ] response uses `request.id`;
- [ ] empty exact local ndarray is successful and completes;
- [ ] `None` is failure, never empty success;
- [ ] provider/transport/materialization failures remain failures;
- [ ] `copy_ticks_range` + `COPY_TICKS_TRADE` is used;
- [ ] provider envelope cannot collapse;
- [ ] exact local `type(raw) is np.ndarray` is required;
- [ ] ndarray netref after failed obtain is rejected;
- [ ] required structured fields are validated;
- [ ] `time_msc` is mandatory;
- [ ] historical rows reuse live routing/conversion;
- [ ] valid non-emitted provider rows follow the live routing decision;
- [ ] exact filtering uses `ts_event`;
- [ ] equal-timestamp multiplicity is preserved;
- [ ] stable order is preserved;
- [ ] no feature-specific `ts_init` change;
- [ ] LOCAL/EXTERNAL parity passes;
- [ ] Actor/DataEngine integration and TC-D31 pass;
- [ ] real historical/live TradeTick stream parity passes;
- [ ] exact MetaTrader5 package/environment is recorded before production use.

---

# 24. Contract exported to B06

B06 consumes only:

```text
bounded RequestTradeTicks(start, end, limit=0)

success:
  zero or more exact-range TradeTicks
  live-equivalent row conversion
  same-timestamp multiplicity preserved
  stable order
  completion callback occurs

failure:
  never disguised as empty
```

B06 separately owns session lifecycle and provider certification.
