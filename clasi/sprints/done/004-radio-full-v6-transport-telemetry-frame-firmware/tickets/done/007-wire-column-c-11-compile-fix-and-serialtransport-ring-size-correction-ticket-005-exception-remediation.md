---
id: '007'
title: Wire::Column C++11 compile fix and SerialTransport ring-size correction (ticket
  005 exception remediation)
status: done
use-cases:
- SUC-003
- SUC-005
- SUC-006
- SUC-007
depends-on: []
github-issue: ''
issue: radio-speaks-full-v6-and-v6-gets-its-telemetry-frame.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Wire::Column C++11 compile fix and SerialTransport ring-size correction (ticket 005 exception remediation)

## Description

Ticket 005 (Phase C bench checkpoint) threw an exception (`surface:
internal`) instead of producing a flashable hex: `uv run python
tools/make_deploy.py` failed with ~20 identical hard C++ compile errors,
on BOTH real build targets (legacy mbed-classic/yotta
`bbc-microbit-classic-gcc` and codal-microbit-v2), at every
`columns_[i++] = {...}` line inside `WireAdapter::buildSnapshot()`
(`src/wire_adapter.cpp:539-579`). Root cause and a second, independently
confirmed defect are both fixed here so ticket 005 can be re-run and
actually complete this sprint's stated Phase C goal. Full diagnosis is
in ticket 005's own `exception:` frontmatter block — read it first if
anything below is unclear.

This ticket depends on nothing (every other ticket in this sprint is
already `done`); it must land, and the full suite plus a real
`make_deploy.py` build must both go green, before ticket 005 can be
recovered and re-attempted.

### Defect A — `Wire::Column` is not an aggregate under C++11 (blocking)

`Wire::Column` (`src/wire_handler.h:157-161`, added by ticket 004) is:

```cpp
struct Column {
  const char* name = "";
  int32_t value = 0;
  bool hex = false;
};
```

Default member initializers (NSDMIs) disqualify a class from being an
aggregate under **C++11** — the standard BOTH real embedded toolchains
compile with (`-std=c++11` is baked into the pxt-microbit target's own
yotta/CMake toolchain files, not overridable from this project's
`pxt.json`). That makes the ~20 `columns_[i++] = {"seq", ..., false};`
sites in `WireAdapter::buildSnapshot()` neither valid
aggregate-initialization nor constructible via any declared
constructor — GCC's own notes confirm `Column`'s only two candidate
`operator=`s are its implicit copy/move assignment, neither of which
accepts a braced-init-list. C++14 restored the aggregate rule, which is
why `tests/host/` (compiled at `-std=c++20`,
`tests/host/test_kernel_harness.py:72`) never caught this — 253 host
tests pass against code that cannot be compiled for a robot at all. This
whole class of gap is now tracked as its own issue,
`host-tests-compile-newer-standard-than-target.md` (filed against sprint
008) — do not attempt to fix that broader gap here; see Out of Scope.

**Chosen fix: give `Column` an explicit defaulted default constructor
plus a 3-argument converting constructor, and keep the existing
NSDMIs.**

```cpp
struct Column {
  const char* name = "";
  int32_t value = 0;
  bool hex = false;

  Column() = default;
  Column(const char* name_, int32_t value_, bool hex_)
      : name(name_), value(value_), hex(hex_) {}
};
```

Why this fix over the alternatives:
- **Dropping the NSDMIs** would restore aggregate status, but every
  member array of `Column` declared with no initializer
  (`Wire::Column columns_[kMaxSnapshotColumns];` in `wire_adapter.h:404`;
  `Wire::Column cols[kShimMaxColumns];` in
  `tests/host/wire_grammar_shim.cpp:100`) would then hold indeterminate
  values until every element is explicitly assigned — a correctness
  regression waiting to happen the next time someone adds a column
  without updating every fill site.
- **Field-by-field assignment** at all ~20 call sites in
  `wire_adapter.cpp` works without touching `Column` at all, but is 20x
  the surface area for a typo (a copy-pasted wrong field, a
  transposed `value`/`hex`) versus a single 6-line struct change, for no
  benefit — the existing `columns_[i++] = {"name", value, hex};` call
  sites are already correct today; the goal is to keep them compiling,
  not to rewrite them.
