---
id: '004'
title: 'Degenerate motion command: stop prior motion, or document that it does not'
status: done
use-cases: []
depends-on: []
github-issue: ''
issue: wire-and-shim-minor-defects.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Degenerate motion command: stop prior motion, or document that it does not

## Description

`src/motion/motion_engine.cpp` has two degenerate-command paths that clear the
move-engine's own bookkeeping but never touch the kernel that is actually
driving the motors:

1. **`wheelsX()`** (`motion_engine.cpp:52-58`):
   ```cpp
   void MotionEngine::wheelsX(float left, float right, float cruise,
                              uint32_t timeoutMs) {
     cancelMove();  // motion-api.md S6: wheels_* clears the planner
     const float absLeft = std::fabs(left);
     const float absRight = std::fabs(right);
     const float dominant = absLeft > absRight ? absLeft : absRight;
     if (dominant <= 0.0f || cruise <= 0.0f) return;  // nothing to command
     ...
   ```
   `cancelMove()` (`motion_engine.cpp:88-91`) only sets `move_.active = false`
   and `move_.hasPending = false` -- it never calls `kernel_.neutral()` or
   `kernel_.drive()`. On the degenerate branch (zero-magnitude wheels command,
   or a non-positive `cruise`), `wheelsX()` returns having touched only that
   flag.

2. **`startSegment()`** (`motion_engine.cpp:98-120`, reached by `moveX()` and
   `queuePivotThenStraight()`):
   ```cpp
   if (dominant <= 0.0f || cruise <= 0.0f) {
     move_.active = false;  // nothing to command -- same contract as wheelsX
     return;
   }
   ```
   This is worse than `wheelsX()`'s case: `moveX()` itself never calls
   `cancelMove()` before reaching `startSegment()`, so the degenerate branch
   here does not even clear `move_.hasPending` -- it only sets `move_.active`
   directly, inline, and returns. Nothing about the kernel is touched.

**Consequence** (confirmed by reading the code, matches the issue): if a
`WHEELS_V` hold is currently driving the robot (`kernel_.drive()` was called
with a real lease that has not yet expired) and a degenerate `WHEELS_X 0 0
100 1000` or `MOVE_X 0 0 ...`-shaped command arrives, the wire ack is `ok`,
the move-engine's own state is cleared/never set, and **the kernel's previous
`drive()` command and lease are untouched -- the robot keeps driving under
the old command** until its own lease naturally expires. The documented
contract at `motion_engine.h:246-248` ("non-positive cruise is a no-op --
nothing is driven") and `motion_engine.h:269` (the `moveV`/degenerate-move
case, "is a no-op -- nothing is driven") describes the NEW command as
inert, which is true, but is silent about -- and in practice contradicts --
what happens to any motion already in progress.

