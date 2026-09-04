---
source_file: design.md
source_hash: 76db1cd8fe26bef92fad34c8c73d65b56f71989d06819599c6c7e42e0afaf63a
---
# Diff: design.md

Comparison of the sprint overlay copy of `design.md` against its pristine (seed-commit) canonical version.

```diff
--- design.md (pristine)
+++ design.md (current)
@@ -101,6 +101,21 @@
 `effectiveTrackWidth() = trackWidth / rotationalSlip` is always
 computed fresh, never cached, so a config read-back can never report a
 derived number as though it had been measured.
+
+### Motion-shaping authority (sprint 029)
+
+The speed floor and every acceleration/jerk/arrival limit are owned by
+one object, `MotionLimits`, consulted by one per-tick function,
+`VelocityShaper` — both in `src/motion/`. The kernel
+(`DifferentialDrive`) tracks whatever wheel velocity it is given and
+applies no floor of its own (`vMin = 0` in the fleet bake); this is a
+deliberate divergence from `radio-robot-lib`'s `motion-api.md` §4,
+which lists a "ratio-preserving speed floor" as a kernel feature — the
+ratio is still preserved, only the policy of *when* to floor moved up
+to the layer that knows which axis is dominant and in what units. See
+`src/DESIGN.md` §3 for the full object model and
+[`docs/design/motion-profile-unification.md`](../../docs/design/motion-profile-unification.md)
+for the design rationale.
 
 ### Protocol versioning
 
```
