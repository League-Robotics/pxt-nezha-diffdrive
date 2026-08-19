---
id: '004'
title: Loop-style square test.ts variant + README tick-contract docs
status: done
use-cases:
- SUC-001
- SUC-002
depends-on:
- '001'
- '002'
github-issue: ''
issue: caller-driven-tick-loop-for-diffdrive-pure-tick-model-design-sprint-002-issue.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Loop-style square test.ts variant + README tick-contract docs

## Description

Demonstrates and documents the generator/tick model this sprint
introduces, per sprint.md's Solution and the issue's `test.ts`/README
scope. Two small, independent pieces:

**`test.ts`**: add a loop-style square variant on button B, alongside
the existing button-A stepwise tour (unchanged). Per-leg: `startMove(...)`
then `while (diffDrive.driveTick()) { /* pose readout, e.g. LED bar
graph or showNumber of rounded x */ }` — the demonstration artifact for
the caller-driven model, mirroring the intent of the old (pre-sprint-001)
`whileMoving` LED-bar-graph demo but built on `driveTick()` instead.
Note: button B's handler currently just sets `bPressed = true` (used to
gate between legs of the button-A tour, `test.ts` lines 15-17) — this
ticket must distinguish "B pressed to advance a leg mid-tour" from "B
pressed to start the loop-style variant" (e.g., guard on `touring`), so
the two behaviors don't collide.

**`README.md`**: add a section documenting the tick contract — "the
robot only moves while your loop ticks" — covering: `driveTick()`'s
existence and the `while (diffDrive.driveTick())` idiom;
`setWheelSpeeds`/`driveTwist` now requiring a following tick source to
keep moving (the breaking runtime-semantics change, sprint.md Migration
Concerns); the starvation watchdog as a safety net (~150 ms bound,
resumable, not an e-stop); and that `move`/`goTo`/`whileMoving`/
`whileGoingTo` need no student-visible change (they tick internally).

## Acceptance Criteria

- [x] `test.ts` button A's existing stepwise square tour is unchanged in
      behavior.
- [x] `test.ts` button B starts a loop-style square variant using
      `while (diffDrive.driveTick())` per leg, with a live readout in
      the loop body, when not already mid-tour; button B's existing
      mid-tour "advance to next leg" behavior (`bPressed` gate) is
      preserved and the two do not collide.
- [x] The loop-style variant completes a recognizable square path (desk-
      reviewed / simulator-run) and ends with the robot stopped.
- [x] `README.md` documents the tick contract prominently, including the
      continuous-mode breaking-change note (Migration Concerns) and the
      watchdog's resumable-without-e-stop-clear behavior.
- [x] README's documentation is consistent with ticket 002's JSDoc (no
      contradictory description of the same contract).

## Testing

- **Existing tests to run**: run the MakeCode simulator build — confirm
  `test.ts`'s existing button-A tour and the new button-B loop-style
  variant both compile and run in the simulator without error.
- **New tests to write**: none automated (no unit-test harness). The
  loop-style variant's on-hardware behavior (actual square closure,
  live pose readout timing) is covered by sprint.md's deferred hardware
  pass — do not block this ticket on it.
- **Verification command**: none (no test runner). Verify by simulator
  run and README proofread against ticket 002's JSDoc.
