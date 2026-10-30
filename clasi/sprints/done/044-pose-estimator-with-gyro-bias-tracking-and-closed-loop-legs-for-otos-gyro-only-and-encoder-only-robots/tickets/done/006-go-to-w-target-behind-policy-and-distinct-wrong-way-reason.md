---
id: '006'
title: GO_TO_W target-behind policy and distinct wrong-way reason
status: done
use-cases:
- SUC-003
depends-on:
- '002'
github-issue: ''
issue:
- otos-fusion-drifts-worse-than-the-sensor-and-legs-miss-cross-track.md
- high/goto-under-closed-profile-terminates-legs-early.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# GO_TO_W target-behind policy and distinct wrong-way reason

## Description

Make "target behind" an explicit policy in decomposeGoToR/goToW: pivot then forward straight; never a near-zero-yaw reverse arc (today theta=wrapToPi(2*bearing) turns bearing +177 deg into a -5 deg reverse arc that wrongWay kills). Report a wrong-way termination as its own stop reason (not `stop`). Host sweep over bearings including +-170..180 deg, both signs, closed and open profile. Resolves the high-priority goto-under-closed-profile issue if wrongWay is the cause; state in the ticket result whether it was.

## Acceptance Criteria

- [x] Host sweep of bearings: no leg terminates early; target behind pivots then drives forward
- [x] Wrong-way termination produces a distinct reason; unit tested
- [x] Behaviour for forward targets unchanged (existing motion_engine tests green)
- [x] Runs against FakePoseSource and the estimator in all three configurations

## Testing

- **Existing tests to run**: `uv run pytest`, `tests/host` suites touching odometry/motion_engine
- **New tests to write**: See acceptance criteria; host tests under tests/host
- **Verification command**: `uv run pytest`
