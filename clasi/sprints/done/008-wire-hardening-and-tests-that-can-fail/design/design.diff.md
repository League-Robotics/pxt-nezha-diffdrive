---
source_file: design.md
source_hash: 606e2ea136a8770f7eae6cda91dfe7ba85c6254e2ec1ffba96408cb09117019b
---
# Diff: design.md

Comparison of the sprint overlay copy of `design.md` against its pristine (seed-commit) canonical version.

```diff
--- design.md (pristine)
+++ design.md (current)
@@ -7,7 +7,7 @@
 ---
 # DiffDrive — System Design
 
-**Owner:** Eric Busboom · **Last reviewed:** 2026-08-23 · **Status:** in-flux (sprint 004 as-built, currently in review, not yet merged; sprint 005 roadmapped, not yet detail-planned)
+**Owner:** Eric Busboom · **Last reviewed:** 2026-08-23 · **Status:** in-flux (as-built through sprint 008, closed and merged — sprints 004, 006, 007 and 008 all closed and merged: radio speaks full v6 with a `thdr`/`t` telemetry frame; motion correctness (goTo geometry, cross-fiber stop delivery, continuous-mode odometry, OTOS heading wrap, encoder-reset rebaseline, encoder `PoseSource` fallback for GO_TO_W); student API (stall-latch clear and readback, the `driveTick()` contract, the wire `cruise == 0` sentinel, simulator parity, a `rotationalSlip` setter); and wire hardening with a standing per-sprint build-checkpoint convention. Sprint 005 roadmapped, not yet detail-planned, blocked on a hardware bench checkpoint)
 
 ## What the system is
 
@@ -156,6 +156,30 @@
 the narrow syntax gate sprint 004 added to catch that class of defect,
 and what that gate does not cover.
 
+**Standing convention (sprint 008).** The `-std=c++11` syntax gate
+closes one defect class (language-standard mismatches in the four
+portable translation units and their extracted-header siblings) but
+provably not the others: a `uint8_t`-truncated buffer size the real
+compiler's `-Woverflow` catches and the gate's plain `-fsyntax-only`
+does not (sprint 004 ticket 005), and a `pxt.json` manifest omission
+that blocks every hex while the gate — which never reads `pxt.json` —
+stays green (sprint 006, found by sprint 007 ticket 001). Both were
+found only because a ticket happened to run a real build. Rather than
+attempt a hard, automated gate on this — the two documented benign
+build-abort shapes (the legacy V1 `bbc-microbit-classic-gcc` hex-merge
+failure, and the nondeterministic packaging abort surfaced as
+`TS9283`/`TS9043`/`TS9200`, always retriable) make a naive pass/fail
+gate unreliable, and `close_sprint` itself is CLASI-server code this
+project's own tickets cannot change — every sprint that touches
+build-eligible source now includes a **mandatory, always-last
+build-checkpoint ticket** that runs `tools/make_deploy.py` (triage-aware
+as of sprint 008: it distinguishes a real `.cpp` compile failure from
+the two benign abort shapes and retries the latter once automatically)
+and confirms a flashable hex results from the sprint's own final state.
+Sprint 004 ticket 005 and sprint 007 ticket 008 already did this
+informally; sprint 008 is where it became a named, standing practice —
+see `src/DESIGN.md` §11/§14 for the full detail and the tooling change.
+
 ### Provenance
 
 `diffdrive.h/.cpp` is a vendored, byte-stable copy of the
```
