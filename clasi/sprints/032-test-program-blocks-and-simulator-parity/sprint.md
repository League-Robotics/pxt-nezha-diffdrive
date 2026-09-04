---
id: '032'
title: Test program, blocks and simulator parity
status: roadmap
branch: sprint/032-test-program-blocks-and-simulator-parity
use-cases: []
issues:
- code-review/test-program-job-lifecycle-abort-profile-terminal-line.md
- code-review/run-dispatch-contract-argument-snapshot-and-fiber-doc.md
- code-review/simulator-split-parity-and-geometry-drift.md
- code-review/goto-turn-rate-arrival-tolerance-tick-runner-cyclestat.md
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sprint 032: Test program, blocks and simulator parity

## Goals

Give the shipped test program one job lifecycle instead of eight
ad-hoc copies: reset the `aborted` flag, apply a named shaping profile,
and emit a terminal `<VERB>:end:<reason>` line from one shared
`beginJob()`/`endJob()` pair that every motion handler uses, so a
`RUN:abort` doesn't silently turn every later pivot/straight/face into
a one-tick no-op that reports a normal end. Snapshot RUN dispatch
arguments per dispatch so a nested `abort`/`clearestop` can't overwrite
the outer handler's `runArg()` reads, and fix the JSDoc that still
claims handlers run on their own fiber (they've run on the protocol
fiber, nested, since sprint 028). Bring the simulator to parity with
hardware on the 50° pivot-then-straight split so `move 47 cm turning
90°` doesn't silently disagree between browser and robot, and drift-test
its geometry constants against the real kernel's. Fix the small
remaining block-API issues: `goTo`'s pivot honoring the default turn
rate, arrival tolerance applying to both go-to blocks, one tick runner
instead of three divergent copies, and deleting dead `cycleStat` shim
surface.

## Problem

`test.ts`'s `aborted` flag is reset only by the eight tours
(`test.ts:59`); after any `RUN:abort`, every `RUN:pivot`/`straight`/
`face`/`cal`/`arc` stops after one tick and emits a normal `*:end` — an
instrument fault that looks exactly like a 99% under-rotation to a bench
tool that doesn't know to suspect it. The five 2026-09-01 tours and
`leverCal` set no shaping profile and emit no `TOUR:end:<reason>` — a
regression of prior fixes. `RUN:abort` can't interrupt a `goToWorld` leg.
RUN handlers still block the wire for the duration of every
`basic.showNumber`/`showString`/`pause`, leaving PING/ESTOP/abort
unserviced, and the handler-fiber JSDoc is factually wrong post-sprint-
028. `runArg()` maps a typo to 0, so `RUN:circle:abc` silently pivots
in place eight times instead of erroring. Separately, the simulator
blends every `(distance, yaw)` into one arc while hardware splits at
50° into pivot-then-straight — the block's own JSDoc ("both at once
makes an arc") is only true in the browser — and its geometry constants
(`trackWidth`, `rotationalSlip`) have no drift test and ignore
`_setGeometry`, so a calibrated robot's browser twin turns 12% differently
from the real one. Smaller: `goTo`'s pivot runs at the linear cruise
instead of honoring "set default turn rate"; three near-duplicate tick
runners exist across `motion.ts`/`world.ts`/`test.ts`; arrival tolerance
gates only one of the two go-to blocks; `cycleStat` has no caller
anywhere.

## Solution

One `beginJob(name)` that sets `touring`, clears `aborted`, applies a
named profile, and resets `maxGapMs`; one `endJob(reason)` that emits
`GAP:` and the terminal `<VERB>:end:<reason>` line; every motion
handler in `test.ts` calls both. The `abort` handler calls
`diffDrive.stopMove()` so abort becomes universal, including mid-`goToWorld`.
Replace blocking `showNumber`/`showString`/`pause` calls inside RUN
handler bodies with non-blocking forms or tick-serviced waits.
`runArgOr(i, default)` rejects NaN and non-positive radii instead of
silently mapping to 0. For the dispatch contract: bind the split
argument array into the handler call (closure value, or a push/pop
stack the nested bypass restores) instead of reassigning the
module-level `runParts`; rewrite `onRun()`'s JSDoc to say handlers run
on the wire's fiber and that anything that sleeps stalls the wire; fix
the three factually wrong comments this implies. For the simulator:
mirror the split in `_startMove` using the existing `simMoveRemain*`
machinery, with the 50° threshold drift-tested against
`kTurnFirstAngleRad`; fix `move()`'s JSDoc; add a drift test for the
sim's geometry constants and make the sim honor `_setGeometry` and
`RotationalSlip`. For the block minors: convert the default yaw rate to
a pivot cruise in `startGoTo` (or fix both comments so they agree with
the code); have `world.ts` call the shared `move()`/`goTo()` instead of
its own copy; decide `_endMove()`'s behavior once; make `turnFirstDeg`
a `const`; pass `arriveTolCm` into `_goToR`; unify `stop`/`stop move`
into one block with `stopMove` as a hidden alias; delete `cycleStat`.

