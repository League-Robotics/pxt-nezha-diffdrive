---
id: '002'
title: Route startGoTo/goTo/whileGoingTo through goToR; correct two false doc comments
  in motion.ts
status: done
use-cases: []
depends-on:
- '001'
github-issue: ''
issue: block-go-to-misses-its-target.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Route startGoTo/goTo/whileGoingTo through goToR; correct two false doc comments in motion.ts

## Description

Ticket 001 exposed `MotionEngine::goToR()` to the block layer as a `//%`
shim. This ticket consumes it: `startGoTo(x, y)` in `src/blocks/motion.ts`
(`:183-198`) currently computes its own constant-curvature arc pair
(`theta = 2*atan2(y,x)`, `s = R*theta`) and hands `(s, theta)` to
`startMove()` -> `MotionEngine::moveX()`, which is only self-consistent as
one blended segment. `moveX()`'s own documented, correct split (pivot then
drive `s` as a STRAIGHT LINE) turns that arc length into the wrong distance
whenever `|theta| >= 50 deg` — measured at 112.5 mm off a 141.4 mm hop for
`goTo(10,10)`, and a 3.07 m arc to a point 10 cm away for `goTo(-10,1)`
(`block-go-to-misses-its-target.md`). `startGoTo` also never wraps `theta`
to the short arc, so a target behind the robot becomes a near-360 deg turn
around a huge circle — that is the second half of the same defect.

Rewrite `startGoTo` to call the newly exposed `goToR` shim directly instead
of computing `(s, theta)` and going through `startMove`. Apply the same
cm-to-mm / cm/s-to-mm/s unit conversion `startMove()` already applies for
`_startMove()` (`Math.round(x * 10)` etc.), and pass `defaultSpeed` (already
in scope in the `diffDrive` namespace) as the speed argument. `goTo` and
`whileGoingTo` both call `startGoTo` internally and need no changes of their
own — fixing `startGoTo` fixes all three of the affected Move-palette
blocks in one place.

This ticket also fixes two doc comments in `src/blocks/motion.ts` that the
2026-08-26 code review found factually wrong, unrelated to the arc defect
but in the same file:

