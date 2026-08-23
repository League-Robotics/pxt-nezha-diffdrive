---
status: pending
---

# The settle-tick loop is not host-testable, so deleting it would go uncaught

Sprint 003 ticket 009 wrote a regression test for the tick-model contract:
**a move that ends must still deliver the kernel's neutral to the motors.**
Without it the staged zero never reaches the motors and the wheels coast at
full duty until the lease watchdog fires ~150 ms later (commit `3e919e5`).

The test proves the NECESSITY of that step, and does it well — it verifies the
gap is real by showing the last duty delivered to `FakeMotor` is nonzero at the
instant `serviceMove()` reports done, and only zeroes after one more `step()`.

But it cannot execute the actual loop. The real settle loop lives in
`src/shims.cpp::Rig::tickDrive()` (~lines 416-434), and `shims.cpp` includes
`pxt.h` and composes CODAL platform types (`CodalClock`, `CodalSleeper`,
`CodalFiberLauncher`, `NezhaMotorPort`). The host harness only ever links
`diffdrive.cpp` and `motion_engine.cpp`, never `shims.cpp`.

**So a regression that deleted or shortened that loop would pass the whole
220-test suite.** The behaviour is pinned by argument, not by execution.

Ticket 007 deliberately left the loop in `shims.cpp` on the grounds that it is
tick-engine pacing rather than move-engine shaping — a defensible call, and it
was the right one to avoid a last-minute refactor of the move-completion path.
This issue is the follow-up that call implies.

## What to do

Either:

- extract the loop's LOGIC (bounded iteration count, break-on-rest, never
  re-energize) into a host-portable helper in `motion_engine`, leaving only
  the platform glue in `shims.cpp`; or
- accept the gap deliberately and write it down where a future reader of
  `tickDrive()` will see it, rather than leaving it as an accident of where
  the include boundary happens to fall.

The first is preferable — the loop's shape is exactly the sort of thing a
well-meaning simplification would flatten, and it is load-bearing.

Note the related constraint from the same work: exactly ONE fiber may tick a
given move. Protocol co-ticking caused heisenbugs. Any extraction must not
make it easier to tick a move from two places.
