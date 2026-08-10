---
ID: 019fed12-dbb6-72af-9157-0db40548b8dc
---

# A05 implementation clarifications x03 for the `nt_mt5` coding agent

## Status

**Implementation may proceed.**

The questions A–K raised before implementation have been checked against:

- `Parau/nt_mt5`, branch `TradingUltimateV1`, commit
  `53a6d839e02fdc5bc2fb18811ffe7ba78df8ce49`;
- NautilusTrader `v1.227.0`;
- the current `nt_mt5` adapter contract and data capability matrix;
- the current MT5 live-feed routing/conversion path;
- the official NautilusTrader adapter and DataTester development guidance.

This document **supersedes the previous A05 implementation-clarifications
document (x02)**. It clarifies implementation details only and does not reopen
A05 or B07 architecture. A05 remains the adapter specification.

x03 additionally resolves the final `LOCAL_PYTHON` constant-access contradiction:
`COPY_TICKS_TRADE` must be resolved through the common wrapper surface, with
attribute lookup followed by `get_constant(...)` fallback. No literal MT5 enum
value is used by production A05 code.

---

# 1. Key source facts

## 1.1 Current `nt_mt5` behavior

`nautilus_mt5/data.py::_handle_ticks_request()` currently rewrites:

```python
if not limit:
    limit = self._cache.tick_capacity
```

before the historical bounded path is selected.

The current `MetaTrader5DataClient._request_trade_ticks()` also:

- uses `request.correlation_id`;
- calls `_handle_trade_ticks(...)` with only three arguments;
- returns early when no ticks are received.

These behaviors do not match NautilusTrader `v1.227.0` for the new A05 bounded
request.

## 1.2 NautilusTrader `v1.227.0` response contract

The pinned runtime defines:

```python
_handle_trade_ticks(
    instrument_id,
    ticks,
    correlation_id,
    start,
    end,
    params,
)
```

`Actor.request_trade_ticks()` stores its pending request under the generated or
caller-supplied **request ID** and expects the eventual `DataResponse` to use that
ID as `DataResponse.correlation_id`.

Therefore:

```text
DataResponse.correlation_id = request.id
```

not:

```text
request.correlation_id
```

## 1.3 Nautilus historical request failure behavior

`Actor.request_trade_ticks()`:

1. stores the request in `_requests[request_id]`;
2. stores the user completion callback in `_pending_requests[request_id]`;
3. subscribes the Actor to the historical TradeTick topic;
4. dispatches the request.

Those entries are removed only when a `DataResponse` with the matching
correlation ID is received.

`LiveMarketDataClient` runs `_request_trade_ticks()` as an async task. If that
task raises, the runtime logs the exception. It does **not** automatically create
an error `DataResponse`.

NautilusTrader `v1.227.0` does not expose a separate historical-request error
payload to the Actor callback; the completion callback receives only the request
UUID.

This determines the A05 failure contract described below.

---

# 2. Resolution A — exact failure protocol

For the new bounded A05 path:

```text
success, including zero matching TradeTicks
    -> send normal DataResponse
    -> callback completes

provider / transport / materialization / structural conversion failure
    -> raise MT5HistoricalDataError
    -> do NOT send DataResponse
    -> do NOT convert the failure to []
```

A successful empty bounded interval must execute:

```python
self._handle_trade_ticks(
    request.instrument_id,
    [],
    request.id,
    request.start,
    request.end,
    request.params,
)
```

A failure must **not** execute `_handle_trade_ticks`.

Why:

- `DataResponse([])` means a real successful interval containing no emitted
  TradeTicks.
- The public Actor completion callback receives only the request UUID, not an
  error object.
- Converting a failure to `[]` would make B07 incorrectly advance to the next
  historical page as if the page had completed successfully.
- Letting the controlled exception escape causes `LiveMarketDataClient` to log
  the failed request task; B07's active-request timeout then fails the warmup
  terminally.

This is intentional for the A05/B07 contract.

Do not invent a custom error `DataResponse` in this slice.

