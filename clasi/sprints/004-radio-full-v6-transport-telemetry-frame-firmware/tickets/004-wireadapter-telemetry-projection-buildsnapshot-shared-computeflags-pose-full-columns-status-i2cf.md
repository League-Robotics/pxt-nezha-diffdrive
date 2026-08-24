---
id: '004'
title: 'WireAdapter telemetry projection: buildSnapshot, shared computeFlags, POSE/FULL
  columns, STATUS i2cf='
status: open
use-cases: [SUC-003, SUC-004, SUC-005]
depends-on: ["003"]
github-issue: ''
issue:
- radio-speaks-full-v6-and-v6-gets-its-telemetry-frame.md
- status-lost-diag-numeric-surface.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# WireAdapter telemetry projection: buildSnapshot, shared computeFlags, POSE/FULL columns, STATUS i2cf=

## Description

This is where the SCALE FACTORS live, and where both issues this
sprint closes actually get closed. Add `WireAdapter::buildSnapshot()`
(returns `const Wire::Snapshot&`, mirroring the reference's
`DiffDriveAdapter::buildSnapshot()`) and `telemetryEnabled()` (true iff
`mode_ != Wire::TlmMode::kOff`) as new public methods. Extract the
existing inline flags computation inside `status()`
(`wire_adapter.cpp` ~lines 236-245) into a standalone `computeFlags()`
free function, called from BOTH `status()` (unchanged behavior) and
`buildSnapshot()` (new) — so `STATUS`'s `flags=` and the telemetry
`flags` column can never disagree, because they are now the same
function call, not two copies. Add `i2cf=<n>` to `STATUS`'s reply,
read via the ALREADY-forward-declared `diagValue(8)` (this closes
`status-lost-diag-numeric-surface.md`).

Reach live robot state through FIVE new same-package forward
declarations in `wire_adapter.cpp`'s existing forward-declaration block
(mirroring the `diagValue`/`setWheelsTimed`/etc. convention already
there): `int poseX(); int poseY(); int poseHeading(); int
otosGet(int); int wheelSpeed(int);` — all five already exist in
`shims.cpp` today; this ticket adds ZERO new entry points there.

**Correction (code review 2026-08-23, R-22/WIRE-06, CONFIRMED):**
`wire_adapter.cpp:226` currently hardcodes `out.otos = false;` in
`status()`, with a comment claiming "no OTOS in this project's
wire-reachable surface yet." That claim is false as of this same
session: `shims.cpp:891-892`'s `engineGoToW()` already gates on
`otosRef().connected()`, and `shims.cpp:970`'s `otosGet(7)` already
returns that exact connected/disconnected boolean (`o.connected() ? 1 :
0`) — an entry point this same ticket is already forward-declaring for
`ox`/`oy`/`oh`. So `STATUS` can end up telling a bench operator "no
OTOS" while `GO_TO_W` is actively using one, which would misroute
sprint 005's closed-loop tooling if left uncorrected. Since this
ticket's own forward declaration for `otosGet(int)` already exists,
fixing this costs one line, not a new shim entry point: replace
`out.otos = false;` with `out.otos = otosGet(kOtosConnected) != 0;`
(add `constexpr int kOtosConnected = 7;` alongside this file's existing
`kDiag*` constants), and delete the now-false "no OTOS" comment. `otos`
is a `StatusFields` field independent of `flags`/`computeFlags()` and
is not part of any telemetry column — this fix is scoped to `status()`
alone; `buildSnapshot()` needs no change for it.

POSE columns (12): `seq now flags x y h ox oy oh vl vr i2cf`. FULL adds
8 more (20 total): `cyc posl posr dutl dutr lexc wrng cycovr`, all
sourced from the already-forward-declared `diagValue()` (ordinals 16,
10, 11, 12, 13, 9, 25, 19 respectively — see `shims.cpp`'s own
`diagValue()` switch for the field list). `vl`/`vr` sit in POSE, not
FULL — wheel speed must NEVER be re-derived by differencing the pose
stream (this project's own measured 24 ms-tick-sampled-at-~56 ms
aliasing failure), so the correct instrument belongs on the default
channel.

`seq` wraps `(seq_ + 1) & 0x7F` (mirroring the reference,
`protocol.md` §6.2) — this is THIS ticket's responsibility, not
ticket 003's: the handler just prints whatever value it is given; the
adapter is what advances and wraps it.

