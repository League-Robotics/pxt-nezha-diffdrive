---
source_file: design.md
source_hash: d7ca714866f7d9335d3bf6dc0496d1faf48224561013cdbacabbe8453a36d5ae
---
# Diff: design.md

Comparison of the sprint overlay copy of `design.md` against its pristine (seed-commit) canonical version.

```diff
--- design.md (pristine)
+++ design.md (current)
@@ -237,7 +237,17 @@
 
 ### Sensor doctrine
 
-The OTOS world sensor is consulted at **move boundaries only** — a
+**Sprint 044 supersedes the next sentence's "move boundaries only".**
+Sensors feed one `PoseEstimator` (`motion/pose_estimator.h`) that runs
+continuously, including at rest, and legs steer on its pose in flight.
+Three sensor configurations are first-class, detected by probe at boot
+and each host-tested: OTOS (optical x/y plus gyro heading), gyro-only
+(any `GyroSource` plus encoder distance), encoders-only. A sensor that
+drops out degrades to the next configuration without a heading jump.
+Gyro bias is estimated on the host (ZARU at rest, encoder comparison in
+motion); the chip's one-shot calibration is not trusted.
+
+Previously: The OTOS world sensor is consulted at **move boundaries only** — a
 move runs entirely on encoder odometry and is never steered in flight.
 The overhead camera is a diagnostic, never a control input. All OTOS
 I2C traffic shares a bus with the Nezha encoder and must never land
```
