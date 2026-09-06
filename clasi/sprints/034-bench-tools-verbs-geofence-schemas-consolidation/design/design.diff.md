---
source_file: design.md
source_hash: 39dd1eb8c8b45a0fae53e8762654c7b55e0209b6ba40514c8baf0017a2b399ad
---
# Diff: design.md

Comparison of the sprint overlay copy of `design.md` against its pristine (seed-commit) canonical version.

```diff
--- design.md (pristine)
+++ design.md (current)
@@ -7,7 +7,15 @@
 ---
 # DiffDrive — System Design
 
-**Owner:** Eric Busboom · **Last reviewed:** 2026-08-26 · **Status:** in-flux (as-built through sprint 016 — sprints 004-016 all closed and merged: radio speaks full v6 with a `thdr`/`t` telemetry frame and a resolved motion-completion channel; motion correctness (goTo geometry, cross-fiber stop delivery, continuous-mode odometry, OTOS heading wrap, encoder-reset rebaseline, encoder `PoseSource` fallback for GO_TO_W); student API (stall-latch clear and readback, the `driveTick()` contract, the wire `cruise == 0` sentinel, simulator parity, a `rotationalSlip` setter); wire/radio hardening (raised payload cap, reject-not-clamp over-length RX) with a standing per-sprint build-checkpoint convention; `src/` regrouped into five dependency-layer subdirectories. See `src/DESIGN.md` for current section-by-section detail.)
+**Owner:** Eric Busboom · **Last reviewed:** 2026-09-06 · **Status:**
+in-flux, and the two halves are at different depths. The `tools/` and
+`tests/` entries in the subsystem map below were re-verified against
+the tree on 2026-09-06 and describe it as sprint 034 leaves it. The
+`src/` entry is as-built through sprint 016 **at this document's level
+of detail** and has NOT been re-verified since; `src/DESIGN.md` carries
+the current section-by-section detail and is the authority for the
+extension itself. The global-conventions sections below are content,
+not a change log, and are maintained in place.
 
 ## What the system is
 
@@ -33,12 +41,27 @@
   dependency layer (sprint 013), but that grouping is coarse, so that
   one doc still carries the logical subsystem breakdown as sections.
 - [`tools/DESIGN.md`](../../tools/DESIGN.md) — host-side Python bench
-  and diagnostic tooling: robot/camera links, deploy builds, tour
-  runners/recorders/charts, ground-truth and calibration scripts.
+  and diagnostic tooling: the sequenced-wire link layer and its four
+  carriers, the overhead camera, playfield geometry and the geofence,
+  telemetry parsing and the pose-CSV schema, tour runners/recorders/
+  charts, ground-truth and calibration probes, deploy builds, and the
+  publishing tools. It opens with a complete inventory — every file,
+  one line — held complete by
+  `tests/tools/test_tools_design_inventory.py`. Two self-contained
+  subdirectories carry their own docs:
+  [`tools/rogo/DESIGN.md`](../../tools/rogo/DESIGN.md) (a stdlib-only,
+  pipx-installable netcat for the WiFi carrier, and a deliberate
+  duplicate of the link layer) and
+  [`tools/linefollow/DESIGN.md`](../../tools/linefollow/DESIGN.md).
 - [`tests/DESIGN.md`](../../tests/DESIGN.md) — the Python-run test
-  root; its one subsystem is
-  [`tests/host/DESIGN.md`](../../tests/host/DESIGN.md), the native
-  host harness (firmware C++ under pytest via ctypes).
+  root: which suites `uv run pytest` collects, and which translation
+  units nothing on the host compiles. Its subsystems are
+  [`tests/host/DESIGN.md`](../../tests/host/DESIGN.md) (the native
+  host harness — firmware C++ under pytest via ctypes),
+  [`tests/tools/DESIGN.md`](../../tests/tools/DESIGN.md) (unit tests
+  and source-level guards over this repo's own Python) and
+  [`tests/calibration/DESIGN.md`](../../tests/calibration/DESIGN.md)
+  (the on-robot calibration programs, which pytest does not collect).
 - [`test/DESIGN.md`](../../test/DESIGN.md) — PXT `testFiles`: on-robot
   test programs (playfield tours, the zeguz OTOS rig). Deliberately
   thin.
@@ -259,8 +282,9 @@
 ### Subsystem-doc contract: content, not sprint history
 
 Each canonical subsystem doc (`src/DESIGN.md` and its five thin
-per-directory siblings, `tools/DESIGN.md`, `tests/DESIGN.md`/
-`tests/host/DESIGN.md`/`tests/tools/DESIGN.md`, `test/DESIGN.md`)
+per-directory siblings, `tools/DESIGN.md` and its two subdirectory
+docs, `tests/DESIGN.md` and its five subdirectory docs,
+`test/DESIGN.md`)
 describes the system **as it stands** — its numbered/lettered sections
 are content, not a changelog. None of them narrates what a specific
 sprint changed; that belongs to the sprint's own record
```
