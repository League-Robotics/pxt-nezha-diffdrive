---
id: "005"
title: "Simulator: mirror the 50-degree pivot-then-straight split in _startMove, drift-tested against kTurnFirstAngle"
status: open
use-cases: [SUC-004]
depends-on: ["004"]
github-issue: ""
issue: "simulator-split-parity-and-geometry-drift.md"
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Simulator: mirror the 50-degree pivot-then-straight split in _startMove, drift-tested against kTurnFirstAngle

## Description

Confirmed in current `src/blocks/sim.ts`: `_startMove(distance, yaw,
speed, yawRate)` (line ~130) sets `simMoveRemainDist`/`simMoveRemainYaw`
and `simIntegrate()` (line ~40) applies BOTH the linear velocity and
the yaw rate to every step SIMULTANEOUSLY (`mid = simHeading +
stepYawRate*stepDt/2; simX += stepVel*stepDt*cos(mid)...`) — a single
blended arc, for any combination of distance and yaw, regardless of
magnitude. Confirmed in `src/motion/motion_engine.h` (line ~405):
`kTurnFirstAngle = 0.8726646f` (50° in radians) is the real threshold
`MotionEngine::moveX()`/`goToR()` use to split a large-rotation move
into pivot-then-straight instead of one blended arc. The literal
example from the issue (`move(47, 90)`) is real: hardware would pivot
90° in place then drive 47 cm straight (ending 0 cm forward / 47 cm
left of start), while the CURRENT simulator blends both simultaneously
(ending roughly 30 cm forward / 30 cm left, per the issue's own
figures — reverify the exact numbers as part of this ticket rather than
citing the issue's uncited figure verbatim).

This ticket is sequenced after ticket 004 (both touch `sim.ts`-adjacent
argument/dispatch plumbing only tangentially, but 004 settles the
dispatch layer first so this ticket's own host tests aren't chasing a
moving target in `run.ts`).

## Acceptance Criteria

- [ ] `_startMove()` (or `simIntegrate()`, whichever is the cleaner
      seam) splits into two SEQUENTIAL phases — pivot then straight —
      whenever `distance != 0 && |yaw| >= ` the shared threshold,
      exactly mirroring `MotionEngine::moveX()`'s own condition
      (`distance != 0.0f && std::fabs(rotation) >= kTurnFirstAngle`).
      Use the EXISTING `simMoveRemainDist`/`simMoveRemainYaw` fields for
      the phase bookkeeping (per the Solution text) rather than
      inventing new state — e.g. zero one of the two remain-fields
      during the pivot phase and populate it only once the pivot
      completes, or add a minimal phase flag if the existing fields
      can't cleanly express "not started yet."
- [ ] The threshold value itself is NOT re-typed as a second literal in
      `sim.ts`. It is drift-tested against
      `MotionEngine::kTurnFirstAngle`/`turnFirstAngle()`'s real value —
      add or extend a host test that reads both the TS constant and the
      C++ constant (via whatever mechanism `tests/host/`'s existing
      kernel-parity tests already use — check
      `tests/host/test_motion_engine_primitives.py` and neighbors for
      the house pattern before inventing a new one) and asserts they
      match to a tight tolerance.
- [ ] Below the threshold, behavior is UNCHANGED (still one blended
      step, matching `MotionEngine::moveX()`'s own `else` branch) —
      this ticket only adds the split branch, it doesn't change the
      existing under-threshold math.
- [ ] `move()`'s own JSDoc (`src/blocks/motion.ts`) no longer claims
      "Drive a distance while turning a yaw angle... Both at once makes
      an arc" unconditionally — state the actual behavior (blended
      below the threshold, pivot-then-straight at/above it), matching
      whatever wording `startGoTo()`'s own doc comment already uses to
      describe the analogous native-side split, for consistency.
- [ ] A worked numeric example (`move(47, 90)` or equivalent) is added
      as a host test asserting the simulator's END POSITION now matches
      the pivot-then-straight geometry (0 forward / 47 left, or the
      correct sign/frame per this repo's CCW-positive convention —
      verify the sign against `src/DESIGN.md`'s coordinate-frame
      section, don't assume the issue's own figure got the sign right).

## Testing

- **Existing tests to run**: `uv run pytest tests/host/` (this changes a simulator kinematics function; search `tests/host/` for any existing sim-related test file first — e.g. `test_sim_*.py` — to know what's already pinned).
- **New tests to write**: the threshold drift test and the worked-example end-position test described above; both as new tests or extensions of an existing sim test file (prefer extending if a natural home already exists).
- **TS type-check**: `npx tsc --noEmit`; STRONGLY prefer also running a real `pxt build` in `.tmp/` for this ticket specifically, since it changes actual simulator RUNTIME behavior that only a real PXT/simulator build can prove compiles and runs (a source-pin/tsc-only check proves shape, not that the simulator body executes) — note in the commit message which was actually run.
- **Verification command**: `uv run pytest tests/host/ -k "sim" -v`
