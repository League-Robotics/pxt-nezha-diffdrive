---
id: '002'
title: main.ts caller-driven rewiring (driveTick block, move/goTo/whileMoving/whileGoingTo)
status: done
use-cases:
- SUC-001
- SUC-002
depends-on:
- '001'
github-issue: ''
issue: caller-driven-tick-loop-for-diffdrive-pure-tick-model-design-sprint-002-issue.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# main.ts caller-driven rewiring (driveTick block, move/goTo/whileMoving/whileGoingTo)

## Description

Exposes ticket 001's new C++ shims to MakeCode and rewires the
student-facing blocking/loop move blocks to use them, per sprint.md's
Architecture ("main.ts blocks" module) and the issue's rewiring plan.
Block **signatures are unchanged** — only internals and one new block.

In `main.ts`:

- Add shim declarations `_tickDrive(): boolean` (`//%
  shim=diffDrive::tickDrive`) and `_cycleStat(which: int32): int32`
  (`//% shim=diffDrive::cycleStat`), each with a simulator fallback
  body: kinematic integrate (reuse `simIntegrate()`) plus `basic.pause`
  to a 24 ms absolute schedule, so simulator-run programs behave the
  same as hardware from a timing-observable perspective.
- Add a new block `driveTick()` (`//% block="drive tick"`, Move group)
  wrapping `_tickDrive()` — the primitive students use in a `while
  (diffDrive.driveTick())` loop after `setWheelSpeeds`/`driveTwist`.
- Rewire `move()`/`goTo()` (currently `while (_updateMove())
  basic.pause(10)`) to `while (_tickDrive());` — signature unchanged,
  same blocking contract.
- Rewire `whileMoving()`/`whileGoingTo()` (currently `while
  (_updateMove()) { body(...); basic.pause(24) }`) to `while
  (_tickDrive()) { body(...) }` — the body is now phase-locked to the
  real control cycle instead of racing an independent `basic.pause(24)`.
- Leave `isMoving()` calling the existing non-stepping `_updateMove()`
  shim, per the issue's own design (do not add ticking to it).
- JSDoc: document the continuous-mode ticking contract on
  `setWheelSpeeds`/`driveTwist` ("runs until superseded or stopped" is
  no longer accurate on its own — the robot only moves while something
  ticks; pair with `driveTick()`). Also document, on `startMove`/
  `startGoTo`/`isMoving`/`moveProgress`/`stopMove` (the `advanced`-
  marked async blocks), that this old poll pattern does **not**
  progress a move under the tick model without a separate tick source —
  this is a known, stakeholder-confirmed gap (sprint.md Open Question
  3), not a bug to silently fix in this ticket.
- README: leave `README.md`'s own tick-contract prose to ticket 004
  (do not duplicate it here beyond the JSDoc above).

## Acceptance Criteria

- [x] `move`/`goTo`/`whileMoving`/`whileGoingTo` keep their existing
      signatures and observable blocking/looping behavior from a block
      author's perspective (verified via the simulator).
- [x] `move`/`goTo` internals use `while (_tickDrive());`;
      `whileMoving`/`whileGoingTo` internals use `while (_tickDrive())
      { body(...) }` — no `basic.pause(10)`/`basic.pause(24)` remains in
      these four functions.
- [x] `isMoving()` is unchanged (still calls `_updateMove()`).
- [x] New block `driveTick()` exists in the Move group, wraps
      `_tickDrive()`, and has a simulator fallback body.
- [x] `_tickDrive`/`_cycleStat` shim declarations exist with working
      simulator bodies (kinematic integrate + 24 ms absolute-schedule
      `basic.pause`), so the MakeCode simulator build compiles and runs.
- [x] JSDoc on `setWheelSpeeds`/`driveTwist` documents the new
      ticking-required contract for continuous modes.
- [x] JSDoc on `startMove`/`startGoTo`/`isMoving`/`moveProgress`/
      `stopMove` documents that this async poll pattern requires a
      separate tick source (e.g. a concurrent `driveTick()` loop) to
      progress a move under the tick model, and that this sprint does
      not supply one.
- [x] No block signature in `main.ts` changes from its pre-sprint form
      except the addition of `driveTick()`.

## Testing

- **Existing tests to run**: run the MakeCode simulator build (this
  project's only automated-ish check, per `specification.md` §14) —
  confirm `test.ts`'s existing button-A square tour still completes
  with net-zero pose in the simulator, using the rewired `move()`
  internals.
- **New tests to write**: none automated (no unit-test harness). Desk-
  review the rewired blocking/loop forms against ticket 001's
  `tickDrive()` contract (this ticket's own acceptance criteria).
  Hardware timing/behavior parity is covered by sprint.md's deferred
  hardware pass (old-vs-new square end-pose parity) — do not block this
  ticket on it.
- **Verification command**: none (no test runner). Verify by simulator
  run + code review.
