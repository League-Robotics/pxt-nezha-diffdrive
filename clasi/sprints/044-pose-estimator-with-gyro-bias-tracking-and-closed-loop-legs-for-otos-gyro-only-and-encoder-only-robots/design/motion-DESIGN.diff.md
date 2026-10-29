---
source_file: motion-DESIGN.md
source_hash: 97953198a266d44927ad42abc0011233fe8a4ca55b8d34f2f448ecf63138e21d
---
# Diff: motion-DESIGN.md

Comparison of the sprint overlay copy of `motion-DESIGN.md` against its pristine (seed-commit) canonical version.

```diff
--- motion-DESIGN.md (pristine)
+++ motion-DESIGN.md (current)
@@ -49,6 +49,41 @@
 duplicate that content — it exists so `ls src/motion/` points
 somewhere.
 
+## pose_estimator.h — one pose from whatever sensors are fitted (sprint 044)
+
+`PoseEstimator` replaces `Odometry::fuseHeading()`. It implements
+`PoseSource` and is what `goToW()` and the closed-loop leg phases read.
+Inputs are the kernel `Output` (encoders, always), an optional
+`GyroSource` (heading rate or integrated heading, with read status) and
+an optional optical position source (the OTOS x/y). Host-portable, no
+I2C; driven by `tests/host` with scripted/simulated sensors.
+
+- **Configurations** (set by what the boot probe found, re-evaluated
+  on sensor failure): `Optical` (OTOS x/y + gyro heading), `GyroOnly`
+  (gyro heading, encoder distance along it), `EncodersOnly` (today's
+  `Odometry` maths unchanged). `Odometry` stays as the encoders-only
+  integrator inside the estimator.
+- **Heading** = gyro heading minus an estimated bias angle. There is no
+  permanent re-anchor: a rejected sample is skipped and the sensor
+  remains the reference.
+- **Bias** has two observations: ZARU (drive idle, both encoders
+  unchanged: every gyro heading change is bias; low-gain rate update)
+  and an encoder comparison in motion (running least-squares fit of
+  gyro-minus-encoder heading on [1, time, encoder net turn]). Idle
+  gyro reads must therefore continue while no move is active.
+- **Position** in `Optical` is the OTOS's own x/y increments rotated by
+  the bias-corrected heading (arm applied in software); encoders are the
+  fallback when the sensor is absent, frozen or failing.
+- **Degrade rule**: on dropout the estimator keeps the current heading
+  and carries on from the next-lower configuration, rebasing its
+  reference so no step appears in the output.
+
+Leg control (sprint 044): `goToW()` ends the pivot on estimator heading,
+steers the straight toward the world target on estimator pose, and handles
+a small final residual with a short straight. "Target behind" is an
+explicit policy (pivot then forward straight), never a near-zero-yaw
+reverse arc; a wrong-way termination is reported as its own reason.
+
 ## position_move.h — moves run by the motor's own loop
 
 `position_move.h` (`PositionMove`) is a fourth in-flight command beside
```
