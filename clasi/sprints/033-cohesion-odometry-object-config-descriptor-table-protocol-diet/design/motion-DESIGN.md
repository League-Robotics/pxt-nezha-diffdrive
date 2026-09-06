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

Detail lives in [`src/DESIGN.md`](../DESIGN.md) §3. This file does not
duplicate that content — it exists so `ls src/motion/` points
somewhere.
