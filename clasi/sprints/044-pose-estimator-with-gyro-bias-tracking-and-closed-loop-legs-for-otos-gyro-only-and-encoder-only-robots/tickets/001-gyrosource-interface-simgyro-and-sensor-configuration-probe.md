---
id: '001'
title: GyroSource interface, SimGyro and sensor-configuration probe
status: open
use-cases: [SUC-001]
depends-on: []
github-issue: ''
issue: otos-fusion-drifts-worse-than-the-sensor-and-legs-miss-cross-track.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# GyroSource interface, SimGyro and sensor-configuration probe

## Description

Define the generic gyro interface and the three-way sensor configuration, so everything downstream is testable without hardware.

- `platform/gyro_source.h`: host-portable interface (read status ok/failed/stale, integrated heading and/or rate, present()). Optional optical-position companion interface (x/y increments + validity).
- `OtosPort` implements both (adapter only; no behaviour change). Note: `otos_port.h` includes `pxt.h`, so the adapter lives in a target-only file; the interface header is host-portable.
- `SimGyro` (tests/host): configurable constant bias, temperature-like wander, noise, dropout, frozen output, I2C-style read failures.
- Configuration enum {Optical, GyroOnly, EncodersOnly} and a boot probe that selects it from what is present (probe logic host-testable via fakes).
- Document the follow-on: real driver for the non-OTOS gyro part, once chosen, implements `GyroSource` only.

## Acceptance Criteria

- [ ] Interface header compiles host-side under the C++11 syntax gate
- [ ] SimGyro supports bias, wander, noise, dropout, freeze, read failure
- [ ] Probe selects each of the three configurations from fakes; unit tested
- [ ] OtosPort adapter builds on target with no behaviour change
- [ ] Follow-on ticket text for the real gyro driver noted in the sprint/ticket

## Testing

- **Existing tests to run**: `uv run pytest`, `tests/host` suites touching odometry/motion_engine
- **New tests to write**: See acceptance criteria; host tests under tests/host
- **Verification command**: `uv run pytest`
