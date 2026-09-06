---
id: '007'
title: 'Wire minors: telemetry terminator, RX drain/counters, handleRun refusal counter,
  seq-id wrap, GET rebase'
status: done
use-cases:
- SUC-004
depends-on:
- '006'
github-issue: ''
issue: wire-minors-telemetry-terminator-rx-counters-seq-wrap.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Wire minors: telemetry terminator, RX drain/counters, handleRun refusal counter, seq-id wrap, GET rebase

## Description

**Depends on ticket 006** — CM-07's terminator/strip-check fix applies
to "both sinks," which is simpler to do correctly once ticket 006 has
unified them into one `TransportSink`; CM-06's RX-drain fix is closely
tied to how `routeLine()` (also ticket 006) dispatches lines.

**Sprint 031 coordination — this is the sprint's real collision
point.** `GET rebase` is implemented in `WireAdapter::onGet()`
(`wire_adapter.cpp:899-911`), in the same file as sprint 031's unmerged
`resolvePendingReason()`/done-reason-latch changes. Different
functions, but a dense, tightly-commented section of the file (§5 of
`src/DESIGN.md`, "motion-completion resolution") — **read sprint 031's
actual diff before touching `wire_adapter.cpp`** if that branch is
still unmerged when this ticket runs, don't just avoid the named
functions by name.

Five independent findings, verified live 2026-09-05 (GET rebase
directly; the rest not independently re-checked line-by-line but
untouched by any intervening sprint):

- **CM-07 (terminator)**: `emitHeader()`/`emitFrame()` drop their
  trailing `\n` at exactly 239 bytes; both sinks then strip the last
  byte blind. Bound the frame append at `sizeof - 2` and write `\n`
  last; both sinks check the terminator before stripping. Extend the
  existing pathological-239-byte-frame test to assert the terminator
  survives.
- **CM-06 (RX drain)**: one inbound line drained per transport per
  pass, with silent overflow/drop and dead `rxFrames_`/`rxAccepted_`
  counters. Drain up to N lines per transport per pass through
  `routeLine()`; wire the two counters to something real, or delete
  them if nothing should read them — document the ordinals either way
  (Architecture §Open Question 3).
- **CM-08 (handleRun refusals)**: overlong/non-printable/empty-name
  payloads are refused uncounted; the 400 ms dedupe also eats a
  repeated `abort`. Add one `runMalformed_` counter incremented on all
  three refusal shapes; exempt bypass names (`abort`/`clearestop`) from
  the dedupe window.
- **CM-15 (seq wrap)**: `expectedNext_ = id + 1` wraps to 0 at
  `UINT32_MAX` with no guard (theoretical). Add the guard.
