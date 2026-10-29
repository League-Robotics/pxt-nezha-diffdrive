---
source_file: platform-DESIGN.md
source_hash: 5449b22f381e75238604230bc3f1b816e90e8f57efa9cd871a326e3f4271a37a
---
# Diff: platform-DESIGN.md

Comparison of the sprint overlay copy of `platform-DESIGN.md` against its pristine (seed-commit) canonical version.

```diff
--- platform-DESIGN.md (pristine)
+++ platform-DESIGN.md (current)
@@ -76,6 +76,18 @@
 and the actuation policy). This file does not duplicate that content —
 it exists so `ls src/platform/` points somewhere.
 
+## gyro_source.h — generic gyro interface (sprint 044)
+
+`GyroSource` is the narrow interface the pose estimator reads a heading
+sensor through: `read()` (status: ok / failed / stale), integrated
+`heading()` and/or `rate()`, and `present()`. Implementations: the
+OTOS adapter (`OtosPort`, heading channel; also exposes x/y as the
+optional optical source), and `SimGyro` for host tests (configurable
+bias, temperature-like wander, noise, dropout, freeze). The real driver
+for the non-OTOS gyro part is a follow-on once the part is chosen; it
+implements this interface only. `OtosPort` additionally gains an idle
+sampling path and may re-run `calibrateImu()` after verified stillness.
+
 ## Position moves, the move-live latch and the two speed paths
 
 `NezhaMotorPort` implements `DiffDrive::PositionMotor`
```
