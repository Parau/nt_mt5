---
ID: 019fed42-0949-7a39-a3ed-a6508e0fa313
---

# Review of A05 implementation — `nt_mt5/melhorando-historico`

## Verdict

**Do not merge/promote this branch as the final A05 implementation yet.**

The core bounded TradeTick implementation is substantially correct and should be
preserved. The review found:

1. **one production blocker** introduced by the implementation:
   `allow_pickle=True` on the RPyC bridge;
2. **one required Nautilus integration test still missing**;
3. **one mandatory homologation gate incorrectly described as optional / ready**;
4. **one small controlled-error gap** in the bounded row routing/conversion path.

No return to a broader architecture is required. The corrections below are
surgical.

Review baseline:

```text
repository: Parau/nt_mt5
branch: melhorar-historico / actual ref reviewed: melhorando-historico
base: 53a6d839e02fdc5bc2fb18811ffe7ba78df8ce49
head: 023249f6471dda978223c349ef549ff3c80b5868
NautilusTrader: v1.227.0
```

The branch is one commit ahead of `TradingUltimateV1`.

---

# 1. Preserve these parts

Do **not** redesign the following. They match A05/x03:

- bounded route is selected only for:
  ```text
  start != None
  end != None
  limit == 0
  ```
  before legacy `tick_capacity` rewriting;
- legacy count-based fetch remains separate;
- bounded requests use `copy_ticks_range`;
- `COPY_TICKS_TRADE` resolution is:
  ```text
  direct attribute -> get_constant(name) -> controlled error
  ```
  with no literal fallback;
- bounded empty ndarray is a successful `DataResponse([])`;
- provider `None` / provider failure is not converted to empty success;
- exact local ndarray is required by the A05 helper;
- required tick fields and `time_msc` are checked;
- historical rows reuse `route_wire_tick()` and
  `wire_tick_to_trade_tick()`;
- logical filtering is inclusive by `ts_event`;
- multiplicity is preserved and sorting is stable by `ts_event`;
- one `ts_init` is captured per bounded provider result;
- successful TradeTick responses use the Nautilus 1.227 six-argument
  `_handle_trade_ticks(...)` contract and `request.id`;
- unsupported VenueProfile behavior fails closed on the bounded path;
- the fake `copy_ticks_from` legacy shape remains separate from the new bounded
  `copy_ticks_range` shape.

The real AMP bounded probe is useful evidence: the committed report shows a
30-minute ENQU26 request producing 9,212 TradeTicks, successful zero-length
responses, and provider flag `2`.

---

# 2. BLOCKER — remove `allow_pickle=True` from the RPyC bridge

## Problem

The branch changes both:

```text
MQL5/refactoring/bridge/mt5_bridge.py
MQL5/refactoring/bridge/mt5_bridge_v008.py
```

to:

```python
protocol_config={
    "allow_public_attrs": True,
    "allow_all_attrs": True,
    "allow_pickle": True,
}
```

This was added so `rpyc.classic.obtain()` can materialize the remote NumPy
ndarray.

This is not an acceptable A05 transport requirement.

The same `ThreadedServer` is constructed without an explicit `hostname` and
without an `authenticator`.

RPyC's server contract states:

```text
hostname=None       -> wildcard address / all interfaces
authenticator=None  -> no authentication
```

and `allow_pickle` defaults to `False`.

Therefore A05 currently broadens the bridge's trust surface merely to transport
one historical ndarray.

## Required correction

Restore the bridge to:

```python
protocol_config={
    "allow_public_attrs": True,
    "allow_all_attrs": True,
}
```

or explicitly:

```python
"allow_pickle": False
```

Do this in both bridge copies.

Do **not** solve A05 by enabling pickle globally.

Do **not** change `normalize_rpyc_return()` globally for this feature.

## Preferred safe transport

Keep the public adapter-facing contract:

```text
MetaTrader5.copy_ticks_range(...) -> exact local np.ndarray | None
```

but change the RPyC wire representation.

A safe and efficient option is a versioned, brine-serializable binary frame.

### Bridge side

The MT5 bridge receives the official NumPy structured ndarray.

For `None`:

```python
return None
```

For a valid tick array, project it into the canonical MT5 tick layout and return
only immutable RPyC-brine-safe primitives:

```text
(
    "MT5_TICKS_V1",
    row_count,
    raw_bytes,
)
```

where:

