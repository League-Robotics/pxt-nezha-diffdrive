---
status: in-progress
sprint: '007'
tickets:
- 007-001
---

# Stall latch: no clear path, no readback — robot silently dead until power cycle

Priority: **High** — code review 2026-08-23, R-01 (KERN-01 + API-02;
CONFIRMED; downgraded Critical→Major only because power-cycle recovers).

The stall detector ships enabled (500 ms of demanded duty with near-zero
encoder motion → `stallHalted_` latches). Once latched:

- `clearStallLatch()`'s only caller in the entire repo is a host-test shim —
  no block, no wire verb, no shim path reaches it.
- `estopClear()` clears only the e-stop latch, not the stall latch.
- `checkCommandable()` keeps returning `kOk`, so `drive()` "succeeds" and
  blocking moves "complete" instantly while the robot ignores everything.
- There is no discoverable readback (only the undocumented `probe(2)`).

A student whose robot pushes a wall for half a second loses the rest of
their program with no error anywhere.

## What to do

- Expose a clear path: a block (advanced group), a wire verb, and decide
  whether `clear emergency stop` should also clear it.
- Expose readback: STATUS bit + DIAG ordinal + a student-visible reporter.
- Consider the review's broader design note: e-stop, stall latch, watchdog,
  and lease expiry are four invisible "robot is off" states; one unified
  "why won't it move" surface would retire the whole class (review §Design
  assessment).
