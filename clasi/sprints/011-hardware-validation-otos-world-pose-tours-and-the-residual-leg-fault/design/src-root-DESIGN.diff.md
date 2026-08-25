---
source_file: src-root-DESIGN.md
source_hash: 19498b379d62233b17924c37ce6598928ee172f75342d4cbcc1f2e39a0343d03
---
# Diff: src-root-DESIGN.md

Documents sprint 011's kernel-side investigation: an inline annotation on
§3 (Motion engine) naming `move_.deadline`'s duration math as the
residual-leg-fault issue's next-probe, and a new §15 recording the
sprint's Sprint Changes, Design Rationale, and Open Questions for both
the `motion_engine.cpp` investigation and the `shims.cpp`
first-move-after-boot review. **Revision (ticket 003):** the
`motion_engine.cpp` half is now resolved — ticket 003 traced the
caller-supplied `timeout` to its real source (`shims.cpp::startMove()`'s
dual-rate-duration-plus-1500ms backstop) and drove the real engine
through realistic ~24 ms-tick physics for the three leg shapes
`test.ts`'s tours issue (pure pivot, pure straight, and the blended
split leg where one deadline spans two sequential ramp/taper phases).
Finding: CLEAN, with hundreds of ms of unused margin in every case
tested (worst case ~600 ms consumed of the flat 1500 ms backstop). No
source change landed; §3 and §15 below are updated in place to record
the finding, and `intermittent-cw-pivot-abort-wheel-reversal.md` carries
the same finding as a ruled-out theory. The `shims.cpp` half (ticket
004) remains a separate, still-pending investigation — see §15. No
diagram — the investigation adds no new caller/callee edge between
modules.