---

# 3. Resolution B — `MT5HistoricalDataError`

Create one small adapter-controlled exception:

```text
nautilus_mt5/client/errors.py
```

Recommended implementation:

```python
"""Adapter-side market-data errors.

Purpose/Single Responsibility:
    Define controlled failures raised by MT5 client-layer market-data operations.

Data Flow & Dependencies:
    Raised by the MT5 client/data adapter and observed by Nautilus live-client
    task error handling.

Premises & Limitations:
    These exceptions report failed supported operations; they are not Nautilus
    DataResponse payloads.
"""


class MT5HistoricalDataError(RuntimeError):
    """Report a failed supported MT5 historical-data operation.

    Boundary Role: Adapter
    Access: EXTERNAL

    The exception distinguishes a failed bounded provider operation from a
    successful request whose result contains no matching data.
    """
```

Keep the taxonomy this small.

Do not reuse the old low-level `TerminalError` because A05 failures may originate
from:

- provider transport;
- RPyC materialization;
- cached-instrument preconditions;
- raw-row structure;
- Nautilus conversion.

When wrapping another exception:

```python
raise MT5HistoricalDataError(message) from exc
```

When `copy_ticks_range()` returns `None`, obtain `last_error()` best-effort and
include it in the exception message/diagnostics.

Do not let failure of `last_error()` hide the original failure.

---

# 4. Resolution C — implementation PR scope versus release gates

The implementation task should include all deterministic work necessary to make
A05 testable and reviewable.

## Required in the implementation change

### Production

- bounded route in `nautilus_mt5/data.py`;
- dedicated bounded helper in `nautilus_mt5/client/market_data.py`;
- `MT5HistoricalDataError`;
- reuse of the existing live routing/conversion functions;
- strict local NumPy result validation;
- correct six-argument Nautilus TradeTick response;
- no modification to unrelated count-based/QuoteTick fetch behavior.

### Deterministic tests

Implement the behavior covered by the A05 test matrix, including:

- route isolation;
- empty success;
- provider `None` failure;
- provider exception;
- failed RPyC materialization/netref rejection;
- exact range filtering;
- same-timestamp multiplicity/order;
- result larger than `tick_capacity`;
- response identity;
- bounded LOCAL/EXTERNAL-equivalent fixtures where practical;
- Actor/DataEngine historical response path with fake infrastructure.

### Test support

Update the fake RPyC bridge for the new bounded result contract.

### Documentation

Update deterministic coverage in the local capability/testing documentation
where the project contract requires it.

## Required before production warmup certification, but not necessarily runnable
## inside the coding PR environment

The following remain release/homologation gates:

- real terminal TC-D31;
- real `LOCAL_PYTHON` versus `EXTERNAL_RPYC` verification when both environments
  are available;
- real historical-versus-live TradeTick stream parity;
- repeated recent-history/synchronization observations;
- exact MetaTrader5 package-version homologation;
- final package pin;
- enabling `runtime.warmup` in TradingUltimate.

The implementation should add/reuse a runnable homologation harness for the new
parity checks when practical.

If the real terminal/market environment is unavailable, report those gates as
pending. Do **not** claim the runtime is warmup-certified.

---

# 5. Resolution D — bounded path versus legacy behavior

Keep legacy **fetch semantics** unchanged:

```text
count-based history
copy_ticks_from
legacy tick_capacity behavior
legacy QuoteTick path
legacy general get_historical_ticks()
```

However, there is one concrete compatibility bug inside
`_request_trade_ticks()` which should be corrected for **all successful
TradeTick responses**, not only bounded responses:

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

The current three-argument call is incompatible with the pinned
NautilusTrader `v1.227.0` method signature.

This correction is within the same method and should not be duplicated into a
bounded-only response branch.

Preserve the current legacy empty-result behavior unless separately tasked:

```text
legacy TradeTick empty result
    -> current legacy warning/return behavior remains

A05 bounded empty result
    -> DataResponse([])
```

