---
source_file: DESIGN.md
source_hash: d4ebfa5cd480799eae01d245f72d1287adc585a251079ab3f59ea262ddabb7ac
---
# Diff: DESIGN.md

Comparison of the sprint overlay copy of `DESIGN.md` against its pristine (seed-commit) canonical version.

```diff
--- DESIGN.md (pristine)
+++ DESIGN.md (current)
@@ -11,17 +11,31 @@
 ## Link layer — what everything talks through
 
 - **`robotlink.py`** — one `Link` object that talks to the robot over
-  USB serial or the zavaz radio relay (`--radio`; channel 4, group
-  10 — vevov's assignment; never retune getez's channel 3). Both
-  carriers deliver the same ASCII lines. The split matters: the USB
-  cable only reaches the bench stand where the wheels are off the
-  ground, so anything needing real motion runs untethered over radio.
+  USB serial or the zavaz radio relay (`--radio`). **Sprint 029**: the
+  channel/group are no longer a hardcoded constant
+  (`ZAVAZ_CHANNEL`/`ZAVAZ_GROUP`, stale since vevov's 2026-08-30 move to
+  37/43) — the relay address is derived from the board name (the same
+  base-5 `!N` derivation the relay itself uses,
+  `radio-address-derived-from-board-name`) or read from
+  `field_calibration.json` when present, so a board reassignment no
+  longer requires a source edit here to stay reachable. Both carriers
+  deliver the same ASCII lines. The split matters: the USB cable only
+  reaches the bench stand where the wheels are off the ground, so
+  anything needing real motion runs untethered over radio.
 - **`camlink.py`** — persistent gRPC stream to the aprilcam overhead-
-  camera daemon. Carries the hard-won registration rules in its
-  docstring: tag mount parameters are not persisted across daemon
-  restarts, units are centimetres, vevov's tag mounts a quarter-turn
-  round (`mount_yaw_rad = -pi/2`) — an unregistered tag reports a
-  plausible but wrong position.
+  camera daemon. **Sprint 029**: `field_calibration.json` is now the one
+  calibration of record for tag mounts — `camlink.py` loads it and no
+  longer re-registers a mount as a side effect of merely constructing
+  `Cam` (the previous `MOUNTS` table and `ensure_registered()`'s
+  unconditional `register_tag()` call are deleted). Registration only
+  happens on an explicit `--register` invocation, so starting any tool
+  can no longer silently overwrite the aprilcam daemon's persistent
+  registry with a stale mount — the exact shape of the 2026-08-31 rails
+  crash and the 2026-09-02 finding that motivated this fix
+  (`one-calibration-of-record-camlink-robotlink.md`). The stored mount
+  residual is the sub-degree physical correction only; the fixed +90°
+  yaw convention (`tag-yaw-is-the-front-edge-not-the-hat.md`) is never
+  re-derived or stored as a probe-fitted value. Units remain centimetres.
 
 ## Build / deploy
 
```
