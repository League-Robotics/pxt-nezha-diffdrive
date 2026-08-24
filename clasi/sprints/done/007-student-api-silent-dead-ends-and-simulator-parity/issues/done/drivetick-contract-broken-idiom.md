---
status: done
sprint: '007'
tickets:
- 007-002
---

# The documented `while (driveTick())` idiom stops the robot in ~150 ms

Priority: **High** — code review 2026-08-23, R-10 (API-01; CONFIRMED — the
review's top API finding).

`driveTick()` returns *move-engine* state (`serviceMove()` → false when no
move is active, `motion_engine.cpp:200` → `shims.cpp:544`), and
`driveTwist()`/`wheelsV()` begin by cancelling the move planner
(`motion_engine.cpp:21`). So the documented continuous-drive idiom

    diffDrive.driveTwist(20, 0)
    while (diffDrive.driveTick()) { }

exits on the first iteration; the watchdog stops the robot ~150 ms later.
Every documentation site prescribes this broken idiom — README (two worked
examples), specification.md §4.2, usecases.md UC-002 — while `testrig.ts`
quietly uses a different, working pattern (unconditional tick in a forever
loop). No in-tree program uses the documented form. The simulator is
contract-identical, so students see the same wrong behavior there.

## What to do

Decide the contract, then fix code and all doc sites together:

- either `driveTick()` returns "keep ticking" (true) while a velocity
  command is live, or
- introduce a separate documented idiom for continuous mode (e.g.
  `driveHold()` / bare tick loop) and document `driveTick()`'s return as
  move-progress only.

Add a host test that executes the documented idiom, so docs and code cannot
diverge silently again.
