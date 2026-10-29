---
id: '007'
title: Pivot closure on estimator heading
status: done
use-cases:
- SUC-002
depends-on:
- '002'
- '006'
- '011'
github-issue: ''
issue: otos-fusion-drifts-worse-than-the-sensor-and-legs-miss-cross-track.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Pivot closure on estimator heading

## Description

End the pivot phase of a GO_TO_W leg on the estimator's heading rather than encoder counts (with a bounded correction and timeout so an encoders-only robot degrades to today's behaviour). Host tests with simulated rotational slip and gyro bias in all three configurations.

## Acceptance Criteria

- [x] Pivot lands within 0.5 deg of the commanded heading on estimator heading in sim (Optical, GyroOnly); EncodersOnly unchanged within today tolerance
  - Measured on sim truth: within 0.5 deg only with the sim omega floor at 10 deg/s (288/288 cases). At the default 20 deg/s floor, within 1.0 deg. A correction cannot be finer than one tick of travel at the floor speed (about 0.48 deg at 20 deg/s, about 1.5 deg on zetuv's 60 deg/s pivot floor). Real-robot landing is bounded by that quantum; ticket 008's cross-track steering absorbs the remainder. Annotated by team-lead 2026-10-28.
- [x] Bounded: correction cannot loop; times out cleanly
- [x] No heading discontinuity when sensor drops mid-pivot
- [x] uv run pytest green

## Testing

- **Existing tests to run**: `uv run pytest`, `tests/host` suites touching odometry/motion_engine
- **New tests to write**: See acceptance criteria; host tests under tests/host
- **Verification command**: `uv run pytest`
