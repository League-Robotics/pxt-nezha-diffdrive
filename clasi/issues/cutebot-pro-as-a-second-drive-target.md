---
status: pending
---

# Cutebot Pro as a second drive target behind a board seam

## Description

The stakeholder wants this repo's drive stack (six motion verbs,
MotionEngine, odometry, v6 wire, telemetry, tools) to run on the
ELECFREAKS Cutebot Pro as well as the Nezha fleet. The Cutebot Pro is
a one-piece micro:bit car: two encoder motors and a line sensor,
headlights, servo ports and I2C expansion behind one I2C slave at
0x10 with its own MCU. No Nezha brick, no OTOS, no RJ11 for the WiFi
module.

The analysis is `docs/design/cutebot-pro-support.md`. Its findings:

- The `DiffDrive::Motor` port is the seam. The kernel has no geometry
  and no I2C; a Cutebot port implements the same 14 virtuals against
  the Cutebot's raw PWM command (`0x10`) and per-wheel degree reads
  (`0xA0 [3|4]`). Everything above the port is untouched.
- The Cutebot's onboard speed loop cannot be the ONLY controller: the
  extension clamps it to 200..500 mm/s and reads speed back as one
  unsigned cm/s byte, and the fleet's precision regime (70 mm/s
  floor, shaped ramps, nudge) lives below that. Stakeholder direction
  2026-09-21: a HYBRID — our kernel in the slow regime, their loop at
  cruise (the doc's §3.D). The velocity setpoint is tapped from
  `MotionEngine` (a small observer hook in `motion/`), and a
  board-layer policy picks the PWM frame or the `0x80` setpoint frame
  each tick, runtime-selectable via two new config rows.
- Nezha leaks above the port in a short, enumerated list (the doc's
  §2.1): `Rig`'s concrete `NezhaMotorPort` members, diag ordinals
  reading Nezha-only fields, `configureMotor`, the fault-handler
  `diffdrive_emergency_motor_stop()` frame, `kRole = "NEZHA2"`, the
  `_MOTOR_BAKE_RES` / `EXPECTED_CPP_FILES` literals in
  `make_deploy.py`, the Nezha-only sim bus, and the WiFi UART pins.

## Proposed resolution

Two sprints (the doc's §9):

1. **Board seam, the Cutebot Pro port, and the hybrid actuation path
   on the host.** Move the §2.1 list behind a compile-time board
   composition (`platform/board.h`, baked from a new
   `geometry.firmware_bake.board` key, Nezha by default so existing
   builds are byte-identical); add `CutebotMotorPort` and a shared
   `CutebotDevice` with both the `0x10` PWM path and the `0x80`
   velocity path; the `WheelCommandTap` observer in `MotionEngine`;
   the actuation policy (off / threshold / plateau) and its two
   config rows; `sim_cutebot_bus.h` with a simulated onboard loop;
   host tests; fleet JSON for the assigned board; docs.
2. **Bring-up, calibration and the handoff on the Cutebot.** The
   doc's §8 on the real board (revision probe, raw-pulse probe,
   caliper geometry, sign bake, `fullDutyVelocity`, `travelCalib`,
   slip), then the §3.D handoff probes and a three-way tour A/B
   (`onboard_pid 0/1/2`) that picks the default policy; the WiFi pin
   answer; the servo verb for the gripper.

Open stakeholder decisions: `configure motor` semantics on fixed
wheels (§10.2), and which board is assigned — the stakeholder said
zeguz on mangi; the farm advertises zetuv on magni, currently `busy`
(§8).
