---
id: 008
title: Straight steering on estimator pose and final residual trim
status: open
use-cases: [SUC-002]
depends-on: ['007']
github-issue: ''
issue: otos-fusion-drifts-worse-than-the-sensor-and-legs-miss-cross-track.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Straight steering on estimator pose and final residual trim

## Description

Straight phase steers toward the world target on estimator pose (cross-track feedback with a clamped yaw trim), so pivot error and slip are corrected while driving. A final residual <= ~3 cm becomes a short straight/reverse instead of a re-pivot up to 90 deg. Host tests in all three configurations with injected pivot error; assert cross-track error at arrival.

## Acceptance Criteria

- [ ] Injected 2 deg pivot error yields < 1 cm cross-track at arrival in sim (Optical, GyroOnly)
- [ ] EncodersOnly runs steering on odometry pose without regression
- [ ] Residual <= 3 cm handled without a pivot
- [ ] Tour/goToW existing tests green

## Testing

- **Existing tests to run**: `uv run pytest`, `tests/host` suites touching odometry/motion_engine
- **New tests to write**: See acceptance criteria; host tests under tests/host
- **Verification command**: `uv run pytest`
