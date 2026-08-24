---
status: done
sprint: 008
tickets:
- 008-003
---

# Host-harness doubles drifted from production: three behaviors no test can catch

Priority: **Medium** — code review 2026-08-23, R-25 (PY-03; all three
drifts CONFIRMED from both sides in `verify-python.md`).

The WaHandle test doubles claim to "mirror field-for-field" but have
drifted in three load-bearing places:

1. **Wedge semantics**: the harness STATUS shim reads `wedgeLeft/Right`
   (latched) at kernel_shim 337-338 while production DIAG reads
   `wedgeSuspectLeft/Right` (`shims.cpp:688-689`) — both field pairs exist
   on the Output struct, and no WaHandle test drives wedge at all.
2. **`setWheelsTimed`**: the double calls `kernel.drive()` directly,
   skipping `MotionEngine::wheelsV()` — whose first act is `cancelMove()`
   (`motion_engine.cpp:21`). Command-supersession behavior is untested and
   untestable as wired.
3. **Config rounding**: the double truncates `v*1000.0f` where production
   `std::lround`s in double (`shims.cpp:832`).

The comments asserting mirror-fidelity are false, which is worse than no
comment: they actively tell the next agent not to check.

## What to do

- Re-sync the doubles with production semantics (or better: compile the
  shared logic once against a single contract so there is nothing to
  mirror).
- Add a drift test that fails when either side changes alone.
- Related: `settle-tick-loop-is-not-host-testable` (filed) is the same
  disease — behavior pinned by argument, not execution. Treat these
  together as a "tests must be able to fail" work package.
