---
source_file: platform-DESIGN.md
source_hash: f4a87ae23b728ce4b81e60ddc624cf46c0d76bb1718cc9d735640b8022ffe7b5
---
# Diff: platform-DESIGN.md

Comparison of the sprint overlay copy of `platform-DESIGN.md` against its pristine (seed-commit) canonical version.

```diff
--- platform-DESIGN.md (pristine)
+++ platform-DESIGN.md (current)
@@ -4,11 +4,15 @@
 
 The hardware port implementations: `NezhaMotorPort` (`nezha_port.*`,
 motor + encoder over I2C 0x10), `OtosPort` (`otos_port.*`, the optical
-world sensor), `platform_ports.h` (the port interfaces they implement),
-and `encoder_pose_source.h` (the host-portable dead-reckoning
-`PoseSource` fallback `goToW()` uses on OTOS-less robots). Everything
-here is CODAL/`pxt.h`-bound except `encoder_pose_source.h`, which is
-host-portable (only `motion_engine.h` + libc).
+world sensor), and `platform_ports.h` (the port interfaces they
+implement). Everything here is CODAL/`pxt.h`-bound.
+
+Sprint 033 removed this directory's one host-portable file,
+`encoder_pose_source.h` — the dead-reckoning `PoseSource` fallback
+`goToW()` uses on OTOS-less robots is now `Odometry`
+(`../motion/odometry.h`), which computes the pose it reports instead of
+adapting fields someone else computed, and lives with the rest of the
+motion layer.
 
 Detail lives in [`src/DESIGN.md`](../DESIGN.md) §7. This file does not
 duplicate that content — it exists so `ls src/platform/` points
```
