---
source_file: motion-DESIGN.md
source_hash: 7af7d705bde9bb9f63e3f84dedcf47fe92533c16e2aa4c7770908c76d5088e85
---
# Diff: motion-DESIGN.md

Comparison of the sprint overlay copy of `motion-DESIGN.md` against its pristine (seed-commit) canonical version.

```diff
--- motion-DESIGN.md (pristine)
+++ motion-DESIGN.md (current)
@@ -17,6 +17,18 @@
 `service()` is rewritten to orchestrate these three objects instead of
 running two braided algorithms inline.
 
+**Sprint 033** added `odometry.h` (`Odometry`): the robot's
+dead-reckoned pose as one host-portable object that directly implements
+`PoseSource`. It absorbed `shims.cpp`'s five loose `Rig` odometry
+fields, the free `odomUpdate()` over them, `platform/
+encoder_pose_source.h`'s read-only adapter (deleted), and the
+rebase-epoch guard — which now has exactly one reader in the codebase.
+The integration math itself moved unchanged. `Odometry` reads geometry
+(`countsPerMm()`/`effectiveTrackWidth()`) from `MotionEngine` by
+reference and integrates whatever kernel `Output` it is handed, so it
+holds no kernel and is driven directly by
+`tests/host/test_odometry.py`.
+
 Detail lives in [`src/DESIGN.md`](../DESIGN.md) §3. This file does not
 duplicate that content — it exists so `ls src/motion/` points
 somewhere.
```