## Success Criteria

- `test_run_abort_source_pin.py` (extended): every motion handler
  resets `aborted`, or `beginJob` is the only entry point that can.
- `test_run_tour_programs.py`: every tour emits a terminal line with a
  reason.
- No `basic.pause`/`showString`/`showNumber` inside a RUN handler body.
- A host test (TS type-check plus a source pin): `runArg()` after a
  nested bypass returns the outer command's argument, not the nested
  one's.
- The simulator's pivot-then-straight split threshold is drift-tested
  against `kTurnFirstAngleRad`; its geometry constants are drift-tested
  against the real kernel's; `_setGeometry`/`RotationalSlip` affect
  simulated motion.
- `goTo`'s pivot honors "set default turn rate" (or the comment is
  fixed to match the code, whichever the sprint decides); `cycleStat`
  is gone; one tick-runner implementation is shared by `motion.ts`,
  `world.ts`, and `test.ts`.

## Scope

### In Scope

- `test/test.ts`: job lifecycle (`beginJob`/`endJob`), abort's
  `stopMove()` call, non-blocking display in handler bodies,
  `runArgOr()`.
- `run.ts` / `protocol.h` / `protocol.cpp`: per-dispatch argument
  snapshot, JSDoc and comment fixes for the handler-fiber model.
- `blocks/sim.ts`: the 50° split mirror, geometry drift tests,
  `_setGeometry`/`RotationalSlip` honored.
- `blocks/motion.ts`, `blocks/world.ts`: `goTo` turn-rate fix, one tick
  runner, arrival tolerance on both go-to blocks, one stop block,
  `cycleStat` deletion.

### Out of Scope

- Everything in sprints A (motion profile — note the design's
  `omegaMax`/`MotionLimits` may eventually absorb the yaw-rate half of
  the `goTo` turn-rate fix; this sprint is sequenced independently and
  the block-level fix here is not blocked on that), B (bus/fiber
  safety), D (odometry, config descriptor table, Protocol diet beyond
  the dispatch-argument fix), E (bench tools), and F (comment work
  order beyond what's needed to fix the three factually wrong dispatch
  comments here).
- The one-fiber I2C invariant itself (sprint B) — this sprint only
  fixes the RUN-handler blocking-call symptom of handlers running on
  the protocol fiber, not the underlying bus-ownership guard.

## Related Issues

- [`code-review/test-program-job-lifecycle-abort-profile-terminal-line.md`](../../issues/code-review/test-program-job-lifecycle-abort-profile-terminal-line.md)
- [`code-review/run-dispatch-contract-argument-snapshot-and-fiber-doc.md`](../../issues/code-review/run-dispatch-contract-argument-snapshot-and-fiber-doc.md)
- [`code-review/simulator-split-parity-and-geometry-drift.md`](../../issues/code-review/simulator-split-parity-and-geometry-drift.md)
- [`code-review/goto-turn-rate-arrival-tolerance-tick-runner-cyclestat.md`](../../issues/code-review/goto-turn-rate-arrival-tolerance-tick-runner-cyclestat.md)

## Test Strategy

(Describe the overall testing approach for this sprint: what types of tests,
what areas need coverage, any integration or system-level testing needed.)

## Architecture

Not yet written — this sprint is in Roadmap Mode. Architecture (sized
per the effort decision) is produced when this sprint is detail-planned.

### Architecture Overview

(High-level structure and component relationships, if applicable.)

### Design Rationale

(Significant decisions with alternatives considered and reasoning, if
applicable.)

### Migration Concerns

(Data migration, backward compatibility, deployment sequencing — or
"None" if not applicable.)

## Use Cases

Not yet written — produced at detail-planning time, sized to the
change.

### SUC-001: (Title)
Parent: UC-XXX

- **Actor**: (Who)
- **Preconditions**: (What must be true before)
- **Main Flow**:
  1. (Step)
- **Postconditions**: (What is true after)
- **Acceptance Criteria**:
  - [ ] (Criterion)

## GitHub Issues

(GitHub issues linked to this sprint's tickets. Format: `owner/repo#N`.)

## Definition of Ready

Before tickets can be created, all of the following must be true:

- [ ] Sprint planning document is complete (sprint.md, including its
      Architecture and Use Cases sections)
- [ ] Architecture review passed (or skipped, for changes with no
      architectural impact)
- [ ] Stakeholder has approved the sprint plan

## Tickets

| # | Title | Depends On |
|---|-------|------------|

Tickets execute serially in the order listed.
