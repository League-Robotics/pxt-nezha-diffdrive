---
id: '004'
title: 'Simulator parity: fix set-wheel-speeds turn-rate divisor and latch emergency
  stop'
status: done
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

- [x] `_setWheels`'s yaw-rate expression has no `/10`; a comment pins
      it to the `/115` (assumed track width) formula `_driveTwist`
      already uses correctly.
- [x] `simEstopped` exists, is set by `_estopAll()`, cleared by
      `_estopClear()`, and gates `_setWheels`/`_driveTwist`/
      `_startMove` (checked, no-op while set).
- [x] Code review confirms `_driveTwist`'s own sim body is unchanged
      (it was never affected by bug #1) and that `_tickDrive()`'s
      return-contract fix (ticket 002) still ends a continuous-mode
      loop correctly once `simEstopped` zeroes `simVel`/`simYawRate`
      at the source (no double-fix needed in `_tickDrive()` itself).
- [x] `docs/design/specification.md` §5 documents the e-stop latch;
      `docs/design/usecases.md` UC-011/UC-016 updated per the
      Implementation Plan.
- [x] Manual/PXT-build verification (no host test reaches `main.ts`):
      a program calling `setWheelSpeeds(-15, 15)` in the simulator
      pivots at the corrected rate; a program calling
      `emergencyStop()` then `setWheelSpeeds(15, 15)` in the simulator
      does not move until `clearEmergencyStop()` is called. Verified by
      `pxt build` succeeding (both hex targets regenerated) plus a
      hand-traced dry run of the corrected arithmetic and the latch's
      state transitions (see ticket completion notes below) — not an
      interactive browser-simulator session (none available in this
      environment; no simulator test harness exists to automate it
      either).

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

## Completion Notes

- `pxt build` succeeded (exit 0; `built/binary.hex`, `built/mbcodal-
  binary.hex`, `built/mbdal-binary.hex` all regenerated). `tsc -p .`
  reports exactly the pre-existing baseline error (`basic.ts`'s
  `Math.roundWithPrecision` gap) — 1 error, unchanged. A `pxt build
  --debug` run also surfaces 5 pre-existing `TS9256` ("bit sizes are
  not supported for locals and parameters") diagnostics against
  `int32`-typed shim parameters; confirmed present, same count, on the
  pre-ticket branch tip too (`git stash` + rebuild) — not a
  regression, and not fatal (plain `pxt build` without `--debug`
  exits 0 and produces all three hex targets).
- No browser was available to run the simulator pane interactively.
  In its place, a hand trace of the corrected code:
  - `setWheelSpeeds(-15, 15)` -> `_setWheels(-150, 150)` [mm/s] ->
    `simVel = 0`, `simYawRate = (150 - (-150)) / 115 = 300/115 ≈
    2.609 rad/s` (≈150 deg/s), a pure pivot. Pre-fix this was
    `((300)/10)/115 ≈ 0.261 rad/s` (≈15 deg/s) — exactly 10x smaller,
    matching R-12/BLK-06's own measured ratio.
  - `emergencyStop()` -> `_estopAll()` -> `_stopAll()` zeroes
    `simVel`/`simYawRate`/`simMoveActive`, then `simEstopped = true`.
    A following `setWheelSpeeds(15, 15)` calls `_setWheels`, which
    runs `simIntegrate()` (no-op motion contribution, state already
    zero) then returns at the `if (simEstopped) return` guard before
    touching `simVel`/`simYawRate` — so state stays at zero. A
    `while (driveTick())` loop's `_tickDrive()` then computes
    `stillCommanded = false || false || false = false` and ends
    immediately, matching "does not move." `clearEmergencyStop()` ->
    `_estopClear()` -> `simEstopped = false`; a subsequent
    `setWheelSpeeds(15, 15)` is no longer gated and sets
    `simVel = 150`.
- `simEstopped` composes with ticket 002's `_tickDrive()` contract
  (`simMoveActive || simVel != 0 || simYawRate != 0`) with no
  special-casing in `_tickDrive()` itself — it holds `simVel`/
  `simYawRate`/`simMoveActive` at their zero values at the source
  (`_setWheels`/`_driveTwist`/`_startMove`), which is exactly the
  composition ticket 002 anticipated.
- Firmware semantics mirrored (read from source, not designed from
  first principles): `diffdrive.h`/`diffdrive.cpp` — `estopLatch_`
  (diffdrive.h:285), `checkCommandable()`'s `Status::kRefusedEstopped`
  gate (diffdrive.cpp:311), `step()`'s per-cycle
  `effective = kModeNeutral` override while latched (diffdrive.cpp:
  484), `estop()`/`estopClear()` (diffdrive.cpp:370-376). `shims.cpp`
  — `estopAll()` (kernel.estop() + kernel.emergencyStopMotors(),
  shims.cpp:803-808), `estopClear()` (shims.cpp:811), and
  `deliverStopNow()`'s comment (shims.cpp:286-294) establishing the
  stop-vs-latch distinction that `_stopAll()` not touching
  `simEstopped` mirrors. The simulator's intake-only gate (no per-tick
  override) is a deliberate simplification the ticket's own plan
  calls out: nothing else in the sim can introduce velocity between
  calls, so it is not a divergence from hardware's observable
  behavior.
- Turn-rate derivation: differential-drive kinematics give
  `omega [rad/s] = (v_right - v_left) [mm/s] / trackWidth [mm]`
  (v_right = v + omega*L/2, v_left = v - omega*L/2 => v_right -
  v_left = omega*L). `_driveTwist`'s hardware shim applies the same
  relation in reverse (`twistMmS = yawRad * 0.5 * effectiveTrackWidth()`,
  shims.cpp:323/359). 115 mm is the simulator's fixed stand-in for the
  caliper-measured `trackWidth_` (114.2 mm, `motion_engine.h:386`) —
  `setGeometry()` is a no-op in the simulator, so there is no live
  value to read; `specification.md` §5 already documented this
  approximation before this ticket. The buggy code additionally
  divided by 10 first, an effective 1150 mm track (10x too wide),
  which is what produced the 10x-too-slow turn.
- R-12/R-13 annex material located in
  `docs/code-review/2026-08-23/review.md` (R-12 at line 167, R-13 at
  line 172, summary table row at line 370) and
  `docs/code-review/2026-08-23/raw/verify-blocks.md` (BLK-06/BLK-07
  summary table rows 16-17; detailed verification at "### BLK-06 —
  factor pinned two independent ways" line 165 and "### BLK-07 —
  divergence and spec-gap both real" line 179) and
  `docs/code-review/2026-08-23/raw/correctness-blocks.md` (original
  findings at "### BLK-06 ..." line 182 and "### BLK-07 ..." line
  204).
- `uv run pytest` still reports 333 passed (unchanged baseline) —
  expected, since nothing touched by this ticket is host-tested.
