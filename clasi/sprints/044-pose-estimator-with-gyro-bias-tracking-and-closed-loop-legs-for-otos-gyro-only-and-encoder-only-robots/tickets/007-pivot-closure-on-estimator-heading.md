---
id: '007'
title: Pivot closure on estimator heading
status: open
use-cases: [SUC-002]
depends-on: ['002', '006']
github-issue: ''
issue: otos-fusion-drifts-worse-than-the-sensor-and-legs-miss-cross-track.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Pivot closure on estimator heading

## Description

End the pivot phase of a GO_TO_W leg on the estimator's heading rather than encoder counts (with a bounded correction and timeout so an encoders-only robot degrades to today's behaviour). Host tests with simulated rotational slip and gyro bias in all three configurations.

## Acceptance Criteria

- [ ] Pivot lands within 0.5 deg of the commanded heading on estimator heading in sim (Optical, GyroOnly); EncodersOnly unchanged within today tolerance
- [ ] Bounded: correction cannot loop; times out cleanly
- [ ] No heading discontinuity when sensor drops mid-pivot
- [ ] uv run pytest green

## Testing

- **Existing tests to run**: `uv run pytest`, `tests/host` suites touching odometry/motion_engine
- **New tests to write**: See acceptance criteria; host tests under tests/host
- **Verification command**: `uv run pytest`
