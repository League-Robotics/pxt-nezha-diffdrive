---
id: '010'
title: 'World-frame reduction: goToW via a pluggable PoseSource port'
status: done
use-cases:
- SUC-003
- SUC-004
depends-on:
- '007'
github-issue: ''
issue: implement-motion-api-six-operations.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# World-frame reduction: goToW via a pluggable PoseSource port

## Description

Add `MotionEngine::goToW(x, y, speed, arrive, timeout)` — the world-frame
counterpart to `goToR` (ticket 007): read the current pose from a small
new `PoseSource` port (`motion-api.md` §3.6: "the pose source is
pluggable... OTOS when fitted, encoder odometry otherwise"), transform
the world-frame delta into the body frame, and delegate to `goToR`'s
already-tested reduction. Introduce `PoseSource` as a minimal interface
(`x()`, `y()`, `heading()`) alongside `DiffDrive`'s existing four ports,
with `OtosPort` implementing it for hardware and a `FakePoseSource` in
the test harness for the host. Per sprint.md's Design Rationale, this
is the SPEC-PLAIN reduction — no re-solving mid-flight, no turn-first
heuristic, no curvature cap — a deliberately different, additive code
path from `main.ts`'s existing `goToWorld()`, which keeps its own
heuristic untouched.

## Acceptance Criteria

- [x] `PoseSource` is declared as a small interface with no CODAL/PXT
      dependency, alongside `DiffDrive::Motor`/`Clock`/`Sleeper`.
- [x] `OtosPort` (or a thin wrapper over it) implements `PoseSource` for
      hardware with no behavioral change to `OtosPort` itself.
- [x] `FakePoseSource` exists in the host harness, settable by a test to
      an arbitrary `(x, y, heading)`.
- [x] `MotionEngine::goToW` is tested against hand-computed values for
      several world-frame targets and robot poses, verifying the
      world-to-body transform and the delegated `goToR` arc solve.
- [x] `goToWorld()` in `main.ts` is unchanged — no shared code path with
      `goToW`'s implementation beyond both ultimately reaching the same
      `moveX`/kernel primitives several layers down (sprint.md Design
      Rationale's explicit "two motion paths" decision).
- [x] `test/test.ts`'s existing `tourWorld()`/`goToWorld()`-based tour
      requires no changes and is not exercised by this ticket's new
      code path.

## Implementation Plan

**Approach**: `goToW`'s implementation is a small, pure transform (read
pose, rotate the world delta into the body frame, call `goToR`) — most
of the real work is `goToR`'s own arc math, already built and tested in
ticket 007. `PoseSource` is deliberately minimal (three reads) so a
future robot with no OTOS at all (per `motion-api.md` §3.6's own
`gopiv` example) can supply a trivial always-stale implementation
without breaking the interface.

**Files to modify**: `src/motion_engine.h`/`.cpp` (add `PoseSource`
port + `goToW`), `src/otos_port.h` (implement `PoseSource`, additive —
no existing method signature changes).

**Files to create**: `tests/host/fake_pose_source.h`,
`tests/host/test_motion_engine_gotow.py`.

**Testing plan**: New host unit tests per Acceptance Criteria; no
change to any existing test.

**Documentation updates**: `motion_engine.h`'s header comment notes
`goToW`'s pose-source pluggability and cites `motion-api.md` §3.6.

**Testing**

- **Existing tests to run**: `uv run pytest tests/host/`.
- **New tests to write**: `tests/host/test_motion_engine_gotow.py` per
  Acceptance Criteria above.
- **Verification command**: `uv run pytest tests/host/`
