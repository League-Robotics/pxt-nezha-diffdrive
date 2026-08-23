---
id: 008
title: 'Regression: yaw taper applies only to a pure turn (bd9f005)'
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

# Regression: yaw taper applies only to a pure turn (bd9f005)

## Description

Add a dedicated, host-run regression test locking in one of the two
hard-won behaviors ticketing requirement 5 makes mandatory: the yaw
taper (the end-of-move deceleration window on the rotation axis) must
apply ONLY to a pure turn (`distance == 0`, nonzero rotation), never to
an arc (both distance and rotation nonzero) — because in an arc, twist
and velocity are locked by curvature, so the distance taper already
scales yaw, and a second independent yaw taper double-counts. This bug
was fixed on commit `bd9f005` in `src/shims.cpp`'s `serviceMove` and is
measured (three legs pinned at the 25% floor against a commanded 20,
while the one leg whose bearing fell under the straight-line threshold
ran the full 20.4). This ticket exists to make that fix fail loudly if
`motion_engine`'s port of it (ticket 007) ever regresses.

## Acceptance Criteria

- [x] A test drives `MotionEngine::moveX` with BOTH distance and
      rotation nonzero (an arc) through to completion against the
      `FakeMotor`, and asserts the commanded scale factor near the end
      of the move is governed by the DISTANCE taper window only — the
      yaw taper window plays no independent role.
- [x] A second test drives `MotionEngine::moveX` with distance `== 0`
      and rotation nonzero (a pure turn) and asserts the YAW taper
      window DOES govern the end-of-move scale factor.
- [x] A third test reproduces the specific measured signature commit
      `bd9f005` fixed: an arc whose bearing/rotation is small relative
      to its distance must NOT be pinned at the turn-floor scale for
      its whole duration (the double-counting bug's symptom) — it must
      reach a scale approaching 1.0 before its own end-of-move taper
      begins.
- [x] The test file's docstring/comment cites commit `bd9f005` and the
      measured vevov numbers from `shims.cpp`'s own comment trail, so a
      future reader can find the original incident.
- [x] This test is part of the default `uv run pytest` run (not opt-in,
      not skipped).

## Implementation Plan

**Approach**: This ticket is pure test-writing against
`motion_engine`'s already-ported `moveX`/`serviceMove`-equivalent logic
(ticket 007) — no production code should need to change unless the port
in ticket 007 got this wrong, in which case this ticket's job is to
catch that and hand it back (do not silently "fix" ticket 007's
production code as a side effect of writing this test; if a real defect
is found, treat it as this ticket's own finding against ticket 007's
acceptance criteria and fix the actual bug in `motion_engine`, not just
the test).

**Files to create**: `tests/host/test_regression_yaw_taper_pure_turn.py`
(or added as a dedicated test class inside
`test_motion_engine_reductions.py` — implementer's choice, but the
regression's identity — commit `bd9f005` — must be visible in the test
name or docstring either way).

**Files to modify**: none expected (see Approach).

**Testing plan**: This ticket IS a testing ticket; no separate
"testing plan" beyond the tests themselves.

**Documentation updates**: none beyond the test file's own
commit-citing docstring.

**Testing**

- **Existing tests to run**: `uv run pytest tests/host/` (confirms
  nothing else regressed).
- **New tests to write**: as described in Acceptance Criteria.
- **Verification command**: `uv run pytest tests/host/test_regression_yaw_taper_pure_turn.py`
