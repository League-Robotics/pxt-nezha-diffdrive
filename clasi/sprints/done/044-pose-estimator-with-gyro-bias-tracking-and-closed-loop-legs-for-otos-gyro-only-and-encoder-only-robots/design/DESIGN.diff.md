---
source_file: DESIGN.md
source_hash: 37a3418d2a2ed5db4c955f00d363c2827a0e1500d7d918bb43f43be9430c042a
---
# Diff: DESIGN.md

Comparison of the sprint overlay copy of `DESIGN.md` against its pristine (seed-commit) canonical version.

```diff
--- DESIGN.md (pristine)
+++ DESIGN.md (current)
@@ -585,6 +585,21 @@
 end the move through `hardStop()` on both wheels. `STATUS` carries
 `posmove=` while a position move is live.
 
+### Sprint 044 — pose estimator and leg control
+
+`PoseEstimator` (`motion/pose_estimator.h`) replaces
+`Odometry::fuseHeading()` as the `PoseSource` `goToW()` reads; `Odometry`
+remains its encoder integrator. `tickDrive()` feeds it encoder output
+every tick and gyro/OTOS samples every 4th tick while driving and at a
+low rate while idle (the idle path must run without a TS
+`while (_tickDrive())` loop being active — the ticket decides the
+mechanism, bounded by the §8/§9 single-executor rule). `goToW()` legs:
+pivot ends on estimator heading; straight steers on estimator pose
+toward the world target; a residual <= ~3 cm is a short straight;
+target-behind uses pivot-then-straight. `Segment::wrongWay` termination
+sets a distinct stop reason and `wrng` appears in STATUS. TLM FULL gains
+`bias` (cdeg/min) and a reject counter (§5).
+
 ## 4. Wire grammar — `comms/wire_handler.h/.cpp` (`Wire::WireHandler`)
 
 **Responsibility.** Protocol v6's ASCII line-grammar mechanics plus
@@ -1626,6 +1641,16 @@
 a host test exercises directly, proving the same LSB round-trip
 (350° → −10°) the real register write would produce without needing
 I2C in the link.
+
+**Sprint 044 — `GyroSource` and the sensor configurations.**
+`platform/gyro_source.h` defines the generic gyro interface
+(read status, integrated heading and/or rate). `OtosPort` implements it
+(and additionally supplies optical x/y); the host `SimGyro` implements
+it for tests; the non-OTOS gyro part's driver is a follow-on. The boot
+probe sets the configuration (OTOS / gyro-only / encoders-only) and
+`motion/pose_estimator.h` (§3, §9) consumes it. `OtosPort` is read while
+the robot is idle as well as driving, under the same bus guard and on the
+same fiber that ticks the kernel (the §7 bus invariant is unchanged).
 
 **`EncoderPoseSource` — RETIRED in sprint 033, replaced by `Odometry`
 (`motion/odometry.h`, §9).** Sprint 006 added it here as a second
```
