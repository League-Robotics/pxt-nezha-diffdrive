---
id: 009
title: Hardware acceptance on OTOS and encoder-only robots
status: open
use-cases: [SUC-001, SUC-002, SUC-003]
depends-on: ['008', '005']
github-issue: ''
issue: otos-fusion-drifts-worse-than-the-sensor-and-legs-miss-cross-track.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Hardware acceptance on OTOS and encoder-only robots

## Description

Camera-truthed acceptance. (a) vevov (OTOS): 100 m random run with tests/dev/otos_drift.py, no camera re-zero, plus stationary 30 min with tests/dev/otos_gyro.py. (b) tigez (encoders only, chosen by the stakeholder 2026-10-28): same leg run, checking no wrong-way stalls and arrival accuracy. Score with otos_drift_report.py; write results to captures/ with date and board; every measured figure cites its capture file per .claude/rules/measurement-citations.md; anything not run is marked UNVERIFIED. Follow the repo rules for connecting to a robot, camera-checked steps, and not driving blind. Requires stakeholder-arranged robot access.

## Acceptance Criteria

- [ ] OTOS: pose error <= 15 cm rms, heading <= 3 deg rms (2nd half), zero wrong-way stalls
- [ ] OTOS: arrival median < 1 cm, p90 < 2 cm
- [ ] Stationary 30 min: heading change < 2 deg after settling
- [ ] tigez (encoders only): zero stalls; arrival results recorded (target documented honestly if sensor-less accuracy is lower)
- [ ] Captures committed under captures/ and cited

## Testing

- **Existing tests to run**: `uv run pytest` (host suites unaffected)
- **New tests to write**: Hardware runs described above
- **Verification command**: `uv run pytest`