Do **not** refactor `_request_quote_ticks()` in this A05 change solely because it
has an analogous legacy three-argument response problem. Record that as a
separate issue unless an unavoidable test dependency proves it must be fixed in
the same change.

---

# 6. Resolution E — `request.id` versus `request.correlation_id`

Use:

```python
request.id
```

as the correlation ID passed to `_handle_trade_ticks()`.

Do not use:

```python
request.correlation_id
```

for the `DataResponse`.

Reason:

```text
Actor.request_trade_ticks()
    -> pending request key = RequestTradeTicks.id

DataResponse.correlation_id
    -> Actor looks up and completes that pending request
```

The request's optional `correlation_id` belongs to broader message correlation;
it is not the ID under which `Actor.request_trade_ticks()` owns this historical
request.

This rule applies to both new bounded and successful legacy TradeTick responses.

---

# 7. Resolution F — VenueProfile capability gate

Keep the existing `VenueProfile` TradeTick gate before entering the bounded
helper.

Do not move provider capability policy into the low-level helper.

For the bounded path:

```text
TESTED / CERTIFIED
    -> proceed

ASSUMED / OBSERVED
    -> preserve existing warning behavior and proceed

UNSUPPORTED
    -> raise controlled MT5HistoricalDataError

strict-profile check failure
    -> wrap/raise MT5HistoricalDataError
```

For the legacy path, preserve current behavior unless separately tasked.

B07 independently prevents production warmup enablement until the entire concrete
provider runtime has passed its stronger homologation gates. A05 therefore does
not need to invent a second capability model.

---

# 8. Resolution G — exact malformed-row contract

The bounded path accepts only an **exact local NumPy structured ndarray**.

## 8.1 Whole-result validation

Require:

```python
type(raw) is np.ndarray
raw.dtype.names is not None
```

Required field names:

```python
_REQUIRED_TRADE_FIELDS = frozenset(
    {
        "time_msc",
        "bid",
        "ask",
        "last",
        "volume",
        "volume_real",
        "flags",
    }
)
```

If any required field is absent, fail the entire bounded request.

Do not support dict/tuple/arbitrary-object rows in this new production path.

## 8.2 Per-row structural extraction

Use strict extraction.

For integer fields, prefer integer-only conversion semantics such as
`operator.index(...)` so a floating-point timestamp/flag is not silently
truncated:

```python
time_msc = operator.index(row["time_msc"])
volume = operator.index(row["volume"])
flags = operator.index(row["flags"])
```

Require:

```text
time_msc > 0
volume >= 0
flags >= 0
```

For:

```text
bid
ask
last
volume_real
```

convert to `float` and require `math.isfinite(...)`.

Require:

```text
volume_real >= 0
```

Do **not** classify zero `bid`, zero `ask`, zero `last`, or zero volume as a
structural error. Those can be legitimate MT5 row shapes and the live routing /
conversion logic already decides whether a TradeTick should be emitted.

Do not add an historical-only:

```text
last > 0
ask > bid
```

structural rule.

## 8.3 Routing/conversion outcome

After constructing `WireTick`:

```python
decision = route_wire_tick(instrument, wire_tick)

if not decision.emit_trade:
    continue
```

Then:

```python
trade = wire_tick_to_trade_tick(
    instrument,
    wire_tick,
    batch_ts_init,
    map_tick_flags_to_aggressor=...,
)

if trade is None:
    continue
```

A valid provider row that the **live-equivalent route** does not turn into a
TradeTick is a valid non-emitted row, not a malformed row.

Exceptions raised while building/converting an in-range candidate are bounded
request failures and should be wrapped in `MT5HistoricalDataError`.

Do not silently `continue` after structural extraction/conversion exceptions.

---

# 9. Resolution H — `ts_init`

Use **one** clock value per bounded provider result:

```python
batch_ts_init = self._clock.timestamp_ns()
```

Pass the same value to every:

```python
wire_tick_to_trade_tick(...)
```

within that returned ndarray.

This mirrors the current live WS path, which captures one `ts_init` for one
`TickBatchMessage` and passes it to all tick conversions in that batch.

