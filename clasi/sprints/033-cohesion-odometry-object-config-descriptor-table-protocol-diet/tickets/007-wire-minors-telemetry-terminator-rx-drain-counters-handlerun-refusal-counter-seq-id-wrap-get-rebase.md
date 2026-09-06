---
id: '007'
title: 'Wire minors: telemetry terminator, RX drain/counters, handleRun refusal counter,
  seq-id wrap, GET rebase'
status: open
use-cases: [SUC-004]
depends-on: ["006"]
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

- [ ] The extended pathological-239-byte-frame test asserts the
      terminator survives (sprint Success Criteria's own bar).
- [ ] RX drop/accept counters actually increment (sprint Success
      Criteria's own bar) — or are deleted, with that decision
      documented.
- [ ] The sequence-id wrap is guarded (sprint Success Criteria's own
      bar).
- [ ] `GET rebase` answers with a documented `kWriteOnly`-shaped code
      instead of the generic "unknown name" (sprint Success Criteria's
      own bar; real-read-path alternative rejected per Design
      Rationale — implementer may override with justification).
- [ ] `handleRun()`'s refusal counter increments on each of the three
      named refusal shapes; a repeated `abort` still executes despite
      the 400 ms dedupe.
- [ ] `wire_adapter.cpp` changes are confirmed rebased against sprint
      031's actual commits if that branch was still unmerged when this
      ticket started.

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
