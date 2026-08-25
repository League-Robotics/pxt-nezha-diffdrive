---
source_file: test-root-DESIGN.md
source_hash: f38150bded6c281aa287567d8994fca9795c3dfd26db5c1404e1cb922383f260
---
# Diff: test-root-DESIGN.md

Documents `test.ts`'s two new named RUN verbs (relative pivot,
turn-rate), `testrig.ts`'s dispatch-bug fix, and adds an explicit note
that the two on-robot programs are mutually exclusive and never
compiled into the same flashable hex — a risk this sprint's own
architecture review flagged for the implementing ticket.

```diff
--- test-root-DESIGN.md (pristine)
+++ test-root-DESIGN.md (current)
@@ -1,6 +1,6 @@
 # test — PXT testFiles (on-robot programs)
 
-**Owner:** Eric Busboom · **Last reviewed:** 2026-08-23 · **Status:** stable
+**Owner:** Eric Busboom · **Last reviewed:** 2026-08-24 · **Status:** stable (sprint 005: `test.ts` gained two named RUN verbs, `testrig.ts`'s dispatch bug is fixed — see below)
 
 MakeCode/PXT `testFiles` (declared in `pxt.json`): TypeScript programs
 compiled into a **deploy** build only — `tools/make_deploy.py`
@@ -8,20 +8,35 @@
 stay `testFiles` so they never run inside a student project that
 installs the extension. They are smoke/bench programs driven by
 buttons and `RUN:` wire commands, not assertion suites — the
-assertion-style coverage lives in `tests/host/`.
+assertion-style coverage lives in `tests/host/`. `test.ts` and
+`testrig.ts` are two independent, mutually exclusive on-robot programs
+(playfield robot vs. the zeguz drum rig), each with its own top-level
+`basic.forever` loop and button handlers — they are never compiled into
+the same flashable hex; `make_deploy.py` promotes only `test.ts` into
+`files`, `testrig.ts` is built/type-checked on its own terms.
 
 - **`test.ts`** — the playfield test programs: three square tours
   (robot-relative encoder+IMU, OTOS-guided `goToWorld`, open-loop
   wheels), each an explicit `startMove` + `driveTick()` loop so the
   tick model stays visible test code; plus named `RUN:` commands for
-  lever-arm calibration (`cal`), fixes, seeding, and probes. Carries
-  vevov's measured lever arm and the playfield's dot coordinates.
+  lever-arm calibration (`cal`), fixes, seeding, probes, **and, as of
+  sprint 005, a relative pivot verb and a turn-rate verb** — added so
+  `pivot_truth.py`, `truth_check.py`, `rotation_check.py`, and
+  `turn_sweep.py` have a real named target instead of the dead numeric
+  `RUN:2/4/5/10`/`RUN:57000+rate`/`RUN:58360+deg` offsets they used to
+  send against a named-verb-only dispatch (see `tools/DESIGN.md`).
+  Carries vevov's measured lever arm and the playfield's dot
+  coordinates.
 - **`testrig.ts`** — the zeguz OTOS validation rig: drum on M1 under
   the sensor, sensor on a servo, a numeric `RUN:<n>` vocabulary
   (probe/zero/stream/calibrate/servo/drum/lever-arm), driven by
   `tools/otos_bench.py`. One worker fiber does **all** I2C —
   kernel ticks and OTOS reads sequentially — per the shared-bus
-  discipline in [`src/DESIGN.md`](../src/DESIGN.md) §7.
+  discipline in [`src/DESIGN.md`](../src/DESIGN.md) §7. **Sprint 005**
+  fixed its `onRunCommand` dispatch: it was storing the handler's
+  always-zero `arg` parameter instead of parsing the verb `name`, so
+  every numeric command silently reached no branch — a one-line
+  storage-bug fix, the vocabulary itself unchanged.
 
 Deliberately thin: these files are working bench instruments; their
 design decisions (tick loops, I2C single-fiber rule, RUN vocabulary)
```
