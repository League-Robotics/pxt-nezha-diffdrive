---
source_file: design.md
source_hash: 5b9e559c509fd93f57c71a1e3fa972c503fe04b25c21e927c9547550a21b1d4f
---
# Diff: design.md

Updates the top-level status line to reflect sprint 005 as closed and
merged (bench tooling retrofitted onto the v6 telemetry stream), and
rewrites the "Protocol versioning" section's stale note that the
`tools/` bench suite had "not yet" been retrofitted onto the `thdr`/`t`
frame — it has, as of this sprint.

```diff
--- design.md (pristine)
+++ design.md (current)
@@ -7,7 +7,7 @@
 ---
 # DiffDrive — System Design
 
-**Owner:** Eric Busboom · **Last reviewed:** 2026-08-23 · **Status:** in-flux (as-built through sprint 008, closed and merged — sprints 004, 006, 007 and 008 all closed and merged: radio speaks full v6 with a `thdr`/`t` telemetry frame; motion correctness (goTo geometry, cross-fiber stop delivery, continuous-mode odometry, OTOS heading wrap, encoder-reset rebaseline, encoder `PoseSource` fallback for GO_TO_W); student API (stall-latch clear and readback, the `driveTick()` contract, the wire `cruise == 0` sentinel, simulator parity, a `rotationalSlip` setter); and wire hardening with a standing per-sprint build-checkpoint convention. Sprint 005 roadmapped, not yet detail-planned, blocked on a hardware bench checkpoint)
+**Owner:** Eric Busboom · **Last reviewed:** 2026-08-24 · **Status:** in-flux (as-built through sprint 005, closed and merged — sprints 004, 006, 007, 008 and 005 all closed and merged: radio speaks full v6 with a `thdr`/`t` telemetry frame; motion correctness (goTo geometry, cross-fiber stop delivery, continuous-mode odometry, OTOS heading wrap, encoder-reset rebaseline, encoder `PoseSource` fallback for GO_TO_W); student API (stall-latch clear and readback, the `driveTick()` contract, the wire `cruise == 0` sentinel, simulator parity, a `rotationalSlip` setter); wire hardening with a standing per-sprint build-checkpoint convention; and, sprint 005, the bench tool suite retrofitted onto the v6 telemetry frame — a shared `tools/tlm.py` parser with fail-loud guards, `tools/camproc.py`/`tools/field.py` consolidating camera/link-layer duplication, a real `WireAdapter` motion-completion signal, and the `testFiles` build-hygiene plus dead-numeric-RUN-vocabulary fixes)
 
 ## What the system is
 
@@ -122,9 +122,10 @@
 (`clasi/issues/radio-rx-capacity-fragmentation.md`). v6 now **does**
 carry a data-bearing telemetry frame — `thdr`/`t`, built in sprint 004
 — replacing the old cleartext `TLM:` stream the same way the rest of
-v5 was replaced, though the bench tooling in `tools/` that used to
-parse `TLM:` has not yet been retrofit onto the new frame (sprint
-005).
+v5 was replaced. The bench tooling in `tools/` that used to parse
+`TLM:` is retrofitted onto the new frame as of sprint 005, through one
+shared parser (`tools/tlm.py`) rather than six scattered ones — see
+`tools/DESIGN.md`.
 
 ### Execution model (tick model, sprint 002)
 
```