```diff
--- src-root-DESIGN.md (pristine)
+++ src-root-DESIGN.md (current)
@@ -181,18 +181,46 @@
   already scales twist by the same factor; an independent yaw taper
   double-counts (measured: legs pinned at the 25% floor, 2026-08-22).
 
-**Sprint 011 (planned):** the residual intermittent-leg-fault hunt
-(`intermittent-cw-pivot-abort-wheel-reversal.md`) names `move_.deadline`'s
-duration math (`nowMs() + timeoutMs` at both `moveX()`/`goToR()` call
-sites; expiry checked as `static_cast<int32_t>(now - move_.deadline) >=
-0` in `serviceMove()`) as an unresolved next-probe for legs that
-truncate mid-drive. This file is host-testable in isolation, so the
-investigation is a host test at the deadline-expiry boundary, not a
-bench measurement — see §15 for the campaign framing and `sprint.md`'s
-Use Cases SUC-003. Outcome not yet known at planning time: a clean
-boundary gets recorded as a ruled-out theory in the issue file; a real
-defect gets fixed here with a pinning host test, and this section gets a
-follow-up edit at that point.
+**Sprint 011 (ticket 003, resolved — clean boundary):** the residual
+intermittent-leg-fault hunt (`intermittent-cw-pivot-abort-wheel-reversal.md`)
+named `move_.deadline`'s duration math (`nowMs() + timeoutMs` at both
+`moveX()`/`goToR()` call sites; expiry checked as
+`static_cast<int32_t>(now - move_.deadline) >= 0` in `serviceMove()`) as
+an unresolved next-probe for legs that truncate mid-drive. This file is
+host-testable in isolation, so the investigation was a host test at the
+deadline-expiry boundary, not a bench measurement — see §15 for the
+campaign framing and `sprint.md`'s Use Cases SUC-003.
+
+Ticket 003 traced the caller-supplied `timeout` all the way to its real
+source — `src/shims.cpp::startMove()`'s own dual-rate dead-reckoned
+duration (`max(distance/speed, yaw/yawRate)`) plus a flat `+1500 ms`
+backstop, the actual function `test.ts`'s tours drive through
+(`tickedMove()`/`legToward()` -> `diffDrive.startMove()` -> this shim ->
+`moveX()`) — then drove the real, unmodified engine through realistic
+~24 ms-tick physics (`tests/host/test_motion_engine_deadline_boundary.py`)
+for the three leg shapes those tours actually issue: a pure pivot
+(`turnFloor_`/`yawTaper_`), a pure straight (`distFloor_`/`distTaper_`),
+and — the shape most likely to exhaust the flat margin — a blended leg
+whose rotation alone exceeds `kTurnFirstAngleRad`, which reaches
+`moveX()`'s own internal pivot-then-straight split
+(motion_engine.cpp:166) so ONE caller-supplied deadline must cover TWO
+sequential ramp/taper overheads instead of one.
+
+**Finding: CLEAN.** Across every parameter combination tested (300-800 mm
+distance, 50-150 deg rotation, `openLoopProfile()`'s own production
+speed/yaw-rate tuning), the deadline never fired before a genuinely-
+progressing move's own completion. The two-phase split leg's measured
+ramp+taper overhead (~600 ms, dominated by two independent 400 ms
+acceleration ramps) consumed at most ~41% of the flat 1500 ms backstop,
+leaving 890+ ms of unused margin in the worst case observed; the
+single-segment pivot and straight legs left even more (59-74% unused).
+A companion test with the +1500 ms margin deliberately stripped confirms
+the harness genuinely detects truncation when it occurs (the same leg
+IS cut short, well outside its completion margin, at the stripped
+deadline) — the clean result above is not an artifact of a lenient test.
+No source change landed; `test_motion_engine_deadline_boundary.py` is
+kept as a permanent regression guard. Full arithmetic and the ruled-out
+theory are recorded in `intermittent-cw-pivot-abort-wheel-reversal.md`.
 
 ## 4. Wire grammar — `wire_handler.h/.cpp` (`Wire::WireHandler`)
 
@@ -1578,26 +1606,35 @@
 for the sizing decision). Two linked issues touch this file's subsystem:
 `otos-on-vevov-move-goto-world-pose-square-tours.md` (measurement only —
 no code here changes) and
-`intermittent-cw-pivot-abort-wheel-reversal.md` (a kernel timing/boot
-investigation that *may* change this file, outcome not yet known at
-planning time). `brick-reset-bench-measurement.md`, the third linked
-issue, touches no `src/` module this sprint didn't already close in
-sprint 006 — it is a bench-handoff-only concern, tracked entirely in
-`tools/DESIGN.md` (this overlay's sibling, `tools-root-DESIGN.md`) and
-the issue file itself.
-
-**Sprint Changes (planned; see §3's inline annotation above for the
+`intermittent-cw-pivot-abort-wheel-reversal.md`, which bundles two
+independent next-probes against this file's subsystem: `move_.deadline`'s
+duration math (ticket 003, **resolved this sprint — clean boundary, no
+source change**, see below and §3's inline annotation) and
+`shims.cpp`'s first-move-after-boot state (ticket 004, code-review only,
+outcome still pending as of this edit — `shims.cpp` is not
+host-testable, §1's layering table). `brick-reset-bench-measurement.md`,
+the third linked issue, touches no `src/` module this sprint didn't
+already close in sprint 006 — it is a bench-handoff-only concern,
+tracked entirely in `tools/DESIGN.md` (this overlay's sibling,
+`tools-root-DESIGN.md`) and the issue file itself.
+
+**Sprint Changes (see §3's inline annotation above for the
 `move_.deadline` detail):**
 
-- `motion_engine.{h,cpp}` — **investigation, conditional fix.** Ticket
-  003 traces `move_.deadline`'s computation and expiry check against a
-  leg that truncates before its commanded distance, and writes a host
-  test at the boundary. If the boundary is clean, no source change
-  lands — the finding is recorded in the issue file only. If a genuine
-  defect is found, it is fixed here with a pinning host test, and this
-  section (plus §3's annotation) gets a follow-up edit reflecting the
-  actual change — not assumed now, since the outcome is genuinely
-  unknown until the ticket executes.
+- `motion_engine.{h,cpp}` — **investigated, no fix landed (clean
+  boundary).** Ticket 003 traced `move_.deadline`'s computation and
+  expiry check all the way to its real caller (`shims.cpp::startMove()`'s
+  dual-rate-duration-plus-1500ms-backstop formula) and drove the real
+  engine through a realistic ~24 ms tick cadence for the three leg
+  shapes `test.ts`'s tours actually issue (pure pivot, pure straight,
+  and the blended-split leg where one deadline spans two sequential
+  ramp/taper phases). Every scenario tested completed with hundreds of
+  ms of unused margin out of the flat 1500 ms backstop (worst case: the
+  two-phase split leg, ~600 ms measured overhead against the 1500 ms
+  budget). The boundary is CLEAN — no source change landed. The new
+  host test (`tests/host/test_motion_engine_deadline_boundary.py`) is
+  kept as a permanent regression guard, and the finding is recorded in
+  `intermittent-cw-pivot-abort-wheel-reversal.md` as a ruled-out theory.
 - `shims.cpp` — **investigation only, no source change planned.**
   Ticket 004 reviews boot-time state (encoder baseline, pose seed, any
   cached filter/velocity state) ahead of the very first
@@ -1626,11 +1663,14 @@
 MotionEngine → Kernel/ports), and no new edge is added regardless of
 which investigation outcome lands.
 
-**Migration concerns.** None. If ticket 003 lands a fix, it is a kernel
-timing correction with its own host-test coverage — no wire-format,
-data-model, or student-facing API change either way, since
-`move_.deadline` is purely internal to `MotionEngine`'s move-servicing
-loop and never exposed across the wire or block API.
+**Migration concerns.** None. Ticket 003's investigation found the
+deadline boundary clean, so no fix landed and there is nothing to
+migrate. Had a genuine defect been found, the fix would have been a
+purely internal kernel-timing correction with its own host-test
+coverage — no wire-format, data-model, or student-facing API change
+either way, since `move_.deadline` is purely internal to
+`MotionEngine`'s move-servicing loop and never exposed across the wire
+or block API.
 
 **Risk.** The `shims.cpp` half of this investigation (first-move-after-
 boot) is, like every `shims.cpp` change or review, invisible to the
@@ -1669,11 +1709,13 @@
 
 **Open Questions (sprint 011):**
 
-- Whether ticket 003's investigation finds a real `moveDeadline` defect
-  or a clean boundary is unknown until executed. Both outcomes are
-  planned for (see Sprint Changes above); neither blocks ticket
-  sequencing, since ticket 006 (the residual-fault campaign procedure)
-  only needs the *finding*, not a specific outcome.
+- **Resolved (ticket 003):** the `moveDeadline` boundary is clean — see
+  Sprint Changes above for the measured margin across all three leg
+  shapes tested. Ticket 006 (the residual-fault campaign procedure) can
+  proceed with `move_.deadline` ruled out as a cause of the residual
+  leg-truncation fault; the campaign's remaining candidate is whatever
+  ticket 004's first-move-after-boot review surfaces (see the next
+  bullet).
 - Whether ticket 004's first-move-after-boot review surfaces a concrete
   enough mechanism to warrant its own follow-up ticket, inside or outside
   this sprint, cannot be answered at planning time — flagged for the
```