```text
raw_bytes = canonical_array.tobytes(order="C")
```

and the canonical dtype is exactly:

```python
np.dtype(
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

The bridge should validate/project the provider fields before producing the
frame.

The wire tag is important: do not return an unversioned arbitrary tuple that
could be confused with another endpoint shape.

### EXTERNAL_RPYC wrapper side

In:

```text
nautilus_mt5/metatrader5/MetaTrader5.py
```

`copy_ticks_range()` should receive the safe frame and reconstruct:

```python
array = np.frombuffer(
    payload_bytes,
    dtype=MT5_TICK_DTYPE,
    count=row_count,
).copy()
```

Validate before reconstruction:

```text
tag == "MT5_TICKS_V1"
row_count >= 0
len(payload_bytes) == row_count * MT5_TICK_DTYPE.itemsize
```

Malformed wire payload should raise a controlled low-level `RuntimeError`.
The A05 helper already wraps exceptions from `mt5.copy_ticks_range(...)` as
`MT5HistoricalDataError`.

The `.copy()` is intentional so the returned array owns local memory and the
A05 invariant remains:

```python
type(raw) is np.ndarray
```

### LOCAL_PYTHON

Do not change `LocalPythonMT5.copy_ticks_range()`.

It already returns the official local NumPy ndarray directly.

### Why this is preferable

It preserves:

```text
LOCAL_PYTHON  -> official local ndarray
EXTERNAL_RPYC -> safe wire frame -> reconstructed local ndarray
```

without making pickle part of the network protocol.

RPyC's brine serializer supports immutable primitives including bytes, integers,
strings and tuples, so this frame remains by-value without pickle.

## Tests required

Add deterministic tests proving:

1. bridge protocol config does not enable pickle;
2. non-empty tick frame reconstructs exact local `np.ndarray`;
3. empty tick frame reconstructs exact local empty `np.ndarray`;
4. `None` stays `None`;
5. bad tag fails;
6. negative row count fails;
7. byte-length/count mismatch fails;
8. reconstructed dtype/names equal the canonical MT5 tick layout;
9. row order and duplicate `time_msc` values survive byte transport unchanged;
10. A05 bounded helper still accepts the reconstructed result.

After this correction, rerun the real AMP A05 bounded probe and replace the
committed report. The current 9,212-tick report is evidence for the old
pickle-enabled transport, not the corrected transport.

---

# 3. REQUIRED TEST GAP — prove Actor -> DataEngine -> adapter -> DataResponse -> Actor

## Problem

The new tests in:

```text
tests/integration_tests/adapters/mt5/test_data_tester_matrix_external_rpyc.py
```

call:

```python
await data_client._request_trade_ticks(req)
```

and replace:

```python
data_client._handle_trade_ticks = _spy_handle
```

The real AMP runner uses the same pattern.

That proves much of the DataClient behavior, but it explicitly bypasses the part
of the Nautilus contract that motivated the six-argument response fix:

```text
Actor.request_trade_ticks()
    -> DataEngine.request
    -> MetaTrader5DataClient
    -> DataResponse
    -> DataEngine.response
    -> historical TradeTick topic
    -> Actor.handle_historical_trade_tick()
    -> Actor completion callback
    -> pending request cleanup
