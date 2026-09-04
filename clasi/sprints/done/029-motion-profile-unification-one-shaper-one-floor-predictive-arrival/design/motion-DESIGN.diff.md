---
source_file: motion-DESIGN.md
source_hash: 2f7546468f63bab61ff3d6e1eb5bab5af8549b5a81c64e45f2b24cd35c808d5e
---
# Diff: motion-DESIGN.md

Comparison of the sprint overlay copy of `motion-DESIGN.md` against its pristine (seed-commit) canonical version.

```diff
--- motion-DESIGN.md (pristine)
+++ motion-DESIGN.md (current)
@@ -7,6 +7,16 @@
 constant-ratio wheel segments the kernel can drive. Host-portable: only
 `diffdrive.h` plus libc, no I2C/CODAL dependency.
 
+**Sprint 029** added three new host-portable files to this directory,
+replacing `MotionEngine`'s inline shaping algorithms and `MoveState`:
+`motion_limits.h` (`MotionLimits`, the one settable value object for
+accel/decel/jerk/floors/ceilings/arrival windows), `velocity_shaper.h`/
+`.cpp` (`VelocityShaper`, the one per-tick commanded-speed function used
+by every entry point), and `segment.h` (`Segment`, replacing
+`MoveState`). `motion_engine.h`/`.cpp` keep their public surface but
+`service()` is rewritten to orchestrate these three objects instead of
+running two braided algorithms inline.
+
 Detail lives in [`src/DESIGN.md`](../DESIGN.md) §3. This file does not
 duplicate that content — it exists so `ls src/motion/` points
 somewhere.
```
