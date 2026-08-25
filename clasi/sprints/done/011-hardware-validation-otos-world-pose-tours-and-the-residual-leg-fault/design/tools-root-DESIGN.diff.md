---
source_file: tools-root-DESIGN.md
source_hash: f00720bafd27cd75f8925f8e77df0fe89fb80b12f0f3612fd517ee9e6b07bea5
---
# Diff: tools-root-DESIGN.md

Documents sprint 011's shipped campaign tooling — the `tour_capture.py`
RUN-vocabulary retarget (ticket 001, done; the one tool sprint 005's own
retargeting work does not cover) and the new `leg_analysis.py` per-leg
believed-vs-target tool (ticket 002, done) — plus the three bench-handoff
campaign procedures (OTOS, residual leg-fault, brick-reset) that turn
that tooling into a repeatable session. Adds a forward-pointing "Sprint
011 update" note under the existing "Known limitation — the telemetry
gap" section rather than rewriting it, since most of that section went
stale from sprint 005's concurrent work, not this sprint's own.
**Revision (ticket 008 re-check):** the header status line and the
`tour_capture.py`/`leg_analysis.py`/"Sprint 011 update" prose, originally
written prospectively ("planned", "will speak named verbs"), are
corrected to past tense now that tickets 001/002 have actually shipped —
no behavioral content changed, only tense/status accuracy.