**Three hazards, each with real debugging history on this project** —
comment all three at the forward-declaration block:
- `poseX()`/`poseY()`/`poseHeading()` each call `odomUpdate()` — this is
  LOAD-BEARING (between moves, nothing else advances odometry; the
  telemetry tick is what keeps pose current when idle). Do not collapse
  three calls into one cached read.
- `otosGet(0)`/`otosGet(1)` are 0.1 mm (divide by 10 for `ox`/`oy`);
  `otosGet(2)` is ALREADY centidegrees (`oh` — do not also divide it).
- `otosGet()` reads a CACHE. The protocol fiber must NEVER call
  `otosRead()` — an I2C transaction interposed in the Nezha encoder's
  select->read window destroys the sample (Phase F). Add the "otosRead
  appears nowhere in wire_adapter.cpp" test below specifically because
  this is a one-careless-line-away, catastrophic, SILENT failure mode.

Also produce `tests/host/golden_telemetry.py`: a shared fixture (real
input values through the real projection + real formatting, byte-exact
expected `thdr`/`t` lines) that BOTH this ticket's own C++-driven pytest
test imports AND sprint 005's future Python parser test will import —
so the emitter and the (future) parser cannot silently drift apart.

## Acceptance Criteria

- [ ] `WireAdapter::buildSnapshot()` returns a `const Wire::Snapshot&`
      built from live state via the five new forward declarations;
      `telemetryEnabled()` returns `mode_ != Wire::TlmMode::kOff`.
- [ ] `WireAdapter::status()`'s `out.otos` reflects real OTOS
      connectivity (`otosGet(kOtosConnected)`, ordinal 7) instead of the
      current hardcoded `false` (R-22/WIRE-06 — see Description). A
      test using a new settable OTOS-connected test double asserts
      `STATUS`'s `otos=` value is `0` when disconnected and `1` when
      connected, not unconditionally `0`.
- [ ] `computeFlags()` is a standalone function (same bit layout as
      today's inline version — this ticket MOVES it, does not
      redefine it) called from both `status()` and `buildSnapshot()`.
- [ ] `Wire::StatusFields` (`wire_handler.h`) gains an `int32_t i2cf =
      0;` field, alongside the existing `flags`; `execStatus()`'s
      snprintf format string (`wire_handler.cpp`) gains `i2cf=%ld` in
      its existing `k=v` reply, populated the same way every other
      `StatusFields` member already is — the handler stays the ONLY
      place that assembles wire text; the adapter only fills the
      struct. `WireAdapter::status()` sets `out.i2cf = diagValue(8);`.
      `protocol.md` §6.1's "order not guaranteed, unknown keys ignored"
      already covers backward compatibility for the new key.
- [ ] `src/protocol.cpp`'s periodic-emission block is updated to the
      REAL conditional: if `wireAdapter_.telemetryEnabled()`, call
      `wireAdapter_.buildSnapshot()` ONCE per tick and pass the SAME
      `Snapshot` reference to BOTH handlers' `emitTelemetry(snapshot)`;
      otherwise call `emitReliability()` on each, as ticket 003 left
      it. (See `sprint.md`'s Design Rationale for why `buildSnapshot()`
      is called once per tick, not once per handler.)
- [ ] Six scale tests (verbatim from the issue's Verification table —
      each test's setter takes RAW shim units so the test is not
      tautological):

  | test | input | expects | catches |
  |---|---|---|---|
  | OTOS 0.1mm→mm | raw `1234,-5678,9000` | `123 -567 9000` | missing `/10`; `/100`; round-half → `-568` |
  | pose passthrough | `123,-45,6789` | unchanged | accidental scaling |
  | `h`/`oh` both cdeg | `9000` | `9000` not `90` | a deg conversion |
  | wheel speed | `440,-440` | unchanged | a `×10` copied from the reference |
  | `flags` hex | `0x2A` | ` 2a ` | `%d`, `%X`, `0x` prefix |
  | `i2cf` decimal | `26` | `26` not `1a` | wrong `hex` bit |

  Negatives specifically on `oy`/`vr` so a `static_cast<uint32_t>` slip
  shows.
- [ ] `seq` wraps `127 -> 0` over 130 frames (adapter-side test, not
      handler-side — the handler only prints).
