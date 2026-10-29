---
id: "010"
title: "Optical rest gate and disturbance handling"
status: open
use-cases: [SUC-001]
depends-on: ['004']
github-issue: ""
issue: otos-fusion-drifts-worse-than-the-sensor-and-legs-miss-cross-track.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Optical rest gate and disturbance handling

## Description

Stakeholder direction (2026-10-28): the OTOS is deliberately mounted off
the centre of rotation, and a diff-drive robot cannot translate sideways
under its own power. So with the wheels still, the raw sensor track
should not move. If it does, someone bumped or lifted the robot.

Today (ticket 002) rest means only "encoders unchanged for `restDwell`".
At rest the heading is held, and every gyro change becomes bias or a
re-referenced step, never output. A robot that is bumped or picked up
and turned keeps its old heading, and the real rotation can be folded
into the bias.

Change the estimator:

- **Optical config, rest:** encoders unchanged AND the raw sensor-track
  displacement (arm NOT applied) under a threshold over the rest window.
  Only then do ZARU and the heading hold apply.
- **Optical config, disturbed:** encoders unchanged but the raw sensor
  track moves past the threshold. This is a disturbance, not rest:
  - no ZARU update for the window;
  - the gyro change is real rotation and goes to the output heading;
  - position follows the optical track while it has a fix;
  - a lost fix (lift) degrades position as in ticket 002's dropout path;
  - count disturbances (`disturbCount()`) for TLM/STATUS, coordinated
    with ticket 005 if it has landed.
- **GyroOnly:** with no optical, a rest-window rate well above the worst
  plausible bias (ticket 002's `maxRate`) is treated as real rotation
  and output, not held as a step. Count it as a disturbance too.
- **EncodersOnly:** unchanged.
- Use the raw sensor track for the gate, not the arm-corrected centre.
  Add a raw-increment accessor to `OpticalPositionSource`/`OtosPort` if
  the existing centre increment cannot be inverted exactly.
- The arm is only applied today if the user program calls
  `setWorldSensorOffset` (ticket 004 finding; the template does not), so
  the optical increments are centre-referenced on some robots and
  sensor-referenced on others. Make the arm a firmware-known per-robot
  value independent of the user program (reuse an existing config path
  if one fits), so both the gate and the centre position are defined the
  same way on every robot.

## Evidence

- **Raw track is still at rest.** In the fleet bench runs
  (`captures/otos-gyro-fleet-20261028/`, 2026-10-28, 30 min, wheels
  still), the arm-corrected TLM `oy` crept 6/6/−12/9 mm on
  gopiv/vevov/tovez/zuvat, in 1 mm steps. That matches arm × gyro drift:
  43 mm × 7.4/7.1/−13.0/11.0° = 5.6/5.3/−9.8/8.3 mm. The creep is the
  software arm correction rotating with the drifting heading, not
  sensor motion. Set the threshold from the raw track's real floor; TLM
  is 1 mm resolution, the chip is 0.1 mm.
- **The arm is not usable as a rotation or bias observer.** In vevov's
  pivots (`captures/vevov-otos-drift-20261028/arm1.json`, 2026-10-28),
  the pivot centre slips 0.2–2.4 cm per 90° (camera), which is 3–30° of
  apparent rotation at a 4.3 cm arm. With the camera's centre motion
  included, the optical chords match within 0.6 cm rms, so the sensor is
  faithful and the robot really skids. By comparison, gyro error per
  pivot is about ±1°, and bias contributes about 0.02° per pivot.

## Acceptance Criteria

- [ ] Optical: wheels still and raw track still gives rest; ZARU and the
      hold behave as in ticket 002 (ticket 002/003 tests stay green)
- [ ] Optical: wheels still and raw track moving gives a disturbance; a
      simulated hand rotation of 30° appears in the output heading
      within 1°, and the bias estimate moves less than 2°/h
- [ ] Optical: the arm-induced centre creep at rest (gyro drift × arm)
      does not trip the gate (regression built from the fleet numbers)
- [ ] GyroOnly: a hand rotation at rest is output, not held
- [ ] Disturbance count exposed for TLM/STATUS
- [ ] Threshold and window are named params, justified from the fleet
      captures and cited
- [ ] `uv run pytest` green

## Testing

- **Existing tests to run**: `tests/host/test_pose_estimator.py`,
  `tests/host/test_pose_estimator_replay.py`, `tests/host/test_gyro_source.py`
- **New tests to write**: disturbance cases above via SimGyro + scripted optical
- **Verification command**: `uv run pytest`
- **Hardware (in ticket 009):** with a robot still on the camera, bump it
  and lift-and-turn it (stakeholder does the handling); check that the
  disturbance count increments and the heading follows the camera.
