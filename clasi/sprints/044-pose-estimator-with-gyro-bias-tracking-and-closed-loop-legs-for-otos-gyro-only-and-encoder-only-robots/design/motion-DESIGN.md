# src/motion — motion engine

**Owner:** Eric Busboom · **Last reviewed:** 2026-08-26 · **Status:** stable

`motion_engine.h/.cpp` (`diffDrive::MotionEngine`) — reduces every
student-facing move (`goTo`, `moveX`, `wheelsX`, pivot, twist) to
constant-ratio wheel segments the kernel can drive. Host-portable: only
`diffdrive.h` plus libc, no I2C/CODAL dependency.

**Sprint 029** added three new host-portable files to this directory,
replacing `MotionEngine`'s inline shaping algorithms and `MoveState`:
`motion_limits.h` (`MotionLimits`, the one settable value object for
accel/decel/jerk/floors/ceilings/arrival windows), `velocity_shaper.h`/
`.cpp` (`VelocityShaper`, the one per-tick commanded-speed function used
by every entry point), and `segment.h` (`Segment`, replacing
`MoveState`). `motion_engine.h`/`.cpp` keep their public surface but
`service()` is rewritten to orchestrate these three objects instead of
running two braided algorithms inline.

**Sprint 033** added `odometry.h` (`Odometry`): the robot's
dead-reckoned pose as one host-portable object that directly implements
`PoseSource`. It absorbed `shims.cpp`'s five loose `Rig` odometry
fields, the free `odomUpdate()` over them, `platform/
encoder_pose_source.h`'s read-only adapter (deleted), and the
rebase-epoch guard — which now has exactly one reader in the codebase.
The integration math itself moved unchanged. `Odometry` reads geometry
(`countsPerMm()`/`effectiveTrackWidth()`) from `MotionEngine` by
reference and integrates whatever kernel `Output` it is handed, so it
holds no kernel and is driven directly by
`tests/host/test_odometry.py`.

**Sprint 040 ticket 003** added `wheel_command_tap.h`
(`WheelCommandTap`): a small, host-portable, optional observer
`MotionEngine` notifies with the shaped per-wheel `(left, right)` mm/s
alongside every `kernel_.drive()` call (plus that tick's
`VelocityShaper::Step::phase`), and `onNeutral()` alongside every
`kernel_.neutral()` call. It exists because the vendored kernel does
not publish what it was last commanded, only what it measured — a
board sitting below the kernel has no other way to learn the setpoint.
`MotionEngine` holds it as a nullable, non-owning pointer
(`setWheelCommandTap()`); no tap installed is byte-identical to before
this class existed. **Ticket 004**, same sprint, gives it its first
real consumer: a Cutebot-composed board installs a `CutebotTapAdapter`
(`platform/cutebot_port.h`) that converts the shaped mm/s to
`CutebotActuationPolicy`'s hybrid-actuation decision (`src/DESIGN.md`
§7). A Nezha-composed board still leaves the pointer `nullptr`.

Detail lives in [`src/DESIGN.md`](../DESIGN.md) §3. This file does not
duplicate that content — it exists so `ls src/motion/` points
somewhere.

## pose_estimator.h — one pose from whatever sensors are fitted (sprint 044)

`PoseEstimator` replaces `Odometry::fuseHeading()`. It implements
`PoseSource` and is what `goToW()` and the closed-loop leg phases read.
Inputs are the kernel `Output` (encoders, always), an optional
`GyroSource` (heading rate or integrated heading, with read status) and
an optional optical position source (the OTOS x/y). Host-portable, no
I2C; driven by `tests/host` with scripted/simulated sensors.

- **Configurations** (set by what the boot probe found, re-evaluated
  on sensor failure): `Optical` (OTOS x/y + gyro heading), `GyroOnly`
  (gyro heading, encoder distance along it), `EncodersOnly` (today's
  `Odometry` maths unchanged). `Odometry` stays as the encoders-only
  integrator inside the estimator.
- **Heading** = gyro heading minus an estimated bias angle. There is no
  permanent re-anchor: a rejected sample is skipped and the sensor
  remains the reference.
- **Bias** has two observations: ZARU (drive idle, both encoders
  unchanged: every gyro heading change is bias; low-gain rate update)
  and an encoder comparison in motion (running least-squares fit of
  gyro-minus-encoder heading on [1, time, encoder net turn]). Idle
  gyro reads must therefore continue while no move is active.
- **Position** in `Optical` is the OTOS's own x/y increments rotated by
  the bias-corrected heading (arm applied in software); encoders are the
  fallback when the sensor is absent, frozen or failing.
- **Degrade rule**: on dropout the estimator keeps the current heading
  and carries on from the next-lower configuration, rebasing its
  reference so no step appears in the output.

Leg control (sprint 044): `goToW()` ends the pivot on estimator heading,
steers the straight toward the world target on estimator pose, and handles
a small final residual with a short straight. "Target behind" is an
explicit policy (pivot then forward straight), never a near-zero-yaw
reverse arc; a wrong-way termination is reported as its own reason.

## position_move.h — moves run by the motor's own loop

`position_move.h` (`PositionMove`) is a fourth in-flight command beside
`Segment`, `Hold` and `Nudge`; exactly one of the four is live.
`MotionEngine` plans it from the same segment maths (`rotationalSlip`,
`effectiveTrackWidth`): per-wheel count targets, rounded to the port's
`positionQuantum()` with the rounding error split across the two wheels
in opposite directions, and per-wheel degrees-per-second proportional to
each wheel's share of the dominant distance so an arc's two moves finish
together. Two `beginMove()` calls go out back to back.

While a position move is live the engine still calls `kernel_.step()`,
so encoder reads, `Output` positions and `Odometry` stay continuous, but
it stages no wheel commands. Completion is both wheels within
`arriveDist`/`arriveYaw` and `atRest()`. The deadline, e-stop,
cancel and a stall test (no progress for `stallWindow` while live) end it
through `hardStop()`. `isDriving()` is true for the move's duration.
Routing between this path and the kernel is `position_mode` (config);
`WHEELS_V`, `MOVE_V`, twist and line following never use it.

`VelocityShaper` with `jerk > 0` ramps down to the speed floor and never
through it, so the last nonzero commanded speed is at least the floor.
