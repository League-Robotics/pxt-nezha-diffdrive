---
source_file: host-DESIGN.md
source_hash: 02c9c88276200206e4fe8891f9c93784bb493481fb20f4e837a18f83541d0529
---
# Diff: host-DESIGN.md

Comparison of the sprint overlay copy of `host-DESIGN.md` against its pristine (seed-commit) canonical version.

```diff
--- host-DESIGN.md (pristine)
+++ host-DESIGN.md (current)
@@ -1,6 +1,10 @@
 # tests/host — native host test harness
 
-**Owner:** Eric Busboom · **Last reviewed:** 2026-08-23 · **Status:** stable
+**Owner:** Eric Busboom · **Last reviewed:** 2026-08-24 · **Status:** stable
+(as of sprint 008: boundary-value timeout coverage for all six motion
+verbs, `kVersion`/`RUN_EVENT_SOURCE` drift tests, the `WaHandle`
+wedge/`setWheelsTimed`/config-rounding re-sync plus its own drift test,
+a new settle-loop shim, and `TLM AUTO`/`BUFFER` pinning tests)
 
 ---
 
@@ -41,6 +45,23 @@ Three kinds of file, one pattern:
   supplies its own test-double definitions of the `shims.cpp` free
   functions `wire_adapter.cpp` forward-declares, mirroring the
   production math field-for-field with counts-per-mm fixed at 1.0.
+  **Sprint 008**: `WaHandle`'s DIAG double is re-synced to read
+  `wedgeSuspectLeft/Right` (matching production's `diagValue()`, not
+  the double's previous, different `wedgeLeft/Right` substitution —
+  both field pairs exist on the kernel's `Output` struct and mean
+  different things), its `setWheelsTimed` double now routes through the
+  same `cancelMove()`-triggering path production's does instead of
+  calling `kernel.drive()` directly, and its config-rounding double
+  matches `std::lround(v * 1000.0)` instead of a truncating
+  `static_cast<int>(v * 1000.0f)` — see `src/DESIGN.md`'s own §14 for
+  why each was wrong and what production actually does.
+  `motion_engine_shim.cpp` (or `kernel_shim.cpp`, whichever the
+  extraction ticket judges the better home — the settle helper needs
+  only `kernel.step()`/`kernel.output()`, already exposed by
+  `kernel_shim.cpp`'s existing `Handle`) gains the new settle-loop
+  helper's own handle-plus-free-functions surface, reusing
+  `FakeSleeper::onSleep` (`fake_ports.h`) where a test needs to observe
+  how many `sleepMillis()` calls the helper's iterations produced.
 - **Tests** (`test_*.py`) — each builds its shared library through
   `compile_shared_lib()` (defined in `test_kernel_harness.py`,
   reused by every later suite: same compiler invocation, no CMake)
@@ -125,12 +146,44 @@ taper (`test_regression_*.py`); the v6 grammar mechanics, golden
 vectors, and malformed-input behavior (`test_wire_grammar.py`); the
 reliability layer (`test_wire_reliability.py`); and all six motion
 verbs end-to-end through the real `WireAdapter`
-(`test_wire_motion_verbs.py`).
+(`test_wire_motion_verbs.py`). **Sprint 008** adds: boundary-value
+timeout/duration coverage (`0`, `2^31−1`, `2^31`, uint32-max) across
+all six motion verbs; a `kVersion`/`pxt.json` drift test and an
+`emitLine`/transport line-cap test; a `RUN_EVENT_SOURCE` cross-language
+drift test; a `WaHandle` drift test for the three re-synced doubles
+(wedge fields, `setWheelsTimed`/`cancelMove()`, config rounding),
+demonstrated to fail when only one side changes; the extracted
+settle-loop helper's bounded-iteration/break-on-rest behavior, exercised
+directly through its own new shim (not merely argued for by
+`test_regression_post_move_neutral.py`, which stays as the "why this
+matters" test); and `TLM AUTO`/`BUFFER` `thdr`/`err` pinning.
 
 Not covered, by design (CODAL-bound): `nezha_port`, `otos_port`, the
-transports, `protocol.cpp`'s fiber loop and RUN bridge, `shims.cpp`'s
-real Rig composition/odometry/watchdog, and `tickDrive()`'s post-move
-settle loop — hardware sessions are their only test.
+transports, `protocol.cpp`'s fiber loop and RUN bridge, and
+`shims.cpp`'s real Rig composition/odometry/watchdog — hardware
+sessions are their only test. **Narrower than before sprint 008**:
+`tickDrive()`'s post-move settle loop is no longer entirely
+hardware-only — its bounded-iteration/break-on-rest *decision* is now a
+`MotionEngine` method, host-tested directly; what remains hardware-only
+is `odomUpdate(r)`'s actual encoder-driven pose fold and the loop's
+real `kernel.step()` calls against physical motors, which stay in
+`shims.cpp` unmoved (see `src/DESIGN.md` §9/§14 for the exact boundary
+this extraction drew).
+
+**Target-viability reminder (sprint 008).** Every test in this
+directory, including everything this sprint adds, still only proves
+`-std=c++20` compilation for the four portable translation units (plus
+the `-std=c++11 -fsyntax-only` gate's narrower syntax check over the
+same four files and their extracted-header siblings — none added by
+this sprint, since the settle helper landed on an already-covered
+file). None of it is evidence that `protocol.cpp`, `radio_transport.h`,
+or `shims.cpp`'s changed call site actually link for either real
+target — that is what this sprint's own mandatory build-checkpoint
+ticket proves instead (see `src/DESIGN.md` §11/§14 and
+`docs/design/design.md`'s matching convention). This directory's own
+tests and a real target build are complementary, not substitutes for
+each other, and this sprint is the one that made that relationship a
+named, standing practice rather than an implicit assumption.
 
 Known nit: this directory's `README.md` "What this does NOT cover
 yet" section predates sprint 003's later tickets — the wire and
```