```

A05/x03 required this integration proof.

The project testing contract also says Tier 1 should protect public adapter
wiring/lifecycle and should not treat wrapper-level or heavily patched coverage
as proof of Nautilus-level support.

## Required correction

Add one deterministic Tier-1 integration test using the existing fake RPyC
bridge and the real Nautilus request/response plumbing.

Do **not** monkeypatch `_handle_trade_ticks()` in this test.

Use a minimal test Actor (or the project's existing DataTester infrastructure)
which:

- records historical TradeTicks received through `on_historical_data`;
- records completion callback request IDs;
- exposes enough state for assertions.

### Required cases

#### Non-empty bounded request

Assert:

```text
request ID == completion callback ID
historical TradeTicks reach the Actor
Actor receives only ticks inside [start, end]
pending request is completed once
```

#### Empty bounded request

Assert:

```text
zero historical TradeTicks delivered
completion callback still fires exactly once
request is no longer pending
```

This is the crucial semantic difference between empty success and failure.

#### Sequential bounded requests

Issue two non-overlapping requests sequentially.

Assert:

```text
each callback correlates to its own request ID
first request is fully completed before second completion
historical subscriptions/request state do not leak
```

### Failure case

A provider failure must produce no fake successful DataResponse/callback.

Because Nautilus 1.227.0 does not provide an error DataResponse for this async
failure path, do not wait forever inside this adapter-only Tier-1 test. Assert
that no success callback is emitted within a short deterministic harness-owned
observation window, then explicitly clean up the test Actor/node state.

B07 owns the production timeout which converts this absence of completion into
terminal warmup failure.

---

# 4. RELEASE-GATE ERROR — the historical/live parity gate is not implemented yet

## Problem

The new module:

```text
homologation/support/a05_trade_tick_parity.py
```

contains:

- `TradeTickParitySample`;
- projection of a TradeTick;
- `compare_trade_tick_streams(live_ticks, historical_ticks)`.

This is a useful comparator, but it is **not yet the homologation harness
specified by A05/x03**.

It does not:

- subscribe to the real live feed;
- capture the effective live TradeTick stream;
- choose/record a shared logical interval;
- wait for that interval to become queryable historically;
- request A05 history for the same interval;
- invoke the comparator itself;
- write a pass/fail homologation report.

The committed AMP runner explicitly says it does not certify live/historical
parity.

At the same time, `docs/data_capability_matrix.md` currently says:

```text
A05 live↔hist parity stream: harness ready,
full parity gate still optional follow-up
```

The second clause is incorrect.

Full historical/live TradeTick parity is **mandatory before the provider runtime
can be certified for B07 warmup**.

## Required correction

Choose one of these two honest states for this branch.

### Preferred: complete the homologation runner

Add a real Tier-1.5 runner, for example:

```text
homologation/run_a05_trade_tick_parity.py
```

It must capture the **effective live adapter output**, not just raw WS rows.

Live side:

```text
MQL5 feed
-> parsing
-> InboundFeedHandler
-> TickBatchMessage
-> route_wire_tick_to_nautilus
-> emitted TradeTick list
```

Historical side:

```text
same completed logical interval
-> A05 bounded request
-> copy_ticks_range(COPY_TICKS_TRADE)
-> route_wire_tick
-> wire_tick_to_trade_tick
-> emitted TradeTick list
```

Compare ordered samples using the existing helper:

```text
accepted event count
ts_event
equal-timestamp multiplicity
price.raw
size.raw
aggressor_side
```

The runner must persist:

```text
adapter commit
MetaTrader5 package version
terminal build
broker/server
VenueProfile
instrument
capture start/end
live count
historical count
first mismatch, if any
PASS/FAIL
```

Run it on every provider surface that will later receive
`runtime.warmup != None`.

### Acceptable temporary state: leave the gate pending

If the real parity capture cannot be run now:

- keep the comparator helper;
- rename/document it as a comparator, not a ready homologation harness;
- change the capability matrix to:
  ```text
  bounded A05 real-provider request: PASS on AMP ENQU26
  full historical/live stream parity: PENDING — mandatory before warmup certification
  ```
- do not describe parity as an optional follow-up;
- do not mark any TradingUltimate runtime as warmup-certified.

## Important reason

The existing live path contains `InboundFeedHandler` processing before
conversion. It includes its own tick dedup/filter behavior.

The historical A05 helper does not pass through that handler.

Therefore reusing the same converter is necessary but not sufficient to prove
that the **effective emitted streams** are equivalent.

---

# 5. SMALL PRODUCTION FIX — wrap `route_wire_tick()` failure as `MT5HistoricalDataError`

## Problem

In `get_historical_trade_ticks_range()` the code currently does:

```python
decision = route_wire_tick(instrument, wire)
if not decision.emit_trade:
    continue

try:
    trade = wire_tick_to_trade_tick(...)
except Exception as exc:
    raise MT5HistoricalDataError(...) from exc
```

Only the converter is inside the controlled-error boundary.

`route_wire_tick()` reads instrument metadata and performs conversions such as:

```python
int(info.get("trade_mode", 4))
```

so malformed provider/instrument metadata can raise before the existing wrapper.

That would violate the A05 failure invariant that supported bounded-operation
routing/conversion failures surface as `MT5HistoricalDataError`.

## Required correction

Put the routing and conversion in the same controlled boundary:

```python
try:
    decision = route_wire_tick(instrument, wire)
    if not decision.emit_trade:
        continue

    trade = wire_tick_to_trade_tick(
        instrument,
        wire,
        batch_ts_init,
        map_tick_flags_to_aggressor=map_tick_flags_to_aggressor,
    )