Contrast with `endMove()` (`motion_engine.cpp:93-96`), which gets this right:
```cpp
void MotionEngine::endMove() {
  if (move_.active) kernel_.neutral();
  cancelMove();
}
```
`kernel_.neutral()` stages a zero command (delivered on the kernel's next
`step()`, per the established `settleToRest()`/`tickDrive()` machinery
already in this codebase -- see `motion_engine.h:307-320`'s comment on why
`kernel_.neutral()` alone only STAGES the stop). `endMove()`'s `if
(move_.active)` guard is appropriate there because `endMove()` is only
reached when a move-engine move was known active -- but `wheelsX()`'s and
`startSegment()`'s degenerate branches can be reached regardless of whether
the PRIOR command came from the move engine (`moveX`) or from `wheelsV()`
(which never sets `move_.active` at all), so a `move_.active`-gated guard
would still miss the `WHEELS_V`-then-degenerate-`WHEELS_X` case from the
issue. The fix needs to stop the kernel unconditionally on the degenerate
path, not conditionally on `move_.active`.

**Directive: prefer making it stop.** Per the sprint's stated preference,
implement the fix that makes a degenerate command actually halt any
in-progress motion, rather than the documentation-only alternative, unless
the implementer finds a concrete reason during implementation that stopping
is unsafe or infeasible here (in which case, fall back to plainly correcting
`motion_engine.h`'s "no-op -- nothing is driven" language at both sites to
state that prior motion is NOT stopped, and record why stopping was rejected).

`src/core/diffdrive.{h,cpp}` (the vendored kernel) is not to be edited --
`kernel_.neutral()` already exists as a public method on it and is the same
primitive `endMove()` already calls; this ticket only changes when
`motion_engine.cpp` calls it, not the kernel itself.

## What to change

1. `src/motion/motion_engine.cpp` -- in `wheelsX()`'s degenerate branch
   (`dominant <= 0.0f || cruise <= 0.0f`), call `kernel_.neutral()`
   unconditionally before returning (mirroring `endMove()`'s stop, but
   without the `move_.active` guard, since the prior driver may have been
   `wheelsV()` which never sets that flag).
2. `src/motion/motion_engine.cpp` -- same treatment in `startSegment()`'s
   degenerate branch (`dominant <= 0.0f || cruise <= 0.0f`), which is reached
   by both `moveX()` and `queuePivotThenStraight()`.
3. Consider (implementer's judgment) whether the two nearly-identical
   degenerate-guard blocks in `wheelsX()` and `startSegment()` should share a
   small private helper (e.g. `stopIfDegenerate()`) now that both need the
   same kernel-stop behavior -- optional, only if it does not complicate the
   diff more than the duplication already does.
4. `src/motion/motion_engine.h:246-248` and `:269` -- update the "non-positive
   cruise is a no-op -- nothing is driven" / "is a no-op -- nothing is
   driven" doc comments to state the corrected contract: the new command is
   still a no-op (nothing new is commanded), but any motion already in
   progress is now stopped. If the implementer instead takes the
   document-only fallback (see above), these comments are updated to state
   the OPPOSITE plainly -- prior motion is not stopped -- instead of leaving
   the current ambiguous "no-op -- nothing is driven" phrasing that reads as
   "the robot does nothing" rather than "no NEW command is issued."
5. Do not modify `wheelsV()` -- it has no degenerate early-return branch
   today (it always calls `kernel_.drive()`, including for a zero-velocity
   command, which already actively stops the robot); it is not part of this
   defect.

## Acceptance Criteria

- [x] A degenerate `wheelsX()` call (zero-magnitude wheels, or non-positive
      cruise) arriving while a prior `wheelsV()`-driven motion is still
      within its lease now stops that motion (kernel receives a neutral
      command), rather than leaving it running to its own expiry.
- [x] A degenerate `moveX()`/`startSegment()` call has the same corrected
      behavior.
- [x] `motion_engine.h`'s "no-op -- nothing is driven" comments (both sites)
      are updated to accurately state the new contract (or, if the
      documentation-only fallback was taken instead, to plainly state that
      prior motion is NOT stopped -- either way, the doc comment must match
      what the code actually does).
      **Note**: the current source has these two doc-comment sites at
      `wheelsX()`'s own declaration and at `startSegment()`'s private doc
      comment (not at `moveV()`, which carries no such comment -- it has
      no degenerate branch, per "Do not modify `wheelsV()`" below).
      `goToR()`'s own separate "is a no-op -- nothing is driven" comment
      (its arrival-tolerance gate, a different mechanism) is intentionally
      untouched -- out of this ticket's stated scope (wheelsX()/
      startSegment() only).
- [x] No change to `src/core/diffdrive.{h,cpp}` (vendored, byte-stable) --
      `kernel_.neutral()` is called, not modified.
- [x] `wheelsV()` is unmodified.
- [x] A test demonstrates the fix: drive the kernel into an active motion
      (e.g. via `wheelsV()`), then issue a degenerate `wheelsX()` or `moveX()`
      call, and assert the kernel's commanded velocity/twist (or `Output`)
      goes to (or stages toward) neutral -- this test must FAIL against
      today's code (which leaves the prior drive command intact) and PASS
      after the fix. Four such tests added (two per call site, one per
      degenerate condition); verified failing by temporarily reverting
      `motion_engine.{h,cpp}` to their pre-fix content and confirming all
      four fail, then restoring the fix and confirming they pass.

## Testing

- **Existing tests to run**: `uv run pytest tests/host/test_motion_engine_primitives.py
  tests/host/test_motion_engine_reductions.py tests/host/test_motion_engine_settle.py
  tests/host/test_wire_motion_verbs.py tests/host/test_wire_motion_completion.py`
  (the motion-engine and wire-motion-verb suites most likely to interact with
  this contract), plus the full host suite `uv run pytest tests/host/` to
  catch any coupling this ticket did not anticipate.
- **New tests to write**: in `tests/host/test_motion_engine_primitives.py` (or
  wherever the existing degenerate-command tests, if any, already live --
  grep for `dominant <= 0` / `cruise <= 0` coverage first), add a test using
  the existing `motion_engine_shim.cpp` host harness that: (1) issues a real
  `wheelsV()` command with a live lease, (2) issues a degenerate `wheelsX()`
  or `moveX()` call, (3) asserts the kernel's `Output` now reflects a
  stopped/neutral command rather than the original `wheelsV()` command
  continuing. This directly reproduces the issue's `WHEELS_X 0 0 100 1000`
  during a `WHEELS_V` hold scenario at the `MotionEngine` level (below the
  wire parsing layer, where the sprint's Test Strategy says everything here
  is host-testable without hardware).
- **Verification command**: `uv run pytest tests/host/`
