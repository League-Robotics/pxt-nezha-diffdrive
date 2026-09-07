---
status: pending
---

# `move_x` must never split; the 50° pivot-first rule belongs to `go_to` only

**Fixed 2026-09-07 out of process on master** (the commit that adds this
line): `moveX()` never splits, `Segment::dominantScale()` fixes the
blended-segment frame, simulator and docs follow, host tests
`test_move_x_arc_space.py` and `test_sim_move_is_one_arc.py` pin it.
Remaining: the bench verification listed under "A second defect" is
UNVERIFIED, and the target (PXT/GCC 5) build was not run.

## Description

`MotionEngine::moveX()` runs `(distance, rotation)` as one blended arc
below |rotation| = 50° and as pivot-then-straight at or above it
(`src/motion/motion_engine.cpp:207-210`, `kTurnFirstAngle`). That does
not approximate the requested arc, it replaces it with a different
figure: pivot-then-straight ends at `distance·(cos θ, sin θ)` while the
arc ends at `R·(sin θ, 1−cos θ)`. Endpoints differ by 22 cm for
`move_x(30 cm, 90°)`, 36 cm for `move_x(30 cm, 180°)`, and every 360°
request becomes a spin followed by a straight instead of a circle.

The 50° constant was a go-to-a-point navigator heuristic
(`radio-robot-lib/docs/design/motion-api.md` §3.3, "recovered from
`navigator.cpp:237-240`", alongside a bearing-defined `behind_angle`)
that sprint 003 ticket 007 (4027a87) transplanted onto `moveX` as a
"measured turn_first_angle". Nothing about the drivetrain was measured.
Every `(distance, rotation)` pair is a driveable constant-radius arc: the
inner wheel passes through zero at R = b/2 and reverses below it, which
is the whole physics, and the engine's blended `Segment` already drives
exactly that wheel ratio.

Full analysis with six figures, a kinematic simulation and a
`service()`+`VelocityShaper` emulation: `reports/move-x-arc-space-20260906.md`
(script and output in `reports/move-x-arc-space-20260906/`).

### Recommended rules

- `move_x(distance, rotation)`: always one blended segment, no angle
  threshold. Rotation past ±180° is more than half a turn (360° is a
  full circle, 720° two laps), never a wrap. Sign of `distance` selects
  forward or reverse along the same arc.
- `go_to(x, y)`: keeps its own split in `decomposeGoToR` (sprint 006).
  It is a legitimate policy there: the tangent arc and pivot-then-chord
  both land on the point but differ in time, lateral bulge
  (`(chord/2)·tan(bearing/2)`, the binding constraint against the field
  margin) and final heading (2·bearing vs bearing). State the threshold
  in bearing terms; do not inherit it from a `move_x` constant.
- `go to world` block: unchanged (12° bearing, `src/blocks/world.ts:152`).

### A second defect the split currently hides

By source reading (`motion_engine.cpp:282-343`, `segment.h remaining()`)
and emulation on an ideal plant: for a blended segment `dominantAxis` is
`kDistance`, so `remaining()` is measured on the mean axis while the
shaper's `vCmd`, brake budget and arrival test (`remain <= vNext·dt`)
are in the dominant-wheel frame. Identical on a straight; on a tight
arc the segment brakes on the second tick, crawls at the floor and the
arrival test fires early. Emulated `move_x(5 cm, 180°)`: 1.99 s and
−5.6° short as built, 1.32 s and −0.65° with `remaining()` on the
dominant wheel. This must be fixed in the same change as removing the
split, otherwise the newly exposed tight arcs land short. UNVERIFIED on
hardware; the report has the bench plan (wheels-up MOVE_X at 50 mm /
180°, a radius sweep reading per-wheel TLM velocity, and a 94 cm / 360°
circle from a camera fix at field centre).

### Touches

- `src/motion/motion_engine.cpp` `moveX()`: drop the
  `queuePivotThenStraight` branch; `goToR()` already bypasses it.
  Rename `kTurnFirstAngle` / `turnFirstAngle()` for what it now is, a
  `goToR` bearing policy.
- `src/motion/segment.h` `remaining()`: dominant-wheel frame for blended
  segments, with a host test asserting a tight arc reaches cruise and
  lands on both axes.
- `src/shims.cpp:594-600`: `startMove()`'s `willSplit` duration budget.
- `src/blocks/motion.ts:264`, `src/blocks/sim.ts:239`: block doc and the
  browser simulator's mirror of the split.
- `docs/design/specification.md:132`, `docs/design/usecases.md:167-193`,
  `src/DESIGN.md:221`, `motion-api.md` §3.3 (radio-robot-lib).
- `tests/host/`: `test_motion_engine_reductions.py`,
  `test_sim_pivot_then_straight_split.py`,
  `test_motion_engine_deadline_boundary.py`, `test_wire_motion_verbs.py`,
  `test_goto_turn_rate_reconciliation.py`, `test_goto_block_regression.py`,
  `test_run_tour_programs.py`,
  `test_sim_geometry_matches_kernel_and_setters_apply.py`,
  `test_heading_wrap.py`, `motion_engine_shim.cpp`.
