---
id: 008
title: Straight steering on estimator pose and final residual trim
status: done
use-cases:
- SUC-002
depends-on:
- '007'
github-issue: ''
issue: otos-fusion-drifts-worse-than-the-sensor-and-legs-miss-cross-track.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Straight steering on estimator pose and final residual trim

## Description

Straight phase steers toward the world target on estimator pose (cross-track feedback with a clamped yaw trim), so pivot error and slip are corrected while driving. A final residual <= ~3 cm becomes a short straight/reverse instead of a re-pivot up to 90 deg. Host tests in all three configurations with injected pivot error; assert cross-track error at arrival.

## Acceptance Criteria

- [x] Injected 2 deg pivot error yields < 1 cm cross-track at arrival in sim (Optical, GyroOnly)
- [x] EncodersOnly runs steering on odometry pose without regression
- [x] Residual <= 3 cm handled without a pivot
  - **Reverse exception, for stakeholder review**: decision 3 (target behind = pivot then forward) stands. Reverse is allowed ONLY for a final residual within the 30 mm band that is mostly along the heading, so a 1 cm overshoot is backed off instead of pivoting up to 180 deg. Parameter `ResidualTrim::band`.
- [x] Tour/goToW existing tests green
  - One existing test edited: `test_pivot_closure.py::test_slip_without_closure_misses_so_the_closure_is_what_lands_it` now also turns steering off, because steering now corrects the heading that test was measuring.

## Testing

- **Existing tests to run**: `uv run pytest`, `tests/host` suites touching odometry/motion_engine
- **New tests to write**: See acceptance criteria; host tests under tests/host
- **Verification command**: `uv run pytest`

## Notes (ticket 008)

- Steering: line from the pose at straight start to the target, wanted heading = line heading - atan(crossTrack/150 mm), trim = 4 /s x error, clamped 20 deg/s and 15% of the dominant wheel speed. Residual trim: band 30 mm, 2 trims, 3 s.
- Sim sweep (6 bearings x 4 distances 100-1000 mm x slip 1/1.05/0.95 x bias 0/+-150 deg/h, sensors every 4th tick, default floors): Optical median 0.9 / p90 3.8 mm, GyroOnly 0.8 / 3.6 mm (open loop 2.0 / 6.5). EncodersOnly 15.2 / 83.1 mm (open loop 14.9 / 89.3): the unobserved slipped rotation, not a defect.
- Arcs (|bearing| < 25 deg) are not steered; they are one blended segment.
- Optical short moves from rest: the estimator drops the first optical samples as at-rest (ticket 010), so the pose lags truth by ~6 mm on a 20 mm move; the trim closes the pose, not the truth.
