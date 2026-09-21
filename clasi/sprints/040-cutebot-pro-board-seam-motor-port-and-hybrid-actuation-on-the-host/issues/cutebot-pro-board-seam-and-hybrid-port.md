---
status: in-progress
sprint: '040'
tickets:
- 040-001
- 040-002
- 040-003
- 040-004
- 040-005
- 040-006
- 040-007
- 040-008
---

# Cutebot Pro: board seam, motor port, and the hybrid actuation path (host side)

## Description

First half of the Cutebot Pro arc. Analysis and design:
`docs/design/cutebot-pro-support.md` (§2.1 for the refactor list,
§3.A and §3.D for the port and the hybrid, §4 for board selection,
§7 for the host tests).

The ELECFREAKS Cutebot Pro is a one-piece micro:bit car behind one
I2C slave at 0x10: two encoder motors driven by raw PWM (`0x10`) or
by an onboard speed loop (`0x80`, 200..500 mm/s), per-wheel degree
reads (`0xA0 [3|4]`), a line sensor, servos, headlights. The
`DiffDrive::Motor` port is the seam; the kernel has no geometry and
no I2C. Nezha leaks above the port in an enumerated list: `Rig`'s
concrete `NezhaMotorPort` members, diag ordinals reading Nezha-only
fields, `configureMotor`, the fault-handler
`diffdrive_emergency_motor_stop()` frame, `kRole = "NEZHA2"`,
`_MOTOR_BAKE_RES` / `EXPECTED_CPP_FILES` in `make_deploy.py`, the
Nezha-only sim bus, the WiFi UART pins.

Stakeholder direction 2026-09-21: a HYBRID — our kernel drives the
slow regime (ramps, taper, nudge, pivots with an inner wheel under
the floor), the Cutebot's onboard loop takes cruise.

## Proposed resolution

All host-side; ends with a hex that builds and a host hybrid tour
that closes. No robot needed.

1. Board seam: move the §2.1 list behind a compile-time board
   composition (`platform/board.h` + `board_nezha.cpp` /
   `board_cutebot.cpp`), selected by a new
   `geometry.firmware_bake.board` key in `make_deploy.py`, Nezha by
   default so every existing fleet build is byte-identical. Host
   suite green throughout.
2. `CutebotMotorPort : DiffDrive::Motor` and a shared `CutebotDevice`
   for the 0x10 slave: revision probe at `begin()`, both wheels'
   duties coalesced into ONE `0x10` frame per kernel cycle, degrees
   x10 = counts, held `sampleTime()` on a NACK, per-board emergency
   stop frame.
3. `WheelCommandTap`: an optional observer `MotionEngine` notifies
   with the shaped `(left, right)` mm/s alongside every
   `kernel_.drive()` and "neutral" alongside every `kernel_.neutral()`
   (`motion_engine.cpp:368`, `:406`, and the neutral sites).
4. `CutebotActuationPolicy`: a pure function picking the PWM frame or
   the `0x80` setpoint frame per tick — modes off / threshold-with-
   hysteresis / plateau-only — gated on BOTH wheels being eligible;
   two new `config_fields.h` rows, `onboard_pid` and `onboard_floor`,
   so the mode is runtime-selectable and `onboard_pid 0` is the escape
   hatch.
5. `tests/host/sim_cutebot_bus.h` (v2 frames, revision probe, encoder
   degrees from `SimWheel`, `0x50` clear, and `0x80` as a simulated
   onboard loop with the 200 mm/s clamp), a port shim and tests, tap
   and policy tests, `sim_tour.py --board cutebot-pro`, the pxt-bound
   TU list and `EXPECTED_CPP_FILES` updated.
6. Fleet JSON for the assigned board in `radio-robot-lib`
   (`hardware_model`, `firmware_bake.board`), `pxt.json` files, docs
   (`src/platform/DESIGN.md`, `src/DESIGN.md` §7, `design.md` layer
   table).

Open stakeholder decision: `configure motor` on fixed wheels —
sign-only flip, or refuse the block (§10.2).
