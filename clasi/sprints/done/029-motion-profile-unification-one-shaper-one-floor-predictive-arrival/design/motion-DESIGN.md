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

Detail lives in [`src/DESIGN.md`](../DESIGN.md) §3. This file does not
duplicate that content — it exists so `ls src/motion/` points
somewhere.