1. The namespace docstring (`:1-12`) claims "The wheel servo runs in its
   own fiber on the micro:bit (the DiffDrive kernel, 24 ms cadence); every
   command below just talks to it," and that "the function bodies here are
   the browser-simulator fallbacks." Both are false. The kernel's fiber is
   deliberately unwired — "the robot only moves while something ticks" is a
   stated system invariant (`docs/design/design.md`), and `setWheelSpeeds`'s
   own doc comment two paragraphs later says exactly that ("Continuous-mode
   command: the robot only moves while something keeps ticking the control
   loop"). And the bodies in this file are NOT simulator fallbacks — they
   moved to `sim.ts` in sprint 012's module split; this file's exported
   functions are the real block-API implementations that call into the
   shim layer.
2. `isMoving()`'s doc comment (`:200-206`) says "Checks state only — it
   does not itself advance the move." This is false: `isMoving()` calls
   `_updateMove()`, which is `updateMove()` in `src/shims.cpp`, which calls
   `MotionEngine::serviceMove()` — the exact function that advances a move
   (recomputes taper/ramp, reissues the drive command, checks completion).
   `isMoving()` DOES advance the move as a side effect of checking it.

Fix both comments to state the actual tick model accurately: the robot
only moves while something ticks the control loop (no dedicated fiber),
these are the real block-API bodies (not simulator fallbacks — those live
in `sim.ts`), and `isMoving()`/`_updateMove()` does advance the move via
`serviceMove()`, it does not just read state.

## Acceptance Criteria

- [x] `startGoTo(x, y)` in `src/blocks/motion.ts` calls the `//%`-annotated
      `goToR` shim (ticket 001) with mm-converted arguments, using
      `defaultSpeed` for the speed parameter, instead of computing
      `(s, theta)` and calling `startMove()`.
- [x] `goto_probe.cpp`
      (`docs/code-review/2026-08-26/raw/goto_probe.cpp`), re-run unmodified
      against the block path, lands within 5 mm of target for both measured
      cases: `goTo(10,10)` (currently 112.5 mm off) and `goTo(-10,1)`
      (currently 3172.4 mm off).
- [x] A target behind the robot no longer drives the long way around — the
      short-arc wrap (`wrapToPi()`, already inside `goToR()`) is exercised
      via the block-layer entry point, not re-implemented in `motion.ts`.
- [x] `goTo` and `whileGoingTo` are verified to still work correctly by
      construction (both call `startGoTo` internally; no separate code path
      needs its own fix) — note this explicitly in the ticket's completion
      notes so a reviewer does not go looking for parallel changes in
      those two functions.
- [x] The namespace docstring in `src/blocks/motion.ts` (`:1-12`) no longer
      claims the wheel servo runs in its own fiber, and no longer claims
      the function bodies here are simulator fallbacks.
- [x] `isMoving()`'s doc comment (`:200-206`) no longer claims it "checks
      state only" — it must state that it calls `_updateMove()` /
      `serviceMove()` and therefore does advance the move as a side effect.
- [x] SUC-001 acceptance from `sprint.md`: `goTo(10, 10)` lands within 5 mm;
      a target behind the robot does not drive the long way around; both
      covered by the host test from ticket 001 (extended if needed to
      confirm it now exercises the FIXED `startGoTo` reasoning, not just
      the underlying `goToR` shim in isolation).
- [x] Existing 597-test suite (plus ticket 001's new test) stays green —
      the contrast-case assertion from ticket 001 that pinned today's
      broken arc-length-through-`moveX` behavior must now be understood as
      historical documentation of the fixed bug, not a live path; do not
      leave a passing assertion that still exercises the OLD broken
      reduction as if it were current behavior.

## Completion Notes

- `startGoTo(x, y)` (`src/blocks/motion.ts`) now converts cm to mm
  (`Math.round(x * 10)`/`Math.round(y * 10)`, matching `startMove()`'s
  own conversion), converts `defaultSpeed` cm/s to mm/s the same way,
  picks a 1 mm `arrive` gate and a timeout that sums goToR()'s
  worst-case SEQUENTIAL pivot (≤180 deg at `defaultYawRate`) and
  straight-line (chord at `defaultSpeed`) phases plus a 1500 ms margin
  (mirroring `startMove()`'s own end-of-move taper backstop shape), then
  calls the new `_goToR()` shim directly. No `(s, theta)` computation or
  `startMove()` call remains in `startGoTo()`.
- `_goToR()` did not exist as a callable TS entry point before this
  ticket — ticket 001 only added the `//%` annotation to
  `engineGoToR()` in `src/shims.cpp` (the C++ side). This ticket adds
  the corresponding TS declaration plus simulator-fallback body to
  `src/blocks/sim.ts` (`//% shim=diffDrive::engineGoToR`), following the
  file's existing shim-declaration pattern — `motion.ts` had nothing to
  call otherwise.
- `goTo()` and `whileGoingTo()` (`src/blocks/motion.ts`) both call
  `startGoTo()` internally and were NOT modified — fixing `startGoTo()`
  fixes all three Move-palette blocks by construction. Confirmed by
  reading both functions: neither has its own arc/reduction math.
- `tests/host/test_goto_block_regression.py`: the OLD arc-length
  reduction (`_block_arc_reduction_to_move_x`) is renamed
  `_old_broken_block_arc_reduction_to_move_x` and its test
  (`test_old_broken_block_arc_reduction_misses_probe_targets_above_threshold`)
  now asserts ONLY the pinned historical miss (112.5 mm / 3172.4 mm) —
  the previously-red "lands within 5 mm" assertion against that same OLD
  reduction was removed, since that reduction is no longer motion.ts's
  behavior and asserting it would be asserting a falsehood. A new
  `_fixed_start_go_to_to_go_to_r()` helper transcribes `startGoTo()`'s
  actual post-fix arithmetic (cm→mm conversion, defaultSpeed/
  defaultYawRate-derived timeout, 1 mm arrive) and its test
  (`test_fixed_start_go_to_reaches_probe_targets_above_threshold`)
  asserts landing within 5 mm on both geometries — green.
- Scoped host suite (`uv run pytest tests/host/ -k "goto or
  motion_engine or manifest"`): 76 passed, 0 failed.
- Found and worked around a filed, pending, out-of-scope issue while
  writing the new `_goToR()` shim:
  `clasi/issues/int32-sim-params-break-blocks-conversion.md` documents
  that `int32`-typed params on `sim.ts` shim-fallback functions break
  JS→Blocks conversion (TS9256) and that the fix (`number` instead,
  verified hardware-safe) needs a file-wide sweep. Did not touch the
  ~10 pre-existing `int32` functions that issue names (out of scope
  here), but declared the new `_goToR()`'s own params `number` rather
  than knowingly adding an 11th instance of an already-verified defect.

## Files Expected To Change

- `src/blocks/motion.ts` — `startGoTo()` rewritten to call `goToR` shim
  directly; namespace docstring and `isMoving()` doc comment corrected.
- `tests/host/` — extend or adjust ticket 001's regression test if needed
  so it demonstrably proves the BLOCK-LAYER function (not just the shim in
  isolation) now reaches the target; TypeScript itself is never executed
  by any test in this repo (`no-lint-or-typecheck-gate.md`), so this
  remains a host-side (C++/Python) proof of the underlying reduction the
  rewritten `startGoTo` now calls, not a TS-level test.

## Test Requirement

A test that fails against today's code and passes after. Today,
`goto_probe.cpp` run against the block path measures 112.5 mm and 3172.4 mm
misses; after this ticket the same probe must land within 5 mm on both
cases. If ticket 001's new host test was written against the shim in
isolation, this ticket must confirm (and if necessary extend) that same
test's failure mode maps to `startGoTo`'s actual arithmetic before the fix
and its actual (corrected) call shape after — not merely to `goToR()`'s own
correctness, which was already proven in ticket 001 and does not change
here.