- **The chosen fix requires ZERO changes to any of the ~20 call sites**
  in `wire_adapter.cpp` (they already pass exactly 3 positional
  arguments matching the new converting constructor's signature) and
  ZERO changes to `tests/host/wire_grammar_shim.cpp` (which
  default-constructs `Wire::Column cols[kShimMaxColumns];` then
  field-assigns — unaffected by adding constructors, since the
  explicit `Column() = default;` keeps default-construction working
  exactly as it silently relied on the implicit one before). Verified:
  no `Column{...}` or `Column(...)` call site anywhere in this repo
  passes fewer than 3 arguments — grep confirms every existing brace-init
  site is the full 3-argument form, so the converting constructor's
  signature has no partial-brace-init call site to break.
- `Wire::Snapshot` (`wire_handler.h:171-174`) has the identical NSDMI
  shape and is therefore ALSO not an aggregate under C++11, but it is
  never brace-initialized anywhere in `src/` or `tests/host/` (every
  site does `Wire::Snapshot snapshot; snapshot.columns = ...;
  snapshot.count = ...;` field-by-field) — confirmed by repo-wide grep.
  Leave `Snapshot` as-is; it is not a live defect, just a latent
  structural twin of `Column`'s. Do not "fix" it preemptively — that
  would be scope creep against a struct that has no actual call site to
  break.

### Defect B — `SerialTransport`'s ring size silently truncates (confirmed real)

`src/serial_transport.cpp:47-48` calls
`uBit.serial.setRxBufferSize(kRingBytes)` /
`setTxBufferSize(kRingBytes)` with `kRingBytes = 2 * kMaxLineBytes =
480` (`src/serial_transport.h:46`). Ticket 006 flagged this as
UNVERIFIED (comment at `serial_transport.cpp:37-46`). The build log's own
`-Woverflow` warning ("large integer implicitly truncated to unsigned
type") plus codal-core's real header
(`inc/driver-models/Serial.h`, confirmed via `gh api repos/lancaster-
university/codal-core/contents/...`) now CONFIRM the real signatures:

```cpp
int setRxBufferSize(uint8_t size);
int setTxBufferSize(uint8_t size);
```

`uint8_t` caps at 255. `480 & 0xFF = 224` — **below**
`kMaxLineBytes` (240) — so ticket 006's ring-resize was silently
producing a ring SMALLER than one full v6 line, defeating its entire
purpose with nothing but an easy-to-miss compiler warning as the signal.

**Chosen fix: set `kRingBytes` to the hard ceiling (255), change its
type to `uint8_t` to match the real API, and use brace-initialization so
any future attempt to raise it past 255 is a hard compile error, not a
repeat of this exact silent truncation.**

```cpp
// Hard ceiling: codal-core's setRxBufferSize()/setTxBufferSize() take
// uint8_t (inc/driver-models/Serial.h), so this can never legally
// exceed 255. This is NOT 2x kMaxLineBytes (240) -- that was ticket
// 006's original, unachievable intent (480 truncates to 224 on assignment
// to a plain `size_t`, an even smaller ring than intended). 255 leaves
// only 15 bytes of headroom above one full 240-byte line -- enough for
// one maximal line plus a little slack, NOT enough to hold two full
// lines concurrently. Brace-init (not `=`) makes any future edit that
// pushes this past 255 a HARD COMPILE ERROR (narrowing conversion in a
// constant expression) instead of a silent -Woverflow warning easy to
// miss in a build log -- exactly what happened here.
constexpr uint8_t kRingBytes{255};
```

Honest cost, to state explicitly in this ticket's own notes and carried
into ticket 005's bench checklist: the ring can absorb one full-length
line with only 15 bytes of slack, not the 2x margin ticket 006 intended.
If a second maximal-length line arrives before the first is drained by
the protocol/TS fibers' polling, overflow is still possible — this is a
known, documented residual limitation of the codal-core `uint8_t` API
ceiling, not something this ticket engineers further around (out of
scope — see below). Update the stale doc comments at
`serial_transport.cpp:27-46` and `serial_transport.h:37-46` (the "2x
kMaxLineBytes" claim and the "UNVERIFIED" flag) to state the confirmed
real signature and the corrected 255-byte ceiling and its cost, instead
of leaving them describing an intent that turned out to be
unachievable.

### Recurrence guard (should-if-cheap, not a gate)

Add a `-std=c++11 -fsyntax-only` compile of this project's HOST-PORTABLE
`src/` translation units as a new host test — this would have caught
Defect A before a build checkpoint did. Scope this to exactly the files
already known to have no `pxt.h`/CODAL dependency (confirmed by repo
grep and by their own header comments): `src/diffdrive.cpp`,
`src/motion_engine.cpp`, `src/wire_handler.cpp`, `src/wire_adapter.cpp`.
These are the same four files `tests/host/`'s existing suite already
compiles successfully at `-std=c++20` — this only adds a second,
syntax-only compile of the identical files at the target's real
standard, no shim/link step needed (`-fsyntax-only` needs no `-shared
-fPIC -o`, just `-I src`). Do NOT extend this to `protocol.{h,cpp}`,
`radio_transport.{h,cpp}`, `serial_transport.{h,cpp}`, `shims.cpp`,
`nezha_port.{h,cpp}`, or `otos_port.{h,cpp}` — all of those include
`pxt.h` (directly or transitively via `platform_ports.h`) and cannot be
syntax-checked without the CODAL toolchain, which this repo's host
suite does not have.

This is judged genuinely cheap because: it is a fixed, already-enumerated
4-file list (not a moving target), it needs no new fixture or shim code
(the files already compile clean at C++20 with no test-only headers), and
after this ticket's Defect A fix these exact four files are expected to
already pass at C++11 with no further changes. **If it turns out NOT to
be cheap** (surprising C++14+ construct surfaces in one of these four
files beyond Column, or the syntax-only invocation needs more plumbing
than expected), STOP and drop it from this ticket's scope rather than
letting it grow — the systemic fix is already filed as
`host-tests-compile-newer-standard-than-target.md` against sprint 008;
this ticket's job is Defects A and B, not that issue's full resolution.

## Acceptance Criteria

- [x] `Wire::Column` (`src/wire_handler.h`) has an explicit
      `Column() = default;` and a 3-argument converting constructor
      `Column(const char*, int32_t, bool)`, with its existing NSDMIs
      unchanged. No call site in `src/wire_adapter.cpp` or
      `tests/host/wire_grammar_shim.cpp` is modified.
- [x] `Wire::Snapshot` is left unchanged — its own doc comment (or a
      one-line addition to it) notes it shares Column's NSDMI/aggregate
      quirk but has no live call site that triggers it, so it is
      intentionally not "fixed" here.
- [x] `src/serial_transport.h`'s `kRingBytes` is `constexpr uint8_t
      kRingBytes{255};` (brace-initialized), no longer `2 *
      kMaxLineBytes`. `kMaxLineBytes` itself is untouched (its
      cross-file duplication is `wire-constants-single-source.md`,
      sprint 008 — out of scope here).
- [x] `src/serial_transport.cpp`'s `begin()` doc comment and
      `src/serial_transport.h`'s `kRingBytes` doc comment are updated to
      state the CONFIRMED real `uint8_t` signature (no longer
      "UNVERIFIED"), the 255-byte ceiling, and the honest ~15-byte
      single-line-only headroom cost — not the original "2x" claim.
- [x] `uv run pytest` (full suite) passes at the same 253-test baseline
      (or higher, if the recurrence guard below is included), with no
      regressions in `tests/host/test_wire_telemetry_frame.py`,
      `tests/host/test_wire_telemetry_projection.py`, or the shared
      `tests/host/golden_telemetry.py` fixture ticket 004 built.
- [x] `uv run python tools/make_deploy.py` produces a flashable hex,
      retrying once if the documented nondeterministic `TS9283`
      packaging abort occurs (expected, not a bug) — but treating any
      OTHER compile error (like this ticket's own Defect A) as a real
      failure, not something to retry past.
- [x] Either: (a) a new host test performs a `-std=c++11 -fsyntax-only`
      compile of `src/diffdrive.cpp`, `src/motion_engine.cpp`,
      `src/wire_handler.cpp`, and `src/wire_adapter.cpp`, and passes; or
      (b) this ticket's own notes state plainly that it was dropped
      because it stopped being cheap, and why.
- [x] This ticket's own notes state which fix was chosen for each defect
      and why (do not leave either fix undocumented for the next
      reader — this is exactly the kind of decision ticket 005's
      exception said could not be made inside a checkpoint ticket).

## Implementation Notes

**Defect A (`Wire::Column`)**: implemented exactly as planned —
`Column() = default;` plus the 3-argument converting constructor,
NSDMIs kept. Verified by repo grep before editing: all 20
`columns_[i++] = {"name", value, hex};` sites in
`WireAdapter::buildSnapshot()` (`src/wire_adapter.cpp:539-579`) pass
exactly 3 positional args; `wire_adapter.h:404`'s
`Wire::Column columns_[kMaxSnapshotColumns];` and
`tests/host/wire_grammar_shim.cpp:100`'s `Wire::Column
cols[kShimMaxColumns];` both only default-construct. **Zero call-site
changes were required, confirming the plan's prediction exactly.**
`Wire::Snapshot` was left untouched except for a one-line doc-comment
addition noting the shared NSDMI/aggregate quirk with no live call site
— per the ticket's own explicit instruction not to "fix" it.

**Defect B (`SerialTransport::kRingBytes`)**: implemented exactly as
planned — `constexpr uint8_t kRingBytes{255};` (brace-init preserved
deliberately, so any future push past 255 is a hard compile error, not
a repeat of the silent `-Woverflow` truncation that caused this
defect). Doc comments in both `serial_transport.h` and
`serial_transport.cpp`'s `begin()` were rewritten to state the
CONFIRMED real `uint8_t` signature (no longer "UNVERIFIED"), the
255-byte ceiling, and the honest ~15-byte single-maximal-line-only
headroom — explicitly NOT the 2x-`kMaxLineBytes` margin ticket 006
intended, so no future reader mistakes the ring for holding two full
lines concurrently.

**Recurrence guard**: kept — it stayed exactly as cheap as sized.
Added `tests/host/test_cxx11_syntax_gate.py`, a parametrized
`-fsyntax-only` compile of the four named files at `-std=c++11` via a
plain `subprocess.run(["/usr/bin/c++", "-std=c++11", "-fsyntax-only",
"-I", "src", <file>])` — no shim, no link step, no new fixture. After
the Defect A fix, all four files
(`diffdrive.cpp`/`motion_engine.cpp`/`wire_handler.cpp`/
`wire_adapter.cpp`) compile clean at C++11 with zero additional
findings beyond `Column` — no other C++14+ construct surfaced. Full
suite: 253 baseline + 4 new parametrized cases = 257 passed, no
regressions.

**`uv run python tools/make_deploy.py`**: produced a real flashable hex
(`.tmp/deploy-head/built/mbcodal-binary.hex`, 1,332,476 bytes,
well-formed Intel HEX). One retry was needed: attempt 1 aborted during
hex packaging (a `srec_cat`/pxt-core cache-write failure chained into a
`TS9043` "hex file is not available, please connect to internet"
error) with `make_deploy.py`'s own generic "BUILD PRODUCED NO HEX --
... Just run it again" message — this is the class of nondeterministic
packaging abort the ticket anticipates, NOT a repeat of Defect A: both
attempts compiled every one of this project's `.cpp` files
(`wire_adapter.cpp`, `wire_handler.cpp`, `serial_transport.cpp`
included) with zero errors on both real build variants run in
parallel — no `operator=`/brace-init errors anywhere, confirming Defect
A is fixed on the actual embedded toolchain, not just at
`-fsyntax-only`. The legacy V1 `bbc-microbit-classic-gcc` variant
itself still fails at its own hex-merge step in both attempts (a
`srec_cat: contradictory ... value` / `TS9200` error) — this matches
`make_deploy.py`'s own docstring, which documents that variant's V1
build as an expected, harmless failure this deploy configuration
deliberately keeps enabled; the codal-microbit-v2 variant is the one
that must (and did) produce the real hex.

**No behavior change**: `Column`'s and `kRingBytes`'s observable shape
(field names/order/values; the wire bytes any test or on-wire consumer
sees) is unchanged, so no existing test assertion needed updating — the
253-test baseline passed unmodified.

## Out of Scope

- Converting the whole host suite to compile at `-std=c++11` (the
  broader fix in `host-tests-compile-newer-standard-than-target.md`,
  sprint 008).
- Radio RX fragmentation (`radio-rx-capacity-fragmentation.md`, sprint
  010).
- The `kMaxLineBytes` cross-file duplication
  (`wire-constants-single-source.md`, sprint 008).
- Any change to `src/DESIGN.md` (handled separately by the team-lead).
- Re-engineering `SerialTransport`'s two-writer guard or ring strategy
  beyond the size/type/brace-init correction above — the residual
  "can't hold two full lines" limitation is documented, not solved,
  per this ticket's own honest-cost statement.
- Flashing or hardware validation — this remains a BUILD checkpoint;
  once this ticket lands, ticket 005 (not this ticket) re-attempts the
  bench checkpoint.

## Testing

- **Existing tests to run**: `uv run pytest` (full suite; this is a
  firmware-wide structural fix touching a value type shared by every
  telemetry test, so a scoped subset is not sufficient — run the whole
  suite, matching this project's once-per-ticket testing rule for a
  change of this shape). Pay particular attention to
  `test_wire_telemetry_frame.py`, `test_wire_telemetry_projection.py`,
  `test_wire_per_transport_isolation.py`, and `test_wire_grammar.py`
  (all consume `Wire::Column`/`Wire::Snapshot` shapes directly or via
  `wire_grammar_shim.cpp`/`wire_motion_verb_shim.cpp`).
- **New tests to write**: the recurrence-guard C++11 syntax-check test
  described above, if it stays cheap (see Acceptance Criteria). No new
  runtime-behavior tests are expected — this ticket is a type-system/
  constant-value correction, not a behavior change; `Column`'s
  observable shape (field names, order, values) is unchanged, so no
  existing assertion should need updating.
- **Verification command**: `uv run pytest && uv run python
  tools/make_deploy.py` (retry `make_deploy.py` once only on the
  documented `TS9283` abort).

## Implementation Plan

**Approach**:
1. Edit `src/wire_handler.h`'s `Column` struct: add `Column() =
   default;` and the 3-argument converting constructor, per Defect A's
   chosen fix above. Leave every other line of the file (including
   `Snapshot`) untouched except the one-line note on `Snapshot`'s
   comment block acknowledging the shared quirk.
2. Edit `src/serial_transport.h`: change `kRingBytes`'s declaration to
   `constexpr uint8_t kRingBytes{255};` and rewrite its doc comment.
   Edit `src/serial_transport.cpp`'s `begin()` doc comment to match
   (confirmed signature, 255 ceiling, honest cost).
3. Run `uv run pytest` — expect the existing 253 to stay green with no
   source changes needed beyond the two structs/constants above (this
   ticket is not expected to require any test file edits, since
   `Column`'s and `kRingBytes`'s external behavior/shape is unchanged).
4. If the recurrence guard stays cheap per its own sizing note above,
   add it as a new `tests/host/test_*.py` file following this project's
   existing host-test naming and `subprocess.run([...])` conventions
   (mirroring `tests/host/test_kernel_harness.py`'s `compile_shared_lib`
   pattern, but with `-fsyntax-only` and no shared-lib output needed).
5. Run `uv run python tools/make_deploy.py`, retrying once only on the
   documented `TS9283` abort. Confirm the hex is produced with no
   further compile errors.
6. Record in this ticket's own notes: which fix was chosen for each
   defect (already drafted above — copy forward, adjust only if
   implementation surfaced something this planning pass missed), the
   final `kRingBytes` value and its cost, and whether the recurrence
   guard was included or dropped (and why, if dropped).

**Files to modify**:
- `src/wire_handler.h` (Column constructors; Snapshot comment note)
- `src/serial_transport.h` (`kRingBytes` type/value/comment)
- `src/serial_transport.cpp` (`begin()` doc comment)
- Possibly one new `tests/host/test_*.py` file (recurrence guard, if
  kept cheap)

**Testing plan**: see Testing section above.

**Documentation updates**: none under `docs/design/` — this is a
firmware-internal type/constant fix with no change to the student-facing
block API, `specification.md`, or the wire GRAMMAR any host parses. The
doc-comment corrections inside `src/serial_transport.{h,cpp}` themselves
(see Acceptance Criteria) are this ticket's only "documentation" output,
and they live in source, not `docs/`.
