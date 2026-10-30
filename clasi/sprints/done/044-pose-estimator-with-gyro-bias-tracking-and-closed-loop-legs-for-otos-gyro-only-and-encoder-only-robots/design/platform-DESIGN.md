# src/platform — hardware ports

**Owner:** Eric Busboom · **Last reviewed:** 2026-09-21 · **Status:** stable

The hardware port implementations, plus the compile-time seam
(sprint 040) that composes one board's set of them into `shims.cpp`'s
`Rig` without `Rig` (or anything above it) knowing which board it got:

- **Board composition** (`board.h` + `board_nezha.cpp` /
  `board_cutebot.cpp`) — one literal, `DIFFDRIVE_BOARD`
  (`DIFFDRIVE_BOARD_NEZHA` / `DIFFDRIVE_BOARD_CUTEBOT_PRO`, defaulting
  to Nezha), selected by `tools/make_deploy.py`'s
  `geometry.firmware_bake.board` bake key. Each `board_*.cpp` builds,
  behind its own `#if`, that board's concrete `DiffDrive::Motor` pair,
  the `configureMotor()`/`diagValue()` wiring and diag hooks, the
  per-board `diffdrive_emergency_motor_stop()` fault-context frame, and
  (sprint 040 ticket 004) the board's `WheelCommandTap`/onboard-mode
  hooks — Nezha's are documented no-ops, since a `WheelCommandTap` and
  an onboard speed loop only mean something on a Cutebot. `board.h`
  itself is host-portable (reaches only `core/diffdrive.h`,
  `core/motor_wiring.h`, `motion/wheel_command_tap.h`); each
  `board_*.cpp` reaches `pxt.h` only inside `#ifndef
  DIFFDRIVE_HOST_BUILD`, guarding just its fault-context frame's real
  `uBit.i2c.write()`, and is not host-linkable as a whole even so — its
  singleton constructs its ports through a default I2C-bus argument
  only the target defines.
- **`NezhaMotorPort`** (`nezha_port.*`) — the ElecFreaks Nezha brick's
  motor + encoder over I2C 0x10, implementing all 14 `DiffDrive::Motor`
  calls (`begin`/`requestSample`/`setDuty`/`emergencyStop`/`tick`/
  `position`/`velocity`/`appliedDuty`/`connected`/`sampleTime`/
  `rebaseline`/`wedged`/`wedgeSuspect`). PXT/CODAL-bound except for the
  shaping pipeline and encoder path, which build and run on the host
  under `-DDIFFDRIVE_HOST_BUILD` and are exercised by `sim_tour.py`.
- **`CutebotMotorPort` + `CutebotDevice`** (`cutebot_port.*`, sprint 040
  ticket 002) — the ELECFREAKS Cutebot Pro's port, also implementing
  all 14 `DiffDrive::Motor` calls, against a shared `CutebotDevice` both
  wheels' ports bind to (the Cutebot takes both wheels' duties in ONE
  `0x10` frame). `CutebotDevice` owns the 0x10 slave's session state:
  the cached revision probe, v2 frame encode/decode, the coalesced PWM
  write, the `0xA0` encoder reads (degrees ×10 = kernel counts), and —
  since ticket 004 — staging the tap's shaped setpoint and shipping
  whichever frame `CutebotActuationPolicy` picks (`0x10` PWM or `0x80`
  onboard setpoint) each cycle. Fully host-portable — no `pxt.h`
  anywhere in this file, not even guarded, unlike every other file in
  this directory; host-tested directly against a simulated 0x10 slave
  (`tests/host/sim_cutebot_bus.h`, `test_cutebot_port.py`,
  `test_cutebot_hybrid_actuation.py`).
- **`CutebotActuationPolicy`** (`cutebot_actuation_policy.*`, sprint 040
  ticket 004) — the pure, per-tick decision between the kernel's PWM
  duty and the Cutebot's onboard `0x80` setpoint: a function of the
  staged duties, the tapped setpoint, the configured mode/floor, and
  the previous engaged/disengaged state, returning the frame to ship
  and the new state. No I2C, no `CutebotDevice`, no `MotionEngine`, no
  kernel reference — host-tested with zero bus in the link
  (`test_cutebot_actuation_policy.py`), the same isolation
  `MotionLimits`/`VelocityShaper` get in `motion/`.
- **`OtosPort`** (`otos_port.*`) — the SparkFun OTOS optical world
  sensor, implementing `PoseSource`.
- **`platform_ports.h`** — the `Clock`/`Sleeper`/`FiberLauncher`
  interfaces every board's ports are built against.

Everything here is CODAL/`pxt.h`-bound **except** `board.h`,
`cutebot_port.*`, and `cutebot_actuation_policy.*`, which are
host-portable by construction (no `pxt.h` at all) and are host-tested
directly rather than only proved by a hex checkpoint.

`otos_port.cpp`, `vfp_guard.cpp` and `microbit_i2c_bus.cpp` are the
exception to the exception: since sprint 044 ticket 011 they compile on
the host against a stub `pxt.h` inside the `shims.cpp` host build, so the
real `OtosPort` runs over a simulated OTOS slave
(`tests/host/sim_otos_bus.h`). The stub is test scaffolding; the files
themselves are unchanged.

