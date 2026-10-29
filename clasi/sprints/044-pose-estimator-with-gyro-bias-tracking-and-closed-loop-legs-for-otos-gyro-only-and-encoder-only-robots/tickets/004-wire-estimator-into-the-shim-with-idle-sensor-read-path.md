---
id: '004'
title: Wire estimator into the shim with idle sensor read path
status: open
use-cases: [SUC-001, SUC-004]
depends-on: ['002']
github-issue: ''
issue: otos-fusion-drifts-worse-than-the-sensor-and-legs-miss-cross-track.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Wire estimator into the shim with idle sensor read path

## Description

Integrate the estimator into shims.cpp: boot probe selects configuration; tickDrive() feeds encoders every tick and gyro/OTOS on the existing cadence; engineGoToW() selects the estimator as its PoseSource; remove fuseHeading() use. Add the idle sensor read path: today the OTOS is read only inside the TS `while (_tickDrive())` loop, so at rest nothing reads it and ZARU is blind. Decide the mechanism (candidate: idle tick from the existing executor / a low-rate idle service on the kernel-ticking fiber) within the bus-guard rule (every OTOS transaction on the fiber that ticks the kernel) and the single-executor rule; document the decision in the overlay. Optional: re-run calibrateImu after ~1 s verified stillness only if ZARU alone misses the stationary criterion.

## Acceptance Criteria

- [ ] Idle sensing reads at a few Hz with the robot stationary and no move active; TLM ox/oy/oh update at rest
- [ ] Bus guard respected; no read inside the encoder settle window (existing bus tests green)
- [ ] No OTOS fitted: behaviour identical to today (encoders-only)
- [ ] Idle-path mechanism and its rationale recorded in design overlay/DESIGN.md
- [ ] Firmware builds (pxt build) and uv run pytest green

## Testing

- **Existing tests to run**: `uv run pytest`, `tests/host` suites touching odometry/motion_engine
- **New tests to write**: See acceptance criteria; host tests under tests/host
- **Verification command**: `uv run pytest`