- [ ] The widest `FULL` frame's formatted byte length is asserted
      against `RadioTransport`'s 200-byte silent-truncation cap, using
      realistic-but-large values (not a synthetic all-`INT32_MIN` frame
      — see `sprint.md`'s Open Questions for why this specific number
      is unverified at planning time and must come from a real test,
      not a guess).
- [ ] A test asserts the literal substring `otosRead` appears NOWHERE in
      `src/wire_adapter.cpp` (a source-text check, not a runtime one —
      e.g. a small pytest reading the file and asserting the substring's
      absence).
- [ ] `tests/host/golden_telemetry.py` exists, imported by a new C++-
      driven test in this ticket that feeds known raw shim inputs
      through the real `WaHandle` (`wire_motion_verb_shim.cpp`) and
      asserts the exact `thdr`/`t` bytes match the fixture.

## Implementation Plan

**Approach**: Port the reference's `buildSnapshot()` shape
(`radio-robot-lib/src/adapter/diffdrive_adapter.cpp:297-334`), adjusted
for this project's column set/units (v5-compatible plain integers, NOT
the reference's `mm/s ×10` quantum — see `sprint.md` Design Rationale),
and adjusted so `seq_`/column arrays live on `WireAdapter`, not a
reference-specific class.

**Files to modify**:
- `src/wire_adapter.h`: declare `buildSnapshot()`, `telemetryEnabled()`;
  add `seq_` (uint8_t or similar, wraps at 0x7F), a `Wire::Column
  columns_[20]` member array, a `Wire::Snapshot snapshot_` member (the
  reference's own pattern — `buildSnapshot()` returns a reference into
  a member, not a temporary).
- `src/wire_adapter.cpp`: add the five forward declarations; implement
  `buildSnapshot()`/`telemetryEnabled()`; extract `computeFlags()` out
  of `status()`'s current inline block into its own function in the
  anonymous namespace, call it from both `status()` and
  `buildSnapshot()`; set `out.i2cf = diagValue(8);` inside `status()`;
  add `constexpr int kOtosConnected = 7;` alongside the existing
  `kDiag*` constants and replace `out.otos = false;` (plus its stale
  comment) with `out.otos = otosGet(kOtosConnected) != 0;` (R-22 fix).
- `src/wire_handler.h`: add `int32_t i2cf = 0;` to `Wire::StatusFields`.
- `src/wire_handler.cpp`: extend `execStatus()`'s snprintf format
  string to include `i2cf=%ld` (matching the existing `flags=%x`-style
  formatting immediately next to it) and its buffer size accordingly.
- `tests/host/wire_motion_verb_shim.cpp` (`WaHandle`): add test-double
  definitions for the five new forward declarations
  (`waSetOtosRaw(x_01mm, y_01mm, h_cdeg)`,
  `waSetWheelSpeed(left_mms, right_mms)`, reuse the existing
  `FakePoseSource`/odometry path for `poseX`/`poseY`/`poseHeading` where
  practical, or add a settable override if the existing fake does not
  already expose one); also add `waSetOtosConnected(bool)` so the R-22
  `otos=` fix has a test double to flip (`otosGet(7)`'s fake must
  return this value, independent of the `waSetOtosRaw()` values, since
  a disconnected OTOS can still have a stale cached pose).
- `tests/host/golden_telemetry.py` (new): the shared fixture described
  above.

**Testing plan**:
- Extend `test_wire_motion_verbs.py` or add a new
  `test_wire_telemetry_projection.py` exercising the real `WaHandle`
  (`WireAdapter` + `FakeMotor` + `MotionEngine` + `FakePoseSource`) —
  this is the ticket where the real-adapter shim is required, per
  `sprint.md`'s own handler/projection test split.
- Six scale tests, `seq`-wrap test, FULL-width byte-budget test,
  `otosRead`-absence source check, the `STATUS otos=` truthfulness test
  (R-22), and the golden-frame test, all as listed in Acceptance
  Criteria above.
- **Verification command**: `uv run pytest tests/host/test_wire_motion_verbs.py tests/host/test_wire_telemetry_projection.py` (or wherever the new tests land — scoped to this ticket's modules; full suite runs once at `close_sprint`).

**Documentation updates**: `wire_adapter.h`'s file-header comment
(currently silent on telemetry) should gain a short note describing
`buildSnapshot()`/`telemetryEnabled()`'s existence and the
shared-`computeFlags()` guarantee, matching the file's existing
convention of documenting each public method's role at the top.