Do not create a new historical-specific `ts_init` policy.

The existing converter already applies:

```python
ts_init=max(batch_ts_init, ts_event)
```

---

# 10. Resolution I — `wait_until_ready`, `use_rth`, cache miss

## `wait_until_ready`

Keep:

```python
await self._client.wait_until_ready()
```

before the bounded helper, matching the current bounded request path.

Do not refactor `wait_until_ready()` as part of A05.

Its current timeout behavior logs rather than re-raising; if the provider is in
fact unavailable, the bounded provider call/materialization path remains
responsible for producing the controlled A05 failure.

## `use_rth`

Do not add regular-trading-hours filtering to the bounded helper.

The current MT5 tick historical implementation does not implement a real RTH
filter.

Recommended bounded helper signature therefore omits `use_rth`.

## Instrument missing from cache

For the new bounded path:

```text
instrument missing
    -> MT5HistoricalDataError
```

Never convert this condition to successful `[]`.

For the legacy path, preserve current behavior.

Also treat a malformed/missing symbol mapping required to build `MT5Symbol` as a
bounded precondition failure.

---

# 11. Resolution J — fake RPyC bridge

Yes, the fake must change for the new bounded contract.

Update:

```text
tests/support/fake_mt5_rpyc_bridge.py
```

for `exposed_copy_ticks_range()` only.

## Constants

Add:

```python
"COPY_TICKS_TRADE": 2
```

to the fake gateway constants so its `get_constant(...)` surface mirrors the
real provider contract.

Also add a focused LOCAL_PYTHON wrapper test using a fake underlying official
MetaTrader5 module where `COPY_TICKS_TRADE` exists only on that module. The A05
constant resolver must obtain it through `LocalPythonMT5.get_constant(...)`.

## Bounded result

Return a NumPy structured array matching the real MT5 tick shape, preferably all
eight canonical fields:

```text
time
bid
ask
last
volume
time_msc
flags
volume_real
```

Example dtype shape:

```python
MT5_TICK_DTYPE = np.dtype(
    [
        ("time", "<i8"),
        ("bid", "<f8"),
        ("ask", "<f8"),
        ("last", "<f8"),
        ("volume", "<u8"),
        ("time_msc", "<i8"),
        ("flags", "<u4"),
        ("volume_real", "<f8"),
    ],
)
```

Use captured/official fixture values rather than broadening production parsing to
accept the old fake dictionaries.

Keep legacy `exposed_copy_ticks_from()` list/dict behavior unchanged unless an
existing legacy test itself requires adjustment.

## RPyC materialization test

The normal external fake path should produce:

```python
type(raw) is np.ndarray
```

after wrapper materialization.

Add a dedicated negative test where:

```text
rpyc.classic.obtain(...) fails
normalize_rpyc_return returns the original ndarray netref
isinstance(netref, np.ndarray) can be True
type(netref) is not np.ndarray
```

The bounded helper must reject it.

Do not add a second generic `rpyc.classic.obtain(list(raw))` fallback in the
bounded helper.

---

# 12. Resolution K — homologation versus coding

Implement the deterministic behavior and homologation **harness** now.

Do not enable TradingUltimate warmup solely because deterministic tests pass.

The real provider release gate must compare the actual TradeTick stream observed
by the adapter live path with the same interval after it becomes historical.

Important: compare the **effective live pipeline**, not merely the converter in
isolation.

The live side includes:

```text
MQL5 feed
    -> parse
    -> InboundFeedHandler
    -> TickBatchMessage
    -> route_wire_tick_to_nautilus
    -> emitted TradeTick
```

The historical side includes:

```text
copy_ticks_range(COPY_TICKS_TRADE)
    -> A05 structured-array validation
    -> WireTick
    -> route_wire_tick
    -> wire_tick_to_trade_tick
    -> emitted TradeTick
```

Compare at least:

```text
accepted TradeTick count
ordered ts_event sequence
equal-time multiplicity
price.raw
size.raw
aggressor_side
```

