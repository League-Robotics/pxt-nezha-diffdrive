---
source_file: src-root-DESIGN.md
source_hash: c2c7a71088a52a96c6fead41202249e39182da8b185a6e1681ea54f7cebab487
---
# Diff: src-root-DESIGN.md

Documents sprint 011's kernel-side investigation: an inline annotation on
§3 (Motion engine) naming `move_.deadline`'s duration math as the
residual-leg-fault issue's unresolved next-probe, and a new §15
recording the sprint's planned Sprint Changes, Design Rationale, and Open
Questions for both the `motion_engine.cpp` investigation (host-testable,
may land a conditional fix) and the `shims.cpp` first-move-after-boot
review (code-review only, no source change planned). No diagram — the
investigation adds no new caller/callee edge between modules.

```diff
--- src-root-DESIGN.md (pristine)
+++ src-root-DESIGN.md (current)
@@ -1,6 +1,6 @@
 # src — the DiffDrive extension
 
-**Owner:** Eric Busboom · **Last reviewed:** 2026-08-24 · **Status:** in-flux (as-built through sprint 008, closed and merged — wire hardening and tests that can fail: timeout reject/clamp unified across all six motion verbs, `kVersion`/line-cap/`RUN_EVENT_SOURCE`/`kDiag*` single-sourced or drift-tested, the `WaHandle` test doubles re-synced to production, the post-move settle loop extracted into a host-testable `MotionEngine` helper, `TLM AUTO`/`BUFFER` given defined semantics, and a triage-aware `make_deploy.py` plus a standing per-sprint build-checkpoint-ticket convention closing the target-viability gap; sprint 005 roadmapped, not yet detail-planned, blocked on a hardware bench checkpoint)
+**Owner:** Eric Busboom · **Last reviewed:** 2026-08-24 · **Status:** in-flux (as-built through sprint 008, closed and merged — wire hardening and tests that can fail: timeout reject/clamp unified across all six motion verbs, `kVersion`/line-cap/`RUN_EVENT_SOURCE`/`kDiag*` single-sourced or drift-tested, the `WaHandle` test doubles re-synced to production, the post-move settle loop extracted into a host-testable `MotionEngine` helper, `TLM AUTO`/`BUFFER` given defined semantics, and a triage-aware `make_deploy.py` plus a standing per-sprint build-checkpoint-ticket convention closing the target-viability gap; sprint 011 (planned, not yet executed) characterizes `MotionEngine`'s `move_.deadline` duration math and `shims.cpp`'s first-move-after-boot state against the residual intermittent-leg-fault hunt — see §15 — landing a host-tested fix only if the investigation finds a real defect; sprint 005 executing concurrently, retrofitting bench tooling onto the v6 telemetry frame)
 
 `src/` is flat — no subdirectories — so this one document carries the
 logical subsystem breakdown as sections. Global conventions (units
@@ -180,6 +180,19 @@
 - Only a **pure turn** tapers on yaw — in an arc the distance taper
   already scales twist by the same factor; an independent yaw taper
   double-counts (measured: legs pinned at the 25% floor, 2026-08-22).
+
+**Sprint 011 (planned):** the residual intermittent-leg-fault hunt
+(`intermittent-cw-pivot-abort-wheel-reversal.md`) names `move_.deadline`'s
+duration math (`nowMs() + timeoutMs` at both `moveX()`/`goToR()` call
+sites; expiry checked as `static_cast<int32_t>(now - move_.deadline) >=
+0` in `serviceMove()`) as an unresolved next-probe for legs that
+truncate mid-drive. This file is host-testable in isolation, so the
+investigation is a host test at the deadline-expiry boundary, not a
+bench measurement — see §15 for the campaign framing and `sprint.md`'s
+Use Cases SUC-003. Outcome not yet known at planning time: a clean
+boundary gets recorded as a ruled-out theory in the issue file; a real
+defect gets fixed here with a pinning host test, and this section gets a
+follow-up edit at that point.
 
 ## 4. Wire grammar — `wire_handler.h/.cpp` (`Wire::WireHandler`)
 
@@ -1558,3 +1571,110 @@
   is a real design choice (see `src/DESIGN.md` §1's deliberate
   `shims.cpp`-has-no-header convention) better made deliberately in its
   own review than folded into a Minor here.
+
+## 15. Sprint 011 — architecture diagram and change summary
+
+Substantial-tier sprint update (see `sprint.md`'s Architecture section
+for the sizing decision). Two linked issues touch this file's subsystem:
+`otos-on-vevov-move-goto-world-pose-square-tours.md` (measurement only —
+no code here changes) and
+`intermittent-cw-pivot-abort-wheel-reversal.md` (a kernel timing/boot
+investigation that *may* change this file, outcome not yet known at
+planning time). `brick-reset-bench-measurement.md`, the third linked
+issue, touches no `src/` module this sprint didn't already close in
+sprint 006 — it is a bench-handoff-only concern, tracked entirely in
+`tools/DESIGN.md` (this overlay's sibling, `tools-root-DESIGN.md`) and
+the issue file itself.
+
+**Sprint Changes (planned; see §3's inline annotation above for the
+`move_.deadline` detail):**
+
+- `motion_engine.{h,cpp}` — **investigation, conditional fix.** Ticket
+  003 traces `move_.deadline`'s computation and expiry check against a
+  leg that truncates before its commanded distance, and writes a host
+  test at the boundary. If the boundary is clean, no source change
+  lands — the finding is recorded in the issue file only. If a genuine
+  defect is found, it is fixed here with a pinning host test, and this
+  section (plus §3's annotation) gets a follow-up edit reflecting the
+  actual change — not assumed now, since the outcome is genuinely
+  unknown until the ticket executes.
+- `shims.cpp` — **investigation only, no source change planned.**
+  Ticket 004 reviews boot-time state (encoder baseline, pose seed, any
+  cached filter/velocity state) ahead of the very first
+  `startMove()`/`serviceMove()` call after power-on, by inspection only
+  — `shims.cpp` includes `pxt.h` and is not host-testable (§1's layering
+  table), so this half of the investigation cannot carry a host test
+  the way ticket 003's can. The finding lands in
+  `intermittent-cw-pivot-abort-wheel-reversal.md`, not in a source
+  change, unless the review surfaces something concrete enough to
+  warrant its own follow-up ticket (not planned as part of this
+  sprint).
+- No other `src/` file is touched. `otos_port.{h,cpp}`'s lever-arm
+  transform (§7) and `main.ts`'s `goToWorld()`/dual-pose seed (§9) are
+  read during this sprint's campaign but not modified — the campaign
+  measures already-shipped behavior, it does not change it.
+
+**Why no diagram.** A component/dependency diagram earns its place when
+a sprint composes modules together in a way that didn't exist before.
+This sprint doesn't: the investigation reads `motion_engine.cpp`'s and
+`shims.cpp`'s existing internals without adding a new caller/callee edge
+between modules, and the conditional fix (if any) stays inside
+`motion_engine.cpp`'s own already-diagrammed position in §14's flowchart
+(`Rig → MotionEngine → DifferentialDrive`) — nothing new to draw. No
+entity-relationship diagram: no data-model change. No separate
+dependency graph: dependency direction is unchanged (Presentation/wire →
+MotionEngine → Kernel/ports), and no new edge is added regardless of
+which investigation outcome lands.
+
+**Migration concerns.** None. If ticket 003 lands a fix, it is a kernel
+timing correction with its own host-test coverage — no wire-format,
+data-model, or student-facing API change either way, since
+`move_.deadline` is purely internal to `MotionEngine`'s move-servicing
+loop and never exposed across the wire or block API.
+
+**Risk.** The `shims.cpp` half of this investigation (first-move-after-
+boot) is, like every `shims.cpp` change or review, invisible to the
+C++11 syntax gate and every host test by construction (§1's layering
+table) — a finding here is a documented hypothesis, not something this
+sprint can mechanically verify short of the bench campaign itself
+(`sprint.md` SUC-006). This is the same risk class §14 already names for
+`shims.cpp` call-site changes generally, not a new one this sprint
+introduces.
+
+**Design Rationale:**
+
+*Decision: `moveDeadline` and first-move-after-boot are two tickets, not
+one.* Alternatives: (a) one combined investigation ticket covering both
+next-probes [rejected], (b) two tickets split by testability profile
+[chosen]. `motion_engine.cpp` is host-testable in isolation; `shims.cpp`
+is not. Combining them would force one ticket's acceptance criteria to
+either overclaim test coverage the `shims.cpp` half cannot honestly
+provide, or underclaim the test coverage the `motion_engine.cpp` half
+genuinely can. Consequence: ticket 003 has host-test acceptance criteria
+and may land a fix; ticket 004 is explicitly scoped as a documented
+finding with "no test to run" stated up front.
+
+*Decision: no source change is committed to in this planning pass for
+either ticket.* Alternatives: (a) pre-decide a fix now and write tickets
+to implement it [rejected], (b) write both tickets as open
+investigations with conditional fix paths [chosen]. A hunt sprint cannot
+honestly promise a root cause before the investigation runs (this
+sprint's own Success Criteria in `sprint.md` says so explicitly for the
+hardware campaign; the same honesty applies to the code-level
+investigation). Consequence: this section states "outcome not yet known"
+rather than describing a fix that may not materialize — matching the
+project's own "tests that can fail" theme (sprint 008) applied to
+architecture documentation: a document that describes work not yet done
+as though it were done is a document that can silently go stale.
+
+**Open Questions (sprint 011):**
+
+- Whether ticket 003's investigation finds a real `moveDeadline` defect
+  or a clean boundary is unknown until executed. Both outcomes are
+  planned for (see Sprint Changes above); neither blocks ticket
+  sequencing, since ticket 006 (the residual-fault campaign procedure)
+  only needs the *finding*, not a specific outcome.
+- Whether ticket 004's first-move-after-boot review surfaces a concrete
+  enough mechanism to warrant its own follow-up ticket, inside or outside
+  this sprint, cannot be answered at planning time — flagged for the
+  team-lead if it happens during execution.
```
