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

- **Shape** (ticket 002). `PoseEstimator(const MotionEngine&, params)`;
  `attachSensors(GyroSource*, OpticalPositionSource*, SensorConfig)`;
  `update(const Output&, dt, sampleSensors = true)` folds the encoders every
  call and reads the sensors only when `sampleSensors`, so the shim owns
  the read cadence; `seed()`/`reset()` as `Odometry`; `config()` is the
  effective configuration now; `atRest()`, `biasRate()` [rad/s],
  `rejectedCount()`, `stepCount()` feed TLM. `GyroBiasTracker`
  (`gyro_bias_tracker.h`) is the separate bias model:
  `observeRest(change, dt)`, `observeMotion(time, gyroTurn, encoderTurn)`,
  `rate()`; gains live in `GyroBiasParams`/`PoseEstimatorParams`.
  `Odometry` gained `stepCentre()`/`stepHeading()` (what the last
  `update()` folded in) and is otherwise unchanged.
- **Configurations** (set by what the boot probe found, re-evaluated
  on sensor failure): `Optical` (OTOS x/y + gyro heading), `GyroOnly`
  (gyro heading, encoder distance along it), `EncodersOnly` (today's
  `Odometry` maths, bit-identical). Position and heading are integrated
  by the estimator itself from `Odometry`'s per-update steps.
- **Heading** = gyro heading minus an estimated bias angle. There is no
  permanent re-anchor: a rejected sample is skipped (the output follows
  the encoders for that interval) and the gyro stays the reference. A
  jump that then holds steady for 3 reads becomes the new reference
  without entering the bias. Gyro heading is differenced wrap-aware.
- **Bias** has two observations. Rest (ZARU): encoders unchanged for
  0.25 s means the true rate is zero, so the heading is HELD and the gyro
  change feeds the rate (2 s windows, duration-weighted running mean that
  settles to a 180 s time constant; windows above 0.1 deg/s are steps and
  skipped). Motion: running least-squares of gyro-minus-encoder heading on
  [1, time, encoder net turn], blended by inverse variance at 0.3 trust.
  Idle gyro reads must therefore continue while no move is active (ticket 004).
- **Position** in `Optical`: the source's centre-referenced increments
  (arm already removed by the port with the chip's heading) rotated by
  corrected-heading minus raw-gyro heading, which also corrects the arm's
  heading dependence; encoder motion fills between takes. A take is
  skipped when it disagrees with the encoders (30 mm + 50%) and the source
  is dropped after 8 in a row or when it falls 40 mm short of the encoders
  beyond a 20% allowance (frozen). Increments are ignored at rest.
- **Degrade rule**: 8 failed/stale reads, or identical readings while the
  encoders turn 3 deg, drop the gyro (and with it the optical source);
  8 takes with no fix or a freeze drop only the optical source. Heading is
  already on the encoders in every such interval, so nothing steps; 10 good
  reads bring a source back with the output as the new anchor.

Leg control (sprint 044): `goToW()` ends the pivot on estimator heading,
steers the straight toward the world target on estimator pose, and handles
a small final residual with a short straight. "Target behind" is an
explicit policy (pivot then forward straight), never a near-zero-yaw
reverse arc; a wrong-way termination is reported as its own reason.

**Pivot closure** (ticket 007). When `goToW()`'s pose source reports
`hasHeadingReference()` (the estimator with a gyro up), the pivot phase
no longer hands straight to the straight phase. After the encoder pivot
arrives it rests `dwell` (250 ms, enough for fresh sensor reads), reads the
pose heading, and if the error to the bearing target (pose heading at call
plus the body-frame bearing, wrapped) exceeds the band it runs a correction
pivot of that error, then rests and reads again. Rotational slip varies per
surface and speed, so the correction is measured, not modelled; the first
pivot still uses the nominal slip. Bounded three ways: `maxCorrections` (3),
`maxCorrection` per pivot (45 deg, so a bad estimate cannot swing the robot),
and `timeout` (2500 ms from the first rest, after which the straight starts
with the heading reached; the segment deadline still spans everything). The
band is `max(deadband, omegaFloor * tick)`: a pivot cannot be finer than one
tick at the floor speed, and a smaller correction overshoots by more than it
fixes, so landing accuracy is floor-limited (about one tick of floor travel).
Correction cruise is 1 mm/s, which the shaper raises to the per-robot omega
floor, so the correction runs at the floor with no accel ramp. A source with
no heading reference (`EncodersOnly`, Odometry, OtosPort, test fakes) skips
the closure entirely: no dwell, no correction, timing unchanged. If the gyro
drops mid-closure the next evaluation ends it. The straight phase and final
residual are unchanged (ticket 008). `PivotClosure` is an engine struct with
no wire config; `lastPivotCorrections()`, `lastPivotResidual()` and
`lastPivotClosureTimedOut()` expose the last closure.

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