except Exception as exc:
    raise MT5HistoricalDataError(
        f"Failed routing/converting MT5 historical trade row at index={index}",
    ) from exc
```

Then append only if `trade is not None`.

Add a deterministic test with malformed routing-relevant instrument metadata and
assert the public bounded helper raises `MT5HistoricalDataError`, not the raw
inner exception.

---

# 6. Documentation/test metadata cleanup

These are not architectural blockers, but fix them in the same surgical pass.

## `test_data_tester_matrix_external_rpyc.py`

Its module header still says:

```text
TC-D30/D31 TradeTick — Partial/Undecided
```

even though the same file now contains XP/AMP D30/D31 and A05 bounded tests.

Update the header so the executable specification matches the file.

## `docs/data_capability_matrix.md`

After fixing the transport and rerunning AMP:

- remove the statement that EXTERNAL_RPYC "requires allow_pickle";
- record the safe wire materialization strategy;
- keep bounded AMP evidence separate from full live/historical parity evidence;
- parity must be `PENDING` until the complete runner passes.

## Commit/report wording

Do not call A05 fully release-complete while mandatory real stream parity remains
pending.

Preferred distinction:

```text
A05 implementation: deterministic code-complete
A05 bounded real-provider operation: PASS for tested AMP interval
A05 historical/live stream parity: PENDING or PASS
B07 provider warmup certification: BLOCKED until parity PASS
```

---

# 7. Regression matrix after corrections

Run the existing deterministic suite plus the new cases.

At minimum:

```text
tests/unit/test_a05_bounded_trade_ticks.py
tests/integration/test_external_rpyc_data_flow.py
tests/integration_tests/adapters/mt5/test_data_tester_matrix_external_rpyc.py
tests/support/test_fake_mt5_rpyc_bridge.py
```

Add:

```text
safe EXTERNAL_RPYC ndarray reconstruction tests
Actor/DataEngine bounded historical request integration tests
route_wire_tick controlled-error test
```

Also rerun existing historical QuoteTick, count-based TradeTick and bar tests to
ensure the safe RPyC transport change does not alter their legacy semantics.

No CI status checks were reported for reviewed head `023249f6...`; do not use
the commit message's `25 passed` as a substitute for the project's normal full
regression command.

---

# 8. Acceptance after this review

The branch can be accepted as the adapter-side A05 implementation when:

- [ ] `allow_pickle=True` has been removed from both RPyC bridge files;
- [ ] EXTERNAL_RPYC `copy_ticks_range()` safely reconstructs an exact local
      NumPy ndarray without pickle;
- [ ] LOCAL_PYTHON behavior remains unchanged;
- [ ] existing A05 unit tests still pass;
- [ ] real Actor/DataEngine non-empty bounded request passes;
- [ ] real Actor/DataEngine empty bounded request completes exactly once;
- [ ] sequential request cleanup/correlation passes;
- [ ] routing/conversion failures are consistently `MT5HistoricalDataError`;
- [ ] capability-matrix wording no longer calls full parity optional;
- [ ] AMP bounded homologation is rerun using the safe transport;
- [ ] full live/historical parity is either PASS or explicitly PENDING;
- [ ] no TradingUltimate runtime is warmup-certified while parity is PENDING.

---

# 9. Sources used for this review

Repository sources at `melhorando-historico`:

```text
MQL5/refactoring/bridge/mt5_bridge_v008.py
nautilus_mt5/metatrader5/MetaTrader5.py
nautilus_mt5/metatrader5/utils.py
nautilus_mt5/client/market_data.py
nautilus_mt5/data.py
nautilus_mt5/tick_routing.py
nautilus_mt5/feed/handler.py
tests/integration_tests/adapters/mt5/test_data_tester_matrix_external_rpyc.py
tests/integration/test_external_rpyc_data_flow.py
homologation/run_amp_a05_bounded.py
homologation/support/a05_trade_tick_parity.py
homologation/last_amp_a05_bounded_report.json
docs/testing_contract.md
docs/data_capability_matrix.md
AGENTS.md
```

External contracts checked:

```text
NautilusTrader adapter developer guide
NautilusTrader testing guide
NautilusTrader Data Testing Spec / TC-D31
NautilusTrader v1.227.0 Actor/DataClient request-response source
RPyC Server API
RPyC protocol configuration
RPyC brine serializer
```