If there is a mismatch, do not compensate inside the warmup coordinator.

Fix/understand the adapter/provider path first or leave
`runtime.warmup=None`.

This matters because the live `InboundFeedHandler` has its own dedup/filter
behavior before conversion.

---

# 13. Dedicated bounded helper

Recommended narrow internal signature:

```python
async def get_historical_trade_ticks_range(
    self,
    *,
    symbol: MT5Symbol,
    instrument: Instrument,
    start_date_time: datetime | pd.Timestamp,
    end_date_time: datetime | pd.Timestamp,
    map_tick_flags_to_aggressor: bool,
) -> list[TradeTick]:
    ...
```

Do not add:

```text
tick_type
number_of_ticks
use_rth
```

to this helper.

Those concepts belong to the legacy generic historical method and are not needed
by this bounded primitive.

Passing the already-cached `instrument` avoids a second cache lookup and makes
the helper's conversion dependency explicit.

---

# 14. Canonical bounds, provider envelope, and MT5 constant resolution

Use one private canonicalizer for the bounded helper.

Conceptually:

```python
def _historical_utc_timestamp(value: datetime | pd.Timestamp) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        raise MT5HistoricalDataError("historical bound must be timezone-aware")
    return ts.tz_convert("UTC")
```

Then:

```python
start_ts = _historical_utc_timestamp(start_date_time)
end_ts = _historical_utc_timestamp(end_date_time)

start_ns = int(start_ts.value)
end_ns = int(end_ts.value)

if start_ns > end_ns:
    raise MT5HistoricalDataError("historical start was after end")
```

Provider envelope:

```python
NS_PER_SECOND = 1_000_000_000

fetch_start_seconds = start_ns // NS_PER_SECOND
fetch_end_seconds = (end_ns + NS_PER_SECOND - 1) // NS_PER_SECOND

if fetch_end_seconds <= fetch_start_seconds:
    fetch_end_seconds = fetch_start_seconds + 1
```

## 14.1 Resolve `COPY_TICKS_TRADE` through the common terminal wrapper surface

Do **not** assume every terminal wrapper exposes MT5 constants as direct Python
attributes.

Current surfaces differ:

```text
EXTERNAL_RPYC wrapper
    -> exposes COPY_TICKS_TRADE directly as a class attribute

LOCAL_PYTHON wrapper
    -> deliberately exposes get_constant(name)
    -> delegates to the official MetaTrader5 module
```

Therefore production A05 code must use a narrow resolver equivalent to:

```python
def _resolve_mt5_constant(mt5: Any, name: str) -> Any:
    value = getattr(mt5, name, None)
    if value is not None:
        return value

    get_constant = getattr(mt5, "get_constant", None)
    if callable(get_constant):
        value = get_constant(name)
        if value is not None:
            return value

    raise MT5HistoricalDataError(
        f"MT5 terminal surface does not expose required constant {name}"
    )
```

Then:

```python
flags = _resolve_mt5_constant(mt5, "COPY_TICKS_TRADE")
```

and:

```python
try:
    raw = await asyncio.to_thread(
        mt5.copy_ticks_range,
        symbol.symbol,
        fetch_start_seconds,
        fetch_end_seconds,
        flags,
    )
except Exception as exc:
    raise MT5HistoricalDataError(
        f"copy_ticks_range failed for {symbol.symbol}",
    ) from exc
```

### Why this is the required solution

This is preferred over adding:

```python
COPY_TICKS_TRADE = 2
```

to `LocalPythonMT5`.

`LocalPythonMT5.get_constant()` already delegates constant ownership to the
installed official MetaTrader5 package. Duplicating constants on the wrapper
would create a second maintained source of truth and would broaden the change
without improving the abstraction.

It is also preferred over production code containing:

```python
flags = 2
```

even though MetaTrader documents `COPY_TICKS_TRADE` as enum value `2`.
The adapter should consume the provider's named constant rather than duplicate
the numeric protocol value.

The resolver is intentionally:

```text
direct attribute
    -> get_constant(name)
    -> controlled failure
```

It must **not** silently fall back to literal `2`, `COPY_TICKS_ALL`, or any other
tick mode.

No change to `nautilus_mt5/metatrader5/local_python.py` is required for A05,
because its existing `get_constant()` method already provides exactly the needed
capability.

---

# 15. Strict materialization boundary

After the wrapper returns:

```python
if raw is None:
    diagnostics = _best_effort_mt5_last_error(mt5)
    raise MT5HistoricalDataError(
        f"copy_ticks_range returned None for {symbol.symbol}; "
        f"last_error={diagnostics!r}"
    )

if type(raw) is not np.ndarray:
    raise MT5HistoricalDataError(
        "copy_ticks_range result is not an exact local numpy.ndarray",
    )

if raw.dtype.names is None:
    raise MT5HistoricalDataError(
        "copy_ticks_range returned an unstructured numpy.ndarray",
    )
```

The exact-type rule is intentionally stronger than `isinstance`.

This is operation-local. Do not broadly rewrite `normalize_rpyc_return()`.

---

# 16. Recommended `_request_trade_ticks()` control flow

Conceptually:

```python
async def _request_trade_ticks(self, request: RequestTradeTicks) -> None:
    bounded = (
        request.start is not None
        and request.end is not None
        and request.limit == 0
    )

    instrument = self._cache.instrument(request.instrument_id)
    if instrument is None:
        if bounded:
            raise MT5HistoricalDataError(
                f"Instrument not in cache: {request.instrument_id}"
            )
        self._log.error(...)
        return

    # Keep the existing VenueProfile policy before either fetch path.
    status = ...
    if capability_fails:
        if bounded:
            raise MT5HistoricalDataError(...)
        # Existing legacy behavior.
        ...
        return

    if bounded:
        try:
            symbol = MT5Symbol(**instrument.info["symbol"])
        except Exception as exc:
            raise MT5HistoricalDataError(
                f"Invalid MT5 symbol metadata for {request.instrument_id}"
            ) from exc

        await self._client.wait_until_ready()

        ticks = await self._client.get_historical_trade_ticks_range(
            symbol=symbol,
            instrument=instrument,
            start_date_time=request.start,
            end_date_time=request.end,
            map_tick_flags_to_aggressor=(
                self._venue_profile.map_tick_flags_to_aggressor
            ),
        )

        # Empty is a formal success here.
        self._handle_trade_ticks(
            request.instrument_id,
            ticks,
            request.id,
            request.start,
            request.end,
            request.params,
        )
        return

    # Existing count-based fetch behavior.
    ticks = await self._handle_ticks_request(...)

    # Preserve legacy empty behavior for this task.
    if not ticks:
        self._log.warning(...)
        return

    # Fix the concrete Nautilus v1.227.0 response signature bug.
    self._handle_trade_ticks(
        request.instrument_id,
        ticks,
        request.id,
        request.start,
        request.end,
        request.params,
    )
```

The actual implementation should minimize duplicated capability/logging code, but
must not route the bounded request through `_handle_ticks_request()` because that
function rewrites `limit=0`.

---

# 17. Row conversion skeleton

Conceptually:

```python
required = {
    "time_msc",
    "bid",
    "ask",
    "last",
    "volume",
    "volume_real",
    "flags",
}

names = frozenset(raw.dtype.names or ())
missing = required - names
if missing:
    raise MT5HistoricalDataError(
        f"copy_ticks_range missing required fields: {sorted(missing)}"
    )

batch_ts_init = self._clock.timestamp_ns()
ticks: list[TradeTick] = []

for index, row in enumerate(raw):
    try:
        time_msc = operator.index(row["time_msc"])
        volume = operator.index(row["volume"])
        flags = operator.index(row["flags"])

        bid = float(row["bid"])
        ask = float(row["ask"])
        last = float(row["last"])
        volume_real = float(row["volume_real"])
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise MT5HistoricalDataError(
            f"Malformed MT5 historical trade row at index={index}"
        ) from exc

    if time_msc <= 0:
        raise MT5HistoricalDataError(
            f"Invalid time_msc at index={index}: {time_msc}"
        )
    if volume < 0 or flags < 0:
        raise MT5HistoricalDataError(
            f"Invalid volume/flags at index={index}"
        )
    if (
        not math.isfinite(bid)
        or not math.isfinite(ask)
        or not math.isfinite(last)
        or not math.isfinite(volume_real)
        or volume_real < 0
    ):
        raise MT5HistoricalDataError(
            f"Non-finite/invalid MT5 trade row at index={index}"
        )

    wire = WireTick(
        time_msc=time_msc,
        bid=bid,
        ask=ask,
        last=last,
        volume=volume,
        volume_real=volume_real,
        flags=flags,
    )

    decision = route_wire_tick(instrument, wire)
    if not decision.emit_trade:
        continue

    try:
        trade = wire_tick_to_trade_tick(
            instrument,
            wire,
            batch_ts_init,
            map_tick_flags_to_aggressor=map_tick_flags_to_aggressor,
        )
    except Exception as exc:
        raise MT5HistoricalDataError(
            f"Failed converting MT5 historical trade row at index={index}"
        ) from exc

    if trade is not None:
        ticks.append(trade)
```

Then apply the A05 inclusive logical filter:

```python
ticks = [
    tick
    for tick in ticks
    if start_ns <= tick.ts_event <= end_ns
]

ticks.sort(key=lambda tick: tick.ts_event)
return ticks
```

Python sort is stable, so equal-timestamp provider order remains intact.

Do not deduplicate.

---

# 18. Test implementation guidance

At minimum, the coding change should prove these distinct behaviors.

## Routing / response

- bounded `start/end + limit=0` never reaches `_handle_ticks_request()`;
- legacy count request still reaches the existing path;
- bounded empty ndarray calls `_handle_trade_ticks(..., [])`;
- bounded response correlation is `request.id`;
- successful legacy TradeTick response uses the correct six-argument method.

## Provider

- `copy_ticks_range()` used;
- `COPY_TICKS_TRADE` used;
- direct-attribute constant resolution works for the EXTERNAL_RPYC wrapper;
- `get_constant("COPY_TICKS_TRADE")` fallback works for LOCAL_PYTHON;
- missing constant in both surfaces raises `MT5HistoricalDataError`;
- `get_constant()` failure propagates as/wraps into `MT5HistoricalDataError`;
- production code never falls back to literal `2` or `COPY_TICKS_ALL`;
- no `tick_capacity` cap;
- same-second/exact-point envelope is widened;
- provider `None` raises;
- provider exception raises;
- `last_error()` diagnostics are best-effort only.

## Materialization

- exact local ndarray accepted;
- ndarray subclass/netref rejected by exact-type rule;
- failed `obtain` leaving an ndarray netref is rejected;
- unstructured ndarray rejected;
- missing field rejected.

## Row semantics

- zero last can be a valid non-emitted row;
- zero volume fields can be a valid non-emitted row;
- invalid/non-finite structural values fail;
- same timestamp multiplicity survives;
- stable ordering survives;
- live-equivalent routing/conversion produces the same TradeTick for the same
  `WireTick`;
- exact inclusive `ts_event` filtering works.

## Nautilus integration

Exercise the real logical flow with fake provider infrastructure:

```text
Actor.request_trade_ticks
    -> DataEngine
    -> MetaTrader5DataClient
    -> bounded helper
    -> DataResponse
    -> historical TradeTick topic
    -> Actor.on_historical_data
    -> completion callback
```

Required successful cases:

- non-empty;
- empty;
- sequential bounded requests;
- response identity.

Also verify a provider failure does not produce a fake successful response.

---

# 19. TC-D31 and official adapter guidance

The official NautilusTrader Data Testing Spec defines TC-D31 for historical
TradeTicks.

The implementation should preserve/extend the existing deterministic TC-D31
coverage and later run the real-provider case for every provider surface that
will be certified for warmup.

