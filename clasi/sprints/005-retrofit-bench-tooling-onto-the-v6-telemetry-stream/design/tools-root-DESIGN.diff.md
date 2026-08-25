---
source_file: tools-root-DESIGN.md
source_hash: 5dc145ef7916e1d6fe9f3b95e1835000021fb3d3ba532737ea67e825d7d1b216
---
# Diff: tools-root-DESIGN.md

Documents the new `tools/tlm.py` telemetry parser and its fail-loud
guards, the new `tools/camproc.py`/`tools/field.py` link-layer/camera
consolidation, the `pyserial` dependency fix, and retargets every
tour/ground-truth/rig tool's description onto its real named RUN verb
— replacing the "Known limitation" section (now "Resolved") that
described the v5 telemetry gap and the dead numeric RUN vocabulary
this sprint closes.

```diff
--- tools-root-DESIGN.md (pristine)
+++ tools-root-DESIGN.md (current)
@@ -1,12 +1,16 @@
 # tools — bench and diagnostic tooling
 
-**Owner:** Eric Busboom · **Last reviewed:** 2026-08-24 · **Status:** stable (host side of the retired cleartext vocabulary — see the telemetry note below; `make_deploy.py`'s `build()` is now triage-aware, see "Build checkpoint triage" below)
+**Owner:** Eric Busboom · **Last reviewed:** 2026-08-24 · **Status:** stable (sprint 005: `tools/tlm.py` retrofits all six telemetry consumers onto the v6 `thdr`/`t` frame with fail-loud guards, `tools/camproc.py`/`tools/field.py` consolidate the camera/link-layer duplication, and the numeric-RUN-vocabulary and testFiles build-hygiene defects are fixed; `make_deploy.py`'s `build()` remains triage-aware, see "Build checkpoint triage" below)
 
 Host-side Python scripts for building, deploying, driving, measuring,
 and charting the robot. Flat root, no subsystems. Run under `uv`
-(`uv run python tools/<script>.py`); `camlink.py` runs under the
-aprilcam pipx venv instead. Conventions (units, frames, camera
-doctrine) are in [`docs/design/design.md`](../docs/design/design.md).
+(`uv run python tools/<script>.py`) — including `robotlink.py`, now
+that `pyproject.toml` declares `pyserial` (sprint 005; previously only
+the system interpreter had it); `camlink.py` still runs under the
+aprilcam pipx venv, its interpreter resolved once by `camproc.py`
+rather than hardcoded per spawn site. Conventions (units, frames,
+camera doctrine) are in
+[`docs/design/design.md`](../docs/design/design.md).
 
 ## Link layer — what everything talks through
 
@@ -22,7 +26,40 @@
   restarts, units are centimetres, vevov's tag mounts a quarter-turn
   round (`mount_yaw_rad = -pi/2`) — an unregistered tag reports a
   plausible but wrong position.
+- **`camproc.py`** (sprint 005) — owns camera-subprocess lifecycle:
+  resolves the AprilTags interpreter once (not six hardcoded spawn
+  sites), surfaces a spawned camera's `ERR` lines to the calling tool
+  instead of discarding them, and invalidates a cached pose once the
+  stream is marked dead — a mid-session camera death is now a visible
+  failure, not a silently frozen pose fed back into `place()`/`fix()`.
+- **`field.py`** (sprint 005) — owns playfield geometry: the dot/corner
+  constants, `wrap()`, and corner scoring that used to be copied into
+  seven separate `Cam` wrapper scaffolds (with two incompatible
+  `latest` tuple orders) across the tour/ground-truth tools. Consumes
+  `camlink.py`'s existing shared `Cam` rather than re-wrapping it.
 
+## Telemetry (`tlm.py`, sprint 005)
+
+- **`tlm.py`** — the single place any v6 telemetry scale factor is
+  written. `TlmStream` tracks the `thdr` column header (re-emitted by
+  firmware at ~1 Hz so a late-attaching consumer can resync) and feeds
+  `t` lines, exposing `frames`, `orphan_frames` (a `t` before any
+  header), `malformed` (a `t` whose value count disagrees with the
+  header — the defense against `RadioTransport`'s 200-byte line
+  truncation), and `dropped`/`loss_pct` (from `seq` gaps — a 7-bit
+  wrapping counter at 20 Hz). Unit-conversion helpers (`pose_cm`,
+  `otos_cm`, `wheels_mms`) live here too. Three fail-loud guards make
+  "the instrument returned nothing" a loud, immediate failure instead
+  of a silent empty CSV: `require_stream(link, timeout=3.0)` aborts
+  *before* a run is triggered if no `t` frame arrives; `write_tlm_csv()`
+  raises rather than writing a header-only CSV; a `<stem>_tlm.meta.json`
+  sidecar (frames/dropped/loss_pct/orphan_frames/malformed/columns/
+  duration) lets `tour_chart.py`/`practice_chart.py` refuse to plot a
+  zero-frame run. All six tour/ground-truth consumers listed below
+  import `tlm.py` instead of parsing wire lines themselves — see the
+  "Known limitation" section this replaced, kept below as a resolved
+  note for history.
+
 ## Build / deploy
 
 - **`make_deploy.py`** — builds a flashable hex in a scratch copy of
@@ -123,11 +160,18 @@
 
 - **`tour_run.py`** — the canonical run: camera used exactly twice
   (seed at start, score at end); the robot drives all four legs on its
-  own sensors; no radio round-trips inside the tour.
+  own sensors; no radio round-trips inside the tour. Records via
+  `tlm.py`; aborts before starting if `require_stream()` finds no
+  telemetry.
 - **`tour_capture.py`** / **`tour_watch.py`** — telemetry recorders
-  (triggered vs. button-watch); write the pose/wheel CSVs.
+  (triggered vs. button-watch); write the pose/wheel CSVs plus the
+  `tlm.py` `.meta.json` sidecar (frames/dropped/loss_pct). Both tools'
+  own pre-sprint-005 field-count arity checks (`tour_watch.py:202`'s
+  `len(f) == 7`, `tour_capture.py:70`'s 7/4/3-length ladder) are gone —
+  `tlm.py` owns arity now.
 - **`tour_chart.py`** / **`practice_chart.py`** — the standard
-  matplotlib plots of those CSVs.
+  matplotlib plots of those CSVs; refuse to plot a run whose
+  `.meta.json` sidecar reports `frames == 0`.
 - **`tour_practice.py`** — repeated camera-scored runs from the start
   dot, repositioning between runs.
 - **`tour_square.py`**, **`tour_closedloop.py`** — earlier variants
@@ -139,12 +183,21 @@
 
 - **`pivot_truth.py`** / **`truth_check.py`** — camera vs. OTOS vs.
   odometry for rotations: is the robot misbehaving or the sensor
-  mis-reporting?
+  mis-reporting? Drive `test.ts`'s named `pivot`/`fix` RUN verbs
+  (sprint 005; previously sent dead numeric `RUN:2/4/5/10` offsets that
+  matched no handler on named-verb-only firmware).
 - **`rotation_check.py`** — commanded vs. gyro-measured rotation
-  (floor + radio only; on the bench the body never rotates).
+  (floor + radio only; on the bench the body never rotates). Same
+  named-verb retargeting as `pivot_truth.py`/`truth_check.py`.
 - **`turn_sweep.py`** — turn accuracy vs. yaw rate, camera-scored.
+  Drives `test.ts`'s named `turnrate`/`pivot` verbs (sprint 005;
+  previously `RUN:57000+rate`/`RUN:58360+deg`, also dead numeric
+  offsets).
 - **`otos_levercal.py`** — fits the OTOS lever arm from pivot circles
-  (produced the 38.2 mm arm baked into `test/test.ts`).
+  (produced the 38.2 mm arm baked into `test/test.ts`). Drives
+  `test.ts`'s already-named `RUN:cal`/`RUN:cal:1` (sprint 005; a
+  Python-side rename only — `RUN:8`/`RUN:14` never matched a handler,
+  but `cal` always did).
 - **`reposition.py`** — put the robot on a world point, camera-
   verified, seeding from measured truth rather than assumed placement.
 
@@ -153,22 +206,22 @@
 - **`otos_bench.py`** — chainable subcommands driving
   `test/testrig.ts`'s numeric `RUN:<n>` vocabulary on the zeguz drum
   rig (probe, zero, stream, calibrate, servo, drum speed, lever arm).
+  `testrig.ts`'s own two-arg `onRunCommand` dispatch bug (it stored the
+  always-zero `arg` instead of the parsed numeric `name`, so every
+  command silently reached no branch) is fixed as of sprint 005; this
+  tool's own commands are unchanged.
 
-## Known limitation — the telemetry gap
+## Resolved (sprint 005): the telemetry gap and the dead RUN vocabulary
 
-These tools speak the **old cleartext vocabulary** (`RUN:` commands
-in; `TLM:`/`DIAG`/`OCAL:`-style lines back). Sprint 003's v6 cutover
-retired the firmware's periodic `TLM:` stream with no v6 replacement
-yet, so the recorders' `TLM:` branch never fires against current
-firmware — pose columns record empty, silently. The `RUN:` cleartext
-*transport* still works (`protocol.cpp` forwards it), but the numeric
-`RUN:<n>` vocabulary has no handlers anywhere: `main.ts` dispatches RUN
-by exact name, `test/test.ts` registers only named handlers, and
-`testrig.ts`'s two-arg handler stores the argument, not the name — so
-every numeric command from `otos_bench.py`, `rotation_check.py`,
-`truth_check.py`, `pivot_truth.py`, `turn_sweep.py`, and
-`otos_levercal.py` is a silent no-op. Only named-verb `RUN:` commands
-and `emitLine()`-based result lines still work. Telemetry restored by
-the planned telemetry-frame work (sprint 004), not yet built; the
-numeric-vocabulary breakage is separate and unplanned (see
-docs/code-review/2026-08-23/, PY-01/BLK-04).
+~~These tools speak the old cleartext vocabulary (`RUN:` commands in;
+`TLM:`/`DIAG`/`OCAL:`-style lines back), and the numeric `RUN:<n>`
+vocabulary has no handlers anywhere on current firmware.~~ Both halves
+are fixed as of sprint 005: telemetry now flows through `tlm.py`'s
+`thdr`/`t` parser (see above), and every tool that used to send a
+numeric `RUN:<n>` offset now sends a real named verb (`test.ts` gained
+two new ones, `pivot` and `turnrate`, for exactly this purpose) or, for
+`otos_bench.py`/`testrig.ts`, has its dispatch bug fixed rather than
+its vocabulary ported. See `clasi/sprints/005-retrofit-bench-tooling-
+onto-the-v6-telemetry-stream/sprint.md`'s Architecture section for the
+full design rationale, including why `testrig.ts`'s vocabulary was
+restored rather than renamed.
```