- **CM-16 (GET rebase)**: CONFIRMED — `onGet()`'s explicit early return
  for `kOrdinalRebase` (`wire_adapter.cpp:909`) answers the same
  `kUnknown`/"unknown name" a genuine typo gets, and is commented in
  the source as a deliberate choice, not an oversight. **Resolve
  Architecture §Open Question 2**: keep refusing (a stored rebase value
  doesn't exist and manufacturing one would be dishonest — the existing
  comment's own reasoning is sound), but make the refusal a
  distinguishable `Wire::Result` (e.g. `kWriteOnly`) instead of the
  generic `kUnknown`, so a host can tell "this field can't be read" from
  "this name doesn't exist." Apply the same treatment to `estop_clear`
  if it has the same refusal shape.

## Acceptance Criteria

- [x] The extended pathological-239-byte-frame test asserts the
      terminator survives (sprint Success Criteria's own bar).
- [x] RX drop/accept counters actually increment (sprint Success
      Criteria's own bar) — or are deleted, with that decision
      documented.
- [x] The sequence-id wrap is guarded (sprint Success Criteria's own
      bar).
- [x] `GET rebase` answers with a documented `kWriteOnly`-shaped code
      instead of the generic "unknown name" (sprint Success Criteria's
      own bar; real-read-path alternative rejected per Design
      Rationale — implementer may override with justification).
- [x] `handleRun()`'s refusal counter increments on each of the three
      named refusal shapes; a repeated `abort` still executes despite
      the 400 ms dedupe.
- [x] `wire_adapter.cpp` changes are confirmed rebased against sprint
      031's actual commits if that branch was still unmerged when this
      ticket started.

## Resolution

Five independent fixes; the ordinals and codes they land on are named
here so a later sprint does not have to rediscover them.

**CM-07 — terminator (emit side).** `emitHeader()`/`emitFrame()` bound
their content at `sizeof(emitBuf_) - 2` and hand the `'\n'` plus NUL to
one shared `terminateEmitBuf()`, written unconditionally into the
reserved bytes. Content truncates instead of the terminator being
dropped — the same reserve-two shape `buildHelpLine()` already used;
all three now match, and `buildHelpLine()`'s own doc comment says so.
The sink half was already done by ticket 006. `test_wire_telemetry_
frame.py` asserts the terminator on the pinned 239-byte pathological
frame and adds three cases past the cliff (overflowing `t`, overflowing
`thdr`, and a byte-by-byte sweep across the boundary) — the off-by-one
is invisible at any single length.

**CM-06 — RX drain and counters.** `Protocol::kRxDrainPerPass = 4`,
used by all three transports. Four because: one per pass meant one per
~24 ms tick while a job ran, and serial at 115200 puts ~276 bytes into
a 255-byte ring in that window; four is what the WiFi branch already
bounded itself at, so one constant now replaces three spellings; and
unbounded would starve `drainEmitQueue()` and the telemetry cadence,
which only run between passes. The counters were WIRED UP, not deleted
(Architecture Open Question 3): `rxFrames_`/`rxAccepted_`/
`rxOversizeDropped_` become `RadioRxCounters` (`frames`, `accepted`,
`oversizeDropped`, `overrunDropped` — the last one new; it is the
`if (rxReady_) return;` drop that was silent), all saturating, behind a
read-only `rxCounters()` accessor. **Diag ordinals 31, 32, 33, 34** in
that order. The decision and the bookkeeping are one host-portable free
function, `radioRxClassify()`, in `radio_transport.h` beside
`radioRxLineFits()` — host-tested in `test_radio_transport_rx_
capacity.py` (dispositions, per-counter increments, and the
`frames - accepted == oversize + overrun` invariant) and syntax-gated
at C++11 by a new `radio_rx_classify_syntax_check.cpp`. The
`onDatagram()` call site and the drain loops are review-verified
(`pxt.h`), with source-text pins in `test_wire_constants_drift.py`.

**CM-08 — RUN refusals.** `RunBridge::malformedCount()`, incremented
through one `malformed()` helper at every sanitizer refusal (overlong,
non-printable, empty name, plus the empty payload), saturating, kept
separate from the ring's capacity count. **Diag ordinal 30.** Bypass
names are now exempt from the 400 ms dedupe: a repeated `abort` inside
the window executes. Both host-tested in `test_run_bridge.py`; the
existing test that pinned the old suppression behaviour was rewritten
to pin the new one, and two tests were added proving the exemption does
not leak to ordinary names.

**CM-15 — sequence-id wrap.** `WireHandler::kMaxSequenceId`
(`UINT32_MAX`) is RESERVED: `expectedNext_` may reach it, no inbound
line may carry it, so `expectedNext_ = id + 1` cannot wrap. A line
carrying it is a decode failure — `nack` plus `err 3` (ERR_RANGE: the
shape is fine, the number is out of bounds) — and does not advance the
sequence. The guard is one public static, `sequenceIdIsExecutable()`,
which is what makes the boundary drivable from a host test at all: no
shim setter was added, because seeding `expectedNext_` through a back
door would test the back door rather than the path a line takes, and
with the guard at intake the seeded state is unreachable by
construction. Covered in `test_wire_reliability.py` (predicate at six
boundary values, plus four end-to-end cases through the real handler)
and by two new `wire_acceptance.py` bench checks.

**CM-16 — `GET rebase`.** Resolves Architecture Open Question 2 as
recommended: keep refusing, but distinguishably. `Adapter::onGet()` now
returns `Wire::Result` instead of `bool` — a bool structurally cannot
tell "no such name" from "nothing to read" — and `rebase` answers
`Wire::Result::kWriteOnly` → **wire code 12** (`Wire::kErrWriteOnly`).
12 is the first number free of the reference grammar's own 1–11 range,
deliberately not one of the 5/7/9 holes inside it. `estop_clear` does
NOT get this treatment: it has a real read path (the live estop flag)
and answers `kOk`, which a new test pins. Bare `GET` dumps are
unchanged. `resultCode()` names the constant rather than re-typing 12,
and `test_wire_constants_drift.py` pins the number across all three
places it appears.

**Sprint 031 rebase:** 031 is merged into this branch's base, so the
coordination concern is moot — `wire_adapter.cpp`'s motion-completion
section was read before editing and is untouched by this ticket
(`onGet()`'s signature and the `rebase` arm are the only changes in
that file).

**Not measured on hardware.** Every claim above is host-executed or
explicitly review-verified; nothing here was run on a robot.

## Testing

- **Existing tests to run**: the existing pathological-239-byte-frame
  test (locate via `grep -rn "239" tests/host/`); any existing `GET`/
  `SET` round-trip tests touching `rebase`/`estop_clear`.
- **New tests to write**: extended terminator test; RX-drain-N-per-pass
  test with counter assertions; `runMalformed_` counter test covering
  all three refusal shapes plus the abort-dedupe-exemption case; a
  sequence-id-wrap unit test (`expectedNext_` seeded near
  `UINT32_MAX`); a `GET rebase` test asserting the new distinguishable
  refusal code.
- **Verification command**: `uv run pytest tests/host/`
