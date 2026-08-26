---
id: '016'
title: Stops that stop, and honest refusals
status: done
branch: sprint/016-stops-that-stop-and-honest-refusals
use-cases: []
issues:
- stop-move-does-not-stop-continuous-drive.md
- move-engine-ignores-estop-and-drive-refusals.md
- wire-motion-obligation-never-clears.md
- run-tours-cannot-be-aborted.md
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sprint 016: Stops that stop, and honest refusals

## Goals

Make every "make it stop" path actually stop, and make every refusal visible.
Today two of three stop paths do not stop, the move engine cannot see an e-stop
or a rejected `drive()`, and a tour that was e-stopped reports a clean run.

## Problem

Five distinct stop mechanisms exist across three layers. Each is individually
defensible; nothing states which one a given entry point delivers.

- **`stop move` does not stop a continuous drive.** `endMove()` stages
  `kernel_.neutral()` only when a move-engine move was active. After
  `setWheelSpeeds()` none is, so the port-level zero is overwritten on the next
  `step()`. Measured: duty back at 23.5% one tick later and *climbing* to 24.3%,
  because the PID makes up the ground the zero cost it. The **simulator does
  stop**, so browser and robot disagree about the student's stop button.
- **`serviceMove()` ends on `stallHalted` but never on `estopped`.** Measured:
  1230 ticks (29.5 s) of `isMoving() == true` after the latch. Safe — the kernel
  refuses to drive — but every `while (driveTick())` loop spins to the deadline.
  It only works today because `estopAll()` happens to call `endMove()` first, an
  undocumented ordering in a different file that `emergencyStopMotors()` bypasses.
- **`kernel_.drive()`'s refusal `Status` is discarded at all four call sites.** A
  refused move arms, reports progress, spins to its deadline, and resolves as
  `kStop` — indistinguishable from one that ran.
- **The wire's motion obligation is never cleared on completion**, so the
  protocol fiber co-ticks the kernel for the whole declared timeout — up to
  24.8 days at the decode clamp. That is a candidate mechanism for
  `i2c-fault-count-climbs-on-idle-bus.md`, and it puts a second fiber on the I2C
  bus during OTOS reads, which `blocks/world.ts` explicitly forbids.
- **A running `RUN:` tour cannot be aborted.** An e-stopped tour proceeds through
  every remaining leg, emits plausible corner fixes from a stale cache, and
  finishes with a normal `TOUR:end`. The operator gets a complete transcript for
  a tour that never moved.

## Solution

Four small, mostly independent changes, plus one decision.

The decision is `stop move`'s contract, and it is the stakeholder's:
**"end the move"** (drop `deliverStopNow()`, make the simulator match) or
**"stop"** (add `kernel.neutral()`, one line). Recommendation: **"stop"** — it
matches the block's caption, matches what the simulator has done since sprint
012, and is the only option that removes a sim/hardware divergence rather than
codifying one. It does change a documented block contract, which is why it is
being asked rather than assumed.

The rest: add `out.estopped` to `serviceMove()`'s end condition; refuse to arm
`move_.active` on a rejected `drive()`; clear `motionObligationActive_` where
the pending motion already resolves; add an abort flag and an honest terminal
line to the tours.

## Success Criteria

- [x] `stop move` zeroes duty one tick after a continuous command, pinned by a
      host test that fails pre-fix. **Corrected during execution**: the original
      criterion said to re-run `stop_probe.cpp` unmodified. That is impossible
      and the criterion was wrong — the probe hardcodes the pre-fix sequence
      inline in its own `main()`, because `shims.cpp` cannot be host-compiled.
      No unmodified re-run can ever reflect a fix to `shims.cpp::endMove()`.
      Scenario B of the same probe (ticket 002's e-stop case) *does* track the
      fix dynamically, because it calls the shared `motion_engine.cpp` code
      directly — it now reports 0 further ticks instead of the measured 1230.
- [ ] Simulator and hardware agree on `stop move`, stated in one place.
- [ ] A host test pins that a move ends within one tick of an e-stop latched
      *without* going through `estopAll()`.
- [ ] A host test pins that a refused `drive()` leaves `move_.active` false.
- [ ] `hasLiveMotionObligation()` reads false within one tick of a goal-directed
      move completing.
- [ ] A tour aborted or e-stopped mid-run says so in its terminal line and emits
      no further corner fixes.
- [ ] Re-check `i2c-fault-count-climbs-on-idle-bus.md` against the obligation
      fix: capture `i2cf` and `cyc` with and without a preceding wide-timeout
      `MOVE_X` and report whether the climb tracked the obligation window.

## Scope

### In Scope

`src/shims.cpp` (`endMove()`), `src/motion/motion_engine.cpp` (`serviceMove()`
end conditions, `startSegment()` refusal handling), `src/comms/wire_adapter.cpp`
(obligation clearing), `src/blocks/sim.ts` (parity), `test/test.ts` (abort flag,
terminal line), `tests/host/`.

### Out of Scope

The stall-latch *inducement* question — whether the taper crawl can trip the
latch — belongs with the pivot work in 015. The unified "why won't it move"
surface that `src/DESIGN.md` S10 has deferred since sprint 007 is not attempted
here; this sprint reduces the count of silent-refusal states from six to four,
which is the down payment on it.

## Test Strategy

As with 015: every fault here is invisible to the current green suite, so each
ticket's bar is a test that fails today. `test_cross_fiber_stop_settle_window.py`
already has the right shape and should be extended to continuous-mode commands
and to an e-stop latched outside `estopAll()`. Refusal propagation is cheap to
test — the kernel harness can produce `kRefusedUnconfigured` and
`kRefusedEstopped` directly, and nothing currently asserts what `MotionEngine`
does with either.

## Architecture

Compact — no structural change. The one thing worth recording in `src/DESIGN.md`
is the stop taxonomy itself: which of the five mechanisms each entry point
delivers, and that `deliverStopNow()` alone is momentary rather than a stop.
That table is the durable output of this sprint.

## Use Cases

### SUC-001: A stop block stops the robot
Parent: UC-011
- **Acceptance**: duty zero on the next tick and staying zero, for the contract
  chosen; simulator agreeing; the block's doc stating it.

### SUC-002: An e-stopped tour says it was e-stopped
Parent: UC-011
- **Acceptance**: `TOUR:end:estop` / `TOUR:end:abort`; no further `OCAL:` lines;
  `isMoving()` false within one tick of the latch.

## Definition of Ready

- [ ] Sprint planning document complete
- [ ] Architecture review passed
- [ ] **Stakeholder has chosen the `stop move` contract** (see Solution)
- [ ] Sprint 015 merged — 016 touches `serviceMove()` and `shims.cpp`, which 015
      is also editing

## Tickets

| # | Title | Depends On |
|---|-------|------------|
| 001 | `stop move` contract (stakeholder's choice) + simulator parity | — |
| 002 | `serviceMove()` ends on `estopped`; `startSegment()` does not arm on a refused `drive()` | — |
| 003 | Clear `motionObligationActive_` when the pending motion resolves | 002 |
| 004 | Re-check the idle-I2C issue against 003's fix; record the result either way | 003 |
| 005 | `RUN:abort` handler; per-leg abort check; honest tour terminal line | 002 |
| 006 | Stop taxonomy recorded in `src/DESIGN.md` | 001–005 |
| 007 | **Build checkpoint** (standing convention, always last) | 001–006 |

Tickets execute serially in the order listed.