The official adapter guide also expects:

- provider-native requests in the adapter/client layer;
- conversion to Nautilus domain types at the adapter boundary;
- integration tests for historical requests;
- explicit error handling;
- tests matching every capability the adapter claims to support.

A05 follows this model by keeping:

```text
copy_ticks_range / raw MT5 details
    -> client layer

RequestTradeTicks / DataResponse
    -> Nautilus adapter layer
```

---

# 20. Non-goals for the A05 coding task

Do not include these unrelated changes unless a direct failing test proves they
are unavoidable:

- B07 coordinator implementation;
- TradingUltimate runtime configuration;
- quote-tick historical redesign;
- generic `_handle_ticks_request()` rewrite;
- global `wait_until_ready()` redesign;
- global RPyC normalization redesign;
- new RTH/session filtering;
- TradeId redesign;
- MT5 live-feed dedup redesign;
- new generic historical error protocol in Nautilus;
- automatic MetaTrader5 package upgrade/pin before homologation.

---

# 21. Completion definition for the coding agent

The implementation can be reported as **code-complete for A05** when:

- production bounded path is implemented;
- deterministic tests pass;
- fake bridge represents the real bounded ndarray shape;
- Actor/DataEngine success path is proven for empty and non-empty responses;
- controlled failure cases are tested;
- existing unrelated behavior remains green;
- homologation harness/evidence points are identified.

It must **not** be reported as production warmup-certified until the real
provider gates are complete.

A suggested final implementation report should separate:

```text
Implemented and deterministic PASS
Real-provider homologation PASS
Real-provider homologation PENDING
Out-of-scope issues discovered
```

Do not conflate those states.

---

# 22. Authoritative references

## `nt_mt5`

- `AGENTS.md`
- `docs/adapter_contract.md`
- `docs/data_capability_matrix.md`
- `res/proximos testes adaptador.md`
- `nautilus_mt5/data.py`
- `nautilus_mt5/client/market_data.py`
- `nautilus_mt5/client/client.py`
- `nautilus_mt5/metatrader5/utils.py`
- `nautilus_mt5/metatrader5/MetaTrader5.py`
- `nautilus_mt5/metatrader5/local_python.py`
- `nautilus_mt5/feed/messages.py`
- `nautilus_mt5/feed/handler.py`
- `nautilus_mt5/feed/converter.py`
- `nautilus_mt5/tick_routing.py`
- `nautilus_mt5/venue_profile.py`
- `tests/support/fake_mt5_rpyc_bridge.py`

Baseline:
`53a6d839e02fdc5bc2fb18811ffe7ba78df8ce49`

## NautilusTrader

Pinned runtime:

- `nautilus_trader/common/actor.pyx`, tag `v1.227.0`
- `nautilus_trader/live/data_client.py`, tag `v1.227.0`
- `nautilus_trader/data/client.pyx`, tag `v1.227.0`

Official developer documentation:

- `https://nautilustrader.io/docs/latest/developer_guide/adapters/`
- `https://nautilustrader.io/docs/latest/developer_guide/testing/`
- `https://nautilustrader.io/docs/latest/developer_guide/spec_data_testing/`

---

# 23. Final resolution of the LOCAL_PYTHON blocker

The final decision is **option 2** from the implementation-agent review:

```text
getattr(mt5, "COPY_TICKS_TRADE", None)
    -> if absent, call get_constant("COPY_TICKS_TRADE")
    -> if still absent, controlled MT5HistoricalDataError
```

This is now part of the A05 implementation contract.

Do not choose option 1 (duplicated wrapper constant) and do not choose option 3
(hardcoded production literal).

Implementation is authorized after this clarification.

---

# 24. Final instruction

Proceed with the A05 implementation using the decisions in this document.

If implementation evidence contradicts one of these pinned-source assumptions,
stop at that concrete contradiction and report it rather than adding a fallback
that weakens:

```text
empty success != failure
```

or the historical/live TradeTick equivalence objective.
