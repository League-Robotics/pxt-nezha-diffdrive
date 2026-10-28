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