Sprint 033 removed this directory's one previously host-portable file,
`encoder_pose_source.h` — the dead-reckoning `PoseSource` fallback
`goToW()` uses on OTOS-less robots is now `Odometry`
(`../motion/odometry.h`), which computes the pose it reports instead of
adapting fields someone else computed, and lives with the rest of the
motion layer.

Detail lives in [`src/DESIGN.md`](../DESIGN.md) §1 (layer map) and §7
(the full behavioral detail for every port, the board-composition seam,
and the actuation policy). This file does not duplicate that content —
it exists so `ls src/platform/` points somewhere.

## gyro_source.h and sensor_config.h — generic gyro interface (sprint 044)

`GyroSource` is the narrow interface the pose estimator reads a heading
sensor through: `readGyro()` (status ok / failed / stale), integrated
`gyroHeading()` and/or `gyroRate()` (`providesHeading()` /
`providesRate()` say which), and `present()`. A stale read succeeded
but delivered no new sample; a failed one left the latched values
untouched. `OpticalPositionSource` is the optional companion:
`opticalPresent()`, `opticalValid()` and
`takeOpticalIncrement(dx, dy, rawDx, rawDy)`, the centre-position change
since the previous take plus the sensor's own track with the lever arm
not applied (false on the take that only re-baselines, after the first
read or a `setPose()`).

The lever arm belongs to the robot: `geometry.firmware_bake.otos_arm_x` /
`otos_arm_y` ([mm], body frame, signed) in the robot's radio-robot-lib
config are baked into `OtosPort::bakedArmX_/Y_` by `make_deploy.py`, the
same path as `otos_angular_scale`. `otos_linear_scale` (`linearScale_`)
is baked the same way and written to the chip's linear scalar register
in `begin()` (value = round((scale - 1) / 0.001), clamped to +-127).
Measure it from straights on camera: scale = camera / OTOS. A lever arm
measured in the chip's own units must be multiplied by the same scale. A non-zero baked arm wins:
`setOffset()` (the `setWorldSensorOffset` block) then changes only the
sensor yaw. With no baked arm the program's offset applies, as before.
The template never calls it, so before this the centre was sensor-
referenced on every robot that didn't.

Implementations: `OtosPort` (target-only, `otos_port.h`; both
interfaces, fed by the one burst `read()`), and `SimGyro`
(`tests/host/sim_gyro.h`; configurable bias, temperature-like wander,
noise, dropout, freeze, read failure). Both headers here are
host-portable and in the C++11 gate.

`sensor_config.h` holds `SensorConfig {kOptical, kGyroOnly,
kEncodersOnly}` and `probeSensorConfig(gyro, optical)`: a gyro counts
only if present and its first `readGyro()` is not kFailed; optical
additionally needs `opticalPresent()`. The caller (shims, ticket 004)
runs `OtosPort::begin()` first.

Follow-on (no ticket yet): the real driver for the non-OTOS gyro part,
once the part is chosen, implements `GyroSource` only. `OtosPort` is
also read while idle, by `idleSense()` at 10 Hz from the protocol fiber's
idle pass under the bus guard (DESIGN.md, Sprint 044). It does not re-run
`calibrateImu()` after stillness; that stays a fallback only if software
bias tracking fails the stationary criterion on hardware.

## Position moves, the move-live latch and the two speed paths

`NezhaMotorPort` implements `DiffDrive::PositionMotor`
(`core/position_motor.h`) as well as `Motor`.

- **Position move.** `beginMove()` writes `0x77 <deg/s>` (per port,
  only when the value changed) then `0x70` direction mode 2 with the
  distance in integer degrees; quantum 10 counts. `hardStop()` writes
  `0x5F` (servo hold at the current count).
- **Move-live latch.** From `beginMove()` until completion,
  `hardStop()` or e-stop, `setDuty()` is a no-op and `driven()` is true.
  This is what keeps the kernel's stop-enforcement (`setDuty(0)` every
  tick while a wheel reads above rest) from sending `0x60 0`, which
  would cancel the brick's move. `emergencyStop()` on a live move sends
  `0x5F` first, then `0x60 0`. No `0x60` frame is written to a live
  port.
- **Speed path (`speed_path`).** 0 (default) is the `0x60` integer
  percent actuator with sigma-delta dither. 1 sends `0x77 round(pct x
  11.5)` (only on change) plus `0x70` direction mode 3 timed run
  (`(10n-3) x 100 ms`, n = 1) per change; the deadband, dwell, slew and
  throttle stay in front, the dither is bypassed, and a stop from speed
  is `0x5F`.
- **Stops.** Every stop path (`Rig::softStop()`, the starvation
  watchdog, `endMove()`, `STOP`, `ESTOP`, `configureWiring()`, the
  fault-context `diffdrive_emergency_motor_stop()`) hard-stops a live
  move or a wheel above the floor first. The fault frame covers ports
  M1 to M4.

Never send brick opcode `0x1D` (motor reset). The opcode map and the
measured tables are in `docs/knowledge/2026-10-27-nezha-brick-opcodes.md`.
`tests/host/sim_nezha_bus.h` implements the brick behaviour the
reference records.
