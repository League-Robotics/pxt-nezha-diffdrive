---
id: '004'
title: 'Simulator parity: fix set-wheel-speeds turn-rate divisor and latch emergency
  stop'
status: open
use-cases:
- SUC-004
depends-on:
- '002'
github-issue: ''
issue: simulator-parity-turn-rate-and-estop.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Simulator parity: fix set-wheel-speeds turn-rate divisor and latch emergency stop

## Description

Two independent, unrelated bugs in `main.ts`'s browser-simulator
fallback bodies, both making the simulator lie to students about what
hardware will do (`main.ts` lines cited are approximate — re-locate
before editing, sprint 006 shifted line numbers since the review):

1. **R-12/BLK-06 — turn rate 10× too slow.** `_setWheels`'s sim body
   computes `simYawRate = ((right - left) / 10) / 115` — an effective
   1150 mm track (10× the real 115 mm assumed elsewhere in the same
   file), confirmed both by dimensional analysis and by disagreement
   with `_driveTwist`'s own sim body in the same file, which is
   already correct. A turn tuned in the simulator rotates 10× faster
   on hardware.
2. **R-13/BLK-07 — no e-stop latch.** `_estopAll` is just `_stopAll`;
   `_estopClear` is an empty no-op. Hardware refuses at two layers
   after `emergencyStop()` (`checkCommandable()`'s `estopLatch_` gate,
   plus `step()` forcing `effective = kModeNeutral` every cycle while
   latched); the simulator refuses nothing, so
   `emergencyStop(); setWheelSpeeds(15, 15)` drives happily in the
   browser and does nothing on the robot — inverting UC-011's
   most-flagged student pitfall ("forgot to clear emergency stop")
   exactly where students develop (UC-016).

**This ticket depends on ticket 002** (the `driveTick()`/`_tickDrive()`
contract fix) because `_tickDrive()`'s new return expression
(`simMoveActive || simVel !== 0 || simYawRate !== 0`) and this
ticket's `simEstopped` gate both touch the same handful of simulator
state variables — landing 002 first means this ticket's `simEstopped`
gate composes against the already-fixed tick contract instead of the
two changes being reasoned about together mid-ticket.

## Implementation Plan

1. Fix #1: change `_setWheels`'s yaw-rate expression to
   `(right - left) / 115` (delete the `/10`), matching `_driveTwist`'s
   own correct math. Add a comment pinning the formula to the
   hardware conversion it mirrors, per the review's own remedy text —
   the exact kind of comment whose absence let this drift undetected.
2. Fix #2: add `let simEstopped = false` to `main.ts`'s simulator
   state block. `_estopAll()` sets it `true` (in addition to its
   existing `_stopAll()` call). `_estopClear()` sets it `false`
   (replacing its current empty body). `_setWheels`, `_driveTwist`,
   and `_startMove` each gain an early return when `simEstopped` is
   `true` (call `simIntegrate()` first, as they already do, so
   elapsed-time bookkeeping stays correct; just don't update
   `simVel`/`simYawRate`/`simMoveActive`) — mirroring hardware's
   intake-time refusal in `checkCommandable()`, not a per-tick gate
   (the sim has no equivalent of the kernel's own per-cycle
   `effective = kModeNeutral` override; intake refusal is sufficient
   here since nothing else in the sim can introduce velocity between
   calls).
3. `docs/design/specification.md` §5 gains the e-stop-latch bullet it
   currently omits (its list of simulator/hardware divergences does
   not mention e-stop at all today) and confirms the `/115` formula
   description already matches the code once fix #1 lands. Direct
   edit on the sprint branch — not part of the canonical
   design-doc-overlay set.
4. `docs/design/usecases.md` UC-011 gains a sentence confirming its
   main flow/postconditions/error-flow now hold in the simulator too;
   UC-016 gains a note that these two gaps are closed, not new
   documented divergences. Same direct-edit note as above.

## Acceptance Criteria

- [ ] `_setWheels`'s yaw-rate expression has no `/10`; a comment pins
      it to the `/115` (assumed track width) formula `_driveTwist`
      already uses correctly.
- [ ] `simEstopped` exists, is set by `_estopAll()`, cleared by
      `_estopClear()`, and gates `_setWheels`/`_driveTwist`/
      `_startMove` (checked, no-op while set).
- [ ] Code review confirms `_driveTwist`'s own sim body is unchanged
      (it was never affected by bug #1) and that `_tickDrive()`'s
      return-contract fix (ticket 002) still ends a continuous-mode
      loop correctly once `simEstopped` zeroes `simVel`/`simYawRate`
      at the source (no double-fix needed in `_tickDrive()` itself).
- [ ] `docs/design/specification.md` §5 documents the e-stop latch;
      `docs/design/usecases.md` UC-011/UC-016 updated per the
      Implementation Plan.
- [ ] Manual/PXT-build verification (no host test reaches `main.ts`):
      a program calling `setWheelSpeeds(-15, 15)` in the simulator
      pivots at the corrected rate; a program calling
      `emergencyStop()` then `setWheelSpeeds(15, 15)` in the simulator
      does not move until `clearEmergencyStop()` is called.

## C++11 Gate Coverage

This entire ticket is `main.ts` only — outside the C++11 host-test
gate entirely (no host test reaches `main.ts` at all; see
`sprint.md`'s constraints). There is no host-testable evidence for
this ticket's fix. Evidence available: a PXT build succeeding, a
manual simulator run comparing before/after turn rate and e-stop
behavior, and code review against the hand-derived formula
(`(right-left)/115`) and the `checkCommandable()`/`step()` two-layer
refusal hardware pattern this ticket's `simEstopped` gate mirrors. No
robot is required — this is a simulator-only fix; hardware behavior is
unchanged (hardware was already correct on both axes).

## Testing

- **Existing tests to run**: none (no host test reaches `main.ts`).
- **New tests to write**: none host-side. Manual simulator
  verification per the Acceptance Criteria above.
- **Verification command**: PXT build (`pxt build` or the project's
  equivalent MakeCode CLI build step) plus a manual run in the
  browser simulator pane.
