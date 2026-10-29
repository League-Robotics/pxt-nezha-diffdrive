---
id: '002'
title: PoseEstimator with bias tracking and degradation
status: done
use-cases:
- SUC-001
depends-on:
- '001'
github-issue: ''
issue: otos-fusion-drifts-worse-than-the-sensor-and-legs-miss-cross-track.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# PoseEstimator with bias tracking and degradation

## Description

Implement `PoseEstimator` (motion/pose_estimator.h) replacing `Odometry::fuseHeading()`. Odometry stays as the encoder integrator inside it. Keep the bias model a separate small class (`GyroBiasTracker`) so the estimator does not become a god object.

- Heading = gyro heading minus estimated bias; never a permanent re-anchor (a rejected sample is skipped, sensor stays the reference).
- Bias: ZARU while idle and encoders unchanged (low-gain rate update, subtract accumulated change); encoder comparison while moving (running least-squares fit of gyro-minus-encoder heading on [1, time, encoder net turn]).
- Position: OTOS x/y increments rotated by corrected heading with the 4.3 cm arm applied in software when Optical; encoder distance along heading when GyroOnly; plain Odometry when EncodersOnly.
- Dropout/freeze detection degrades to the next configuration with no heading step.
- Host test shim + pytest for all three configurations driven by SimGyro and scripted encoder Outputs.

## Acceptance Criteria

- [x] Estimator is a PoseSource; EncodersOnly output equals existing Odometry golden frames
- [x] Constant simulated bias (50 deg/h) is learned and removed at rest and in motion in Optical and GyroOnly
- [x] Slowly ramping bias (0 to +-35 deg/h over 30 min) and a large constant bias (+-150 deg/h): a 30-min stationary SimGyro run holds heading change under 2 deg after settling, in Optical and GyroOnly (the sprint's stationary criterion)
- [x] Rejected samples never produce a persistent heading offset (regression for fuseHeading re-anchor)
- [x] Dropout and freeze mid-run: heading step < 1 deg at the transition, all config pairs
- [x] test_odometry goldens still pass; uv run pytest tests/host green

## Testing

- **Existing tests to run**: `uv run pytest`, `tests/host` suites touching odometry/motion_engine
- **New tests to write**: See acceptance criteria; host tests under tests/host
- **Verification command**: `uv run pytest`