```diff
--- tools-root-DESIGN.md (pristine)
+++ tools-root-DESIGN.md (current)
@@ -1,6 +1,6 @@
 # tools — bench and diagnostic tooling
 
-**Owner:** Eric Busboom · **Last reviewed:** 2026-08-24 · **Status:** stable (host side of the retired cleartext vocabulary — see the telemetry note below; `make_deploy.py`'s `build()` is now triage-aware, see "Build checkpoint triage" below)
+**Owner:** Eric Busboom · **Last reviewed:** 2026-08-24 · **Status:** stable (host side of the retired cleartext vocabulary — see the telemetry note below, now partially superseded — see "Sprint 011 update" beneath it; `make_deploy.py`'s `build()` is now triage-aware, see "Build checkpoint triage" below; sprint 011 (tickets 001/002 done) added a per-leg believed-vs-target analysis tool (`leg_analysis.py`) and retargeted `tour_capture.py`'s RUN vocabulary onto named verbs — see "Campaign tooling and bench-handoff procedures (sprint 011)" below; ticket 008's build/verification checkpoint in progress)
 
 Host-side Python scripts for building, deploying, driving, measuring,
 and charting the robot. Flat root, no subsystems. Run under `uv`
@@ -125,9 +125,23 @@
   (seed at start, score at end); the robot drives all four legs on its
   own sensors; no radio round-trips inside the tour.
 - **`tour_capture.py`** / **`tour_watch.py`** — telemetry recorders
-  (triggered vs. button-watch); write the pose/wheel CSVs.
+  (triggered vs. button-watch); write the pose/wheel CSVs. **Sprint 011
+  (ticket 001, done):** `tour_capture.py` used to select its tour with a
+  numeric `RUN:<n>` verb (`--run N` → `RUN:{a.run}`) that no handler in
+  current firmware answered — the one tool sprint 005's own retargeting
+  work (ticket 006's six-tool list) did not cover. Retargeted onto
+  `RUN:tour:world`/`RUN:tour:robot`/`RUN:tour:wheels` (`--tour
+  {world,robot,wheels}`), matching `tour_run.py`'s already-current
+  vocabulary.
 - **`tour_chart.py`** / **`practice_chart.py`** — the standard
   matplotlib plots of those CSVs.
+- **`leg_analysis.py`** (sprint 011, ticket 002, done) — turns a `tour_capture.py`
+  recording into a per-leg believed-vs-target table: commanded target,
+  believed pose at move end, AprilCam ground truth where available, and
+  a classification (on-target / straight-overrun / mid-leg-truncation)
+  per leg. A new leaf consumer of `tools/tlm.py`'s `TlmStream`/
+  `pose_cm`/`otos_cm` — the same relationship the six tools above already
+  have, one more instance of it, not a new kind of dependency.
 - **`tour_practice.py`** — repeated camera-scored runs from the start
   dot, repositioning between runs.
 - **`tour_square.py`**, **`tour_closedloop.py`** — earlier variants
@@ -172,3 +186,86 @@
 the planned telemetry-frame work (sprint 004), not yet built; the
 numeric-vocabulary breakage is separate and unplanned (see
 docs/code-review/2026-08-23/, PY-01/BLK-04).
+
+**Sprint 011 update.** By sprint 011's own close, most of this section
+is stale — sprint 004 shipped the v6 telemetry frame, sprint 005 ticket
+001 built `tools/tlm.py` as its host-side parser, sprint 005 ticket 002
+retrofitted the tour/ground-truth consumers onto it, and sprint 005
+ticket 006 retargeted `otos_bench.py`, `pivot_truth.py`,
+`truth_check.py`, `rotation_check.py`, `turn_sweep.py`, and
+`otos_levercal.py` off the dead numeric vocabulary. Sprint 011 does not
+rewrite this section (that rewrite belongs to whichever sprint lands
+last among 005/011, or a future hygiene pass) — it added the one piece
+sprint 005 did not cover: `tour_capture.py`'s numeric tour-selection
+verb, retargeted per the "Tour family" section above (ticket 001, done).
+Read this section as describing the **pre-005** state; every tool in
+this file except `testrig.ts`'s console (`otos_bench.py`, out of scope
+here) now speaks named verbs.
+
+## Campaign tooling and bench-handoff procedures (sprint 011)
+
+**Sizing:** substantial (see `sprint.md`'s Architecture section). Full
+write-up below per the 7-step methodology; no diagram (see "Why no
+diagram").
+
+**Step 1 — the problem.** Two of this sprint's three linked issues need
+a real hardware campaign before either can be called resolved: OTOS
+world-pose accuracy against the encoder-only baseline, and the residual
+intermittent distance-leg fault surviving sprint 006's fixes. Neither
+campaign can run, or be scored once run, without tooling and a written
+procedure — and per this sprint's own hard constraint, no ticket's
+acceptance criteria may require a robot, so the tooling and the
+procedure are this sprint's actual deliverables; the robot sessions
+themselves are bench-handoff checklists that don't gate the sprint's
+close.
+
+**Step 2 — responsibilities.** (1) Speak the RUN vocabulary current
+firmware answers (`tour_capture.py` retarget, above). (2) Turn a
+recording into per-leg evidence (`leg_analysis.py`, above). (3) Turn the
+tooling into a repeatable bench session (three written procedures,
+below) — these don't belong in a `.py` file; each lives as a section
+added to its own linked issue file, where a bench operator will actually
+look for it.
+
+**Step 3 — modules (procedures).**
+- **OTOS campaign procedure** (added to
+  `otos-on-vevov-move-goto-world-pose-square-tours.md`). Purpose: make
+  the issue's own Verification section executable. Boundary: sequences
+  `RUN:cal:1` (re-confirm, not re-derive, the lever arm) then repeated
+  `RUN:tour:world`/`RUN:tour:robot` captures via the retargeted
+  `tour_capture.py`, scored by `leg_analysis.py` and `tour_chart.py`
+  against the issue's bar and the recorded 9-54 mm/1-7° baseline. Serves
+  SUC-005.
+- **Residual-fault campaign procedure** (added to
+  `intermittent-cw-pivot-abort-wheel-reversal.md`). Purpose: make the
+  issue's own "next probes" executable as one campaign. Boundary:
+  repetition count for a real failure rate (not one pass/fail), per-leg
+  logging via `leg_analysis.py`, the RETIRED THEORIES do-not-retest list
+  restated inline so a bench operator can't accidentally re-open one,
+  explicit confirmed/ruled-out criteria, and instructions for filing a
+  sharpened successor issue if the fault survives. Serves SUC-006.
+- **Brick-reset bench handoff** (folded into
+  `brick-reset-bench-measurement.md`, which already carries a pointer to
+  the sprint 006 checklist). Purpose: fold the already-written four
+  questions into this sprint's combined bench session, since all three
+  procedures run on the same robot in the same physical sitting. Serves
+  SUC-007.
+
+**Why no diagram.** These three procedures are documentation, not code —
+they don't compose modules together, they sequence commands the tour
+family (above) and `leg_analysis.py` already expose. A diagram would
+show the same box (`tour_capture.py`/`leg_analysis.py`) three times with
+different labels.
+
+**Migration concerns.** None — no tool changes shape, only which verb it
+sends and what new tool consumes its output.
+
+**Design Rationale:** covered in `sprint.md`'s own Architecture section
+(the "no robot required" and "otos_levercal.py not re-ticketed" decisions
+apply directly to this section's scope) and restated in
+`src-root-DESIGN.md` §15 for the kernel-side half of the investigation.
+
+**Open Questions:** whether vevov will be available for the combined
+bench session before sprint 012 starts is outside this sprint's control
+— the sprint closes on the artifacts above regardless; the three linked
+issues stay open until the session actually runs.
```
