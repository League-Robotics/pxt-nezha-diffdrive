---
source_file: calibration-DESIGN.md
source_hash: 57693301403afbe11ac5d301e14f38a5869871984269b65f5eafca433ab4b443
---
# Diff: calibration-DESIGN.md

Comparison of the sprint overlay copy of `calibration-DESIGN.md` against its pristine (seed-commit) canonical version.

```diff
--- calibration-DESIGN.md (pristine)
+++ calibration-DESIGN.md (current)
@@ -1,6 +1,6 @@
 # tests/calibration — the on-robot calibration programs
 
-**Owner:** Eric Busboom · **Last reviewed:** 2026-09-05 · **Status:**
+**Owner:** Eric Busboom · **Last reviewed:** 2026-09-06 · **Status:**
 active (consolidated here 2026-09-05 from `tests/playfield/` and
 `tools/field_dance.py` at the stakeholder's direction: "a small number
 of solid tests we're going to use for testing and calibration".
@@ -16,13 +16,15 @@
 
 ## Entry point
 
-`calibrate.py <dance|turns|lag|distance> [args]` runs the program of
-that name; every program also runs on its own. All share one carrier /
-camera option set (`--robot`, `--wifi NAME|IP`, `--radio`, `--host/--port`
-for a Pi serial daemon, `--camera`, `--field-cm W H`, `--margin`) and one
-safety posture: a fresh camera fix before every move, the projected end
-pose checked against the field limits less the margin, and pivots-only
-programs refusing inside the margin.
+`calibrate.py <dance|turns|lag|distance|mount|acceptance> [args]` runs
+the program of that name; every program also runs on its own. The
+CALIBRATION programs share one carrier / camera option set (`--robot`,
+`--wifi NAME|IP`, `--radio`, `--host/--port` for a Pi serial daemon,
+`--camera`, `--field-cm W H`, `--margin`) and one safety posture: a
+fresh camera fix before every move, the projected end pose checked
+against the field limits less the margin, and pivots-only programs
+refusing inside the margin. `acceptance` is not a calibration program
+and does not share that option set -- see its row below.
 
 | program | what it measures | result |
 |---|---|---|
@@ -32,6 +34,52 @@
 | `lag_measure.py` | step-response drivetrain lag from `WHEELS_V` + `TLM FULL` (design S10.2) | `lag_s` per wheel; `--apply` SETs the mean |
 | `distance.py` | camera-scored straights out and back at several lengths | fit gain/offset; `travel_calib` suggestion |
 | `mount.py` | tag lever/height from in-place pivots, yaw residual from a probe | writes `tools/field_calibration.json`, registers the daemon |
+| `consolidation_acceptance.py` | NOT a calibration: sprint 034's on-field acceptance of the consolidated link, camera and geofence. `--dry-run` prints the plan and opens nothing | PASS/FAIL/BLOCKED per check, appended to `captures/consolidation-acceptance-<robot>-<date>/notes.md` |
+
+## `acceptance` -- the one program here that is not a calibration
+
+`consolidation_acceptance.py` (sprint 034 ticket 013) measures nothing
+a config carries. It answers three questions the host suite cannot,
+because every one of them is proved host-side against an injected fake
+and a fake cannot be switched off, mounted crooked, or driven into a
+rail:
+
+a. a `MOVE_X` sent through the consolidated `robotlink.Link` is
+   acknowledged **and the robot moves**, scored from the overhead
+   camera and never from the wire -- odometry cannot detect its own
+   failure to move, and a switched-off robot acks, reports the full
+   commanded distance, and shows `ready=1 connL=1 connR=1`;
+b. the in-process `Cam` reads the same poses the deleted camera
+   subprocess did: a registered mount, a robot on a known dot, the
+   daemon's corrected heading used **unchanged**. It computes the
+   travel bearing error and names the `+90 applied twice` signature
+   explicitly when it sees one;
+c. `Repositioner.go()` refuses a real out-of-bounds target with
+   **nothing on the wire**, and does not refuse a legitimate one.
+
+It differs from its neighbours in three ways, each deliberate:
+
+- **The robot is POSITIONAL and the carriers are the connecting rule's**
+  (`--wifi-tcp` the default, `--radio`, `--serial HOST:PORT`), not
+  `--robot`/`--wifi`/`--host`/`--port`. It is run by a person following
+  `.claude/rules/connecting-to-a-robot.md` once, not by an operator
+  moving between calibration steps.
+- **It writes to `--capture-dir`, not `--out`.** Its artifact is a
+  capture a later MEASURED citation points at, so it goes under
+  `captures/` -- which is gitignored, so the run prints the `git add -f`
+  reminder and so does the file.
+- **`--dry-run` prints the whole plan** -- every command line that would
+  go out -- and opens no carrier, no camera and no socket.
+
+A non-PASS pre-flight (lights, `PING`, the field-centre tag at world
+(0, 0), this robot's tag visible and registered) stops the run before
+any move is armed, and the three checks are recorded `BLOCKED` rather
+than skipped in silence. `BLOCKED` is a finding about the bench and
+`FAIL` a finding about the code; collapsing them is how a dark room
+reads as a broken camera.
+
+Host-side tests: `test_consolidation_acceptance.py` (55 cases -- fake
+link, fake camera, no robot, no daemon, no network).
 
 ## The calibration order (stakeholder, 2026-09-05)
 
@@ -113,6 +161,24 @@
 - Heading comes from the camera with the fixed +90 deg front-edge
   convention (`.claude/rules/tag-yaw-is-the-front-edge-not-the-hat.md`);
   `--heading-offset` exists only for the sub-degree physical residual.
+- The wire is `tools/link.py`'s. `turn_calibration.py` builds its
+  carriers on `linklib.Sequencer`/`LineBuffer` and tunes the relay with
+  `linklib.relay_setup_lines()` against `RELAY_HOST`/`RELAY_PORT`,
+  rather than the private sequencer and the hard-coded `radio_group`
+  fallback of 10 it carried before. Both halves of the address now come
+  from radio-robot-lib's per-robot config — the deploy-time authority
+  for what is actually baked into the board — with NO default for
+  either (`robot_radio()`). A relay tuned to the right channel and the
+  wrong group is a silent robot with nothing to say why, so a missing
+  key raises instead of guessing.
+- Angles wrap through `tools/field.py`'s `wrap()` and nothing else —
+  **(-180, 180]**, upper end closed, so exactly half a revolution reads
+  `+180`. `turn_calibration.py` and `field_dance.py` each carried a
+  private copy closing the *other* end until sprint 034 ticket 009;
+  ±180 is in the standard pivot set, so that was a real disagreement
+  about a commanded value. `turn_calibration` re-exports the shared
+  function, which is how `mount.py` and `distance.py` reach it as
+  `tc.wrap`.
 - Sample heading at REST, never windowed across a move (the windowing
   reverses the sign of the pivot error; project memory
   `odometry-closure-tuning-knobs`).
```
