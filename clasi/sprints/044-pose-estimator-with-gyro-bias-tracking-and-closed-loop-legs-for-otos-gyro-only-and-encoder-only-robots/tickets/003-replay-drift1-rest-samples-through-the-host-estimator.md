---
id: '003'
title: Replay drift1 rest samples through the host estimator
status: done
use-cases:
- SUC-001
- SUC-004
depends-on:
- '002'
github-issue: ''
issue: otos-fusion-drifts-worse-than-the-sensor-and-legs-miss-cross-track.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Replay drift1 rest samples through the host estimator

## Description

Host test replaying `captures/vevov-otos-drift-20261028/drift1.jsonl` (and gyro1.jsonl rest samples) through the host-built estimator, asserting it reproduces the issue's replay numbers (causal bias ~+52 deg/h vs camera +47 deg/h; 2nd-half heading rms ~3 deg; stationary run settles to < 2 deg change). The log is the fixture; state tolerances in the test and cite the capture file per .claude/rules/measurement-citations.md.

## Acceptance Criteria

- [x] Test loads drift1.jsonl and gyro1.jsonl (copied unmodified to tests/host/fixtures/pose_estimator/, since captures/ is gitignored)
- [x] Estimated bias within stated tolerance of the issue figures; tolerances justified in test header with artifact citation
- [x] Gyro-only variant (encoder distance, same heading) also asserted
- [x] Fleet stationary fixtures (gopiv, vevov, tovez, zuvat) hold heading < 2 deg over 30 min after settling, in OPTICAL and GYRO_ONLY, and the learned rate tracks the logged rate
- [x] uv run pytest green

## Testing

- **Existing tests to run**: `uv run pytest`, `tests/host` suites touching odometry/motion_engine
- **New tests to write**: See acceptance criteria; host tests under tests/host
- **Verification command**: `uv run pytest`
