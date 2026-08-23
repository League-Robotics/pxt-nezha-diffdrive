---
id: '006'
title: 'Motion engine extraction, part 1: geometry and the two wheel primitives (wheelsX,
  wheelsV)'
status: done
use-cases:
- SUC-003
- SUC-004
depends-on:
- '001'
github-issue: ''
issue: implement-motion-api-six-operations.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Motion engine extraction, part 1: geometry and the two wheel primitives (wheelsX, wheelsV)

## Description

Create `src/motion_engine.h`/`.cpp` — a new, host-portable module
(depends only on `DiffDrive::Motor`/`Clock`/`Sleeper`/`FiberLauncher`
and `DiffDrive::DifferentialDrive`, no CODAL/PXT type) — and extract
`shims.cpp`'s `Rig` geometry (`countsPerMm()`, `effectiveTrackWidth()`
— renamed from `effectiveTrack()`, computed the same way, `trackwidth /
rotational_slip`, still never a stored field) plus the two wheel
primitives, `wheelsX` (per-wheel commanded distance, cruise, timeout —
genuinely new: no prior primitive in this codebase commands independent
per-wheel distances) and `wheelsV` (renamed from the existing
`setWheels`/`driveTwistTimed` velocity-hold behavior — same math, same
lease semantics, no reinterpretation). `shims.cpp`'s `//%` functions
for `setWheelSpeeds`/`driveTwist`/the timed variants become thin
forwards into `MotionEngine`; observable block behavior is unchanged.
This ticket does NOT yet move the taper/ramp/settle move-engine
(`serviceMove`) — that is ticket 007, kept separate because it is a
different responsibility (shaping vs. the primitive reduction) that
changes for different reasons.

## Acceptance Criteria

- [x] `MotionEngine::effectiveTrackWidth()` is a method, never a stored
      field, computed as `trackwidth / rotational_slip`; no test or
      code path adjusts `trackwidth` itself to correct a turn (sprint.md
      Success Criteria — a standing project rule).
- [x] `MotionEngine::wheelsV(left, right, duration)` produces
      byte-for-byte the same kernel `drive()` call
      `setWheels`/`driveTwistTimed` produce today, verified against the
      `FakeMotor` for hand-computed values.
- [x] `MotionEngine::wheelsX(left, right, cruise, timeout)` is new: unit
      tests against hand-computed values, plus the degenerate cases
      `wheels_x(+d, -d)` (pivot) and `wheels_x(d, d)` (straight line).
- [x] Sign convention (CCW-positive; positive `omega`/rotation turns
      left; the left wheel is the slower one in a left turn) is tested
      explicitly in BOTH directions, so a future cable-order "fix"
      fails a test instead of shipping (sprint.md Test Strategy).
- [x] `shims.cpp`'s `setWheelSpeeds`/`driveTwist` blocks (and their
      timed-variant callers) behave identically before and after —
      verified by the existing block-level contract, not just by the
      new engine's own unit tests.
- [x] `src/motion_engine.{h,cpp}` are added to `pxt.json`'s `files`
      array.
- [x] No `//%` shim signature grows to 5+ `int32` parameters as a side
      effect of this refactor (the documented PXT build trap).

## Implementation Plan

**Approach**: `MotionEngine` takes a `DiffDrive::DifferentialDrive&`
(constructed by its caller — `shims.cpp` for hardware, the host harness
for tests) plus the geometry constants (`trackwidth`, `rotational_slip`,
`travelCalib`) — mirroring `Rig`'s existing fields exactly, just moved
to a class that does not also own the concrete `NezhaMotorPort`
instances. `shims.cpp` keeps constructing the concrete ports and the
kernel (as `ensure()` does today) and hands the kernel reference to a
`MotionEngine` instance it also owns via the same lazy-singleton
pattern (sprint.md Design Rationale: "motion_engine exposes one
lazy-singleton instance... mirroring shims.cpp's own existing
`ensure()`/`Rig*` pattern"). The host harness constructs its OWN
`MotionEngine` directly over `FakeMotor`s — per that same Design
Rationale, the harness does not use the singleton accessor.

**Files to create**: `src/motion_engine.h`/`.cpp`.

**Files to modify**: `src/shims.cpp` (`Rig`'s geometry fields and
`setWheels`/`driveTwist`/`setWheelsTimed`/`driveTwistTimed` become
thin forwards into `MotionEngine`), `pxt.json` (`files`).

**Testing plan**: New host unit tests for `wheelsX`/`wheelsV` and
`effectiveTrackWidth()`; existing block-level behavior is protected by
this ticket keeping the observable contract identical (no PXT test
changes needed — `test/test.ts` exercises `move`/`goTo`, which this
ticket does not touch; `setWheelSpeeds`/`driveTwist` are exercised by
`testrig.ts`'s drum-speed commands, which must keep working).

**Documentation updates**: `motion_engine.h`'s header comment states
the two-primitive model and cites `motion-api.md` §2/§2.1 as authority.

**Testing**

- **Existing tests to run**: `uv run pytest tests/host/` (all prior
  tickets' suites).
- **New tests to write**: `tests/host/test_motion_engine_primitives.py`
  per Acceptance Criteria above.
- **Verification command**: `uv run pytest tests/host/`
