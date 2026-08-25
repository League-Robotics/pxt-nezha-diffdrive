---
id: '005'
title: 'OTOS world-pose validation campaign: bench procedure and evidence template'
status: done
use-cases:
- SUC-005
depends-on:
- '001'
- '002'
github-issue: ''
issue: otos-on-vevov-move-goto-world-pose-square-tours.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# OTOS world-pose validation campaign: bench procedure and evidence template

## Description

**This ticket does NOT run the bench campaign.** Its acceptance
criteria are about producing a clear, actionable, reviewable procedure
— a written bench session the stakeholder (or a future sprint) can
execute — not about the campaign's outcome. **No acceptance criterion
below requires a robot.** This mirrors sprint 006 ticket 006's
established precedent for exactly this kind of handoff (see
`clasi/sprints/done/006-.../tickets/done/006-brick-reset-bench-experiment-handoff-checklist.md`).

The campaign itself, per the issue's own Verification section and this
sprint's `sprint.md`: re-confirm (not re-derive) the lever-arm
calibration still holds, then run repeated `RUN:tour:world` (OTOS-
guided) and `RUN:tour:robot` (encoder+IMU baseline) passes on vevov, on
the mat, with the AprilCam running throughout as independent ground
truth — diagnostics only, never steering a move in flight, per this
project's standing camera-is-diagnostics-not-control doctrine. Capture
via ticket 001's retargeted `tour_capture.py`; score via ticket 002's
`leg_analysis.py` and the existing `tour_chart.py`; compare against the
issue's own verification bar and the recorded 9-54 mm/1-7° encoder-only
baseline (`RUN:straight`).

## Acceptance Criteria

- [x] A written procedure exists (added to
      `otos-on-vevov-move-goto-world-pose-square-tours.md` as a new
      "Bench Campaign Procedure" section) listing, in order: (1) the
      lever-arm re-confirmation step (`RUN:cal:1` — the verify pass,
      not a re-derivation — expected residual near zero against the
      already-measured 38.2 mm arm, `test/test.ts:42-49`); (2) the
      exact commands for repeated `RUN:tour:world`/`RUN:tour:robot`
      captures via `tour_capture.py --tour world`/`--tour robot`; (3)
      how many repetitions constitute a real sample (not a single
      pass/fail — name a specific minimum, e.g. matching the
      repetition count the pre-006 baseline campaign used); (4) the
      exact scoring commands (`leg_analysis.py`, `tour_chart.py`)
      and what numbers to record per corner (OTOS closure, encoder
      closure, heading residual).
      — Verified: section §5 (lever-arm re-confirmation, `RUN:cal:1`
      via `otos_levercal.py --radio --verify`, citing the 38.2 mm arm
      at `test/test.ts:52-59` — the ticket's own `:42-49` citation
      points at the adjoining corner-geometry constants, not the arm
      values; corrected to the accurate line range), §6 (exact
      `tour_capture.py --radio --tour world`/`--tour robot` commands),
      §7 (repetition count — see note below), §9 (exact
      `leg_analysis.py`/`tour_chart.py` commands and the per-corner
      fields to record). The pre-006 baseline's own repetition count
      is not recorded anywhere in this repository (checked: the issue
      file, the sprint 006 archive, and a repo-wide search for the
      9-54 mm/1-7° and "~70%" figures) — §7 states this explicitly and
      names a specific, justified minimum (10 repetitions per tour
      type) instead of fabricating a historical figure.
- [x] The procedure states explicitly what "meets the issue's
      verification bar" means numerically: per-corner OTOS residual
      within the arrival tolerance (10 mm per the issue's Verification
      section), and closure compared against the 9-54 mm/1-7°
      encoder-only baseline.
      — Verified: "What 'meets the issue's verification bar' means,
      numerically" subsection, directly after §9.
- [x] The procedure references ticket 001's and ticket 002's shipped
      tools by name/path, and sprint 005 ticket 006's `otos_levercal.py`
      retarget as a prerequisite — do not ask the bench operator to
      also debug tooling the procedure assumes already works.
      — Verified: §0 ("Prerequisites already shipped") names
      `tools/tour_capture.py` (ticket 001), `tools/leg_analysis.py`
      (ticket 002), `tools/otos_levercal.py --radio --verify` (sprint
      005 ticket 006's retarget — confirmed already present and
      speaking the named `RUN` vocabulary by inspection of the current
      working tree), and `tools/tour_chart.py`.
- [x] The procedure explicitly restates the camera doctrine (AprilCam
      is diagnostics/scoring only, never in the control loop for a move
      in flight) so a bench operator does not accidentally wire it into
      `goToWorld`'s live path.
      — Verified: §4 ("Camera doctrine — restated so nobody wires this
      into the control loop").
- [x] No acceptance criterion in this ticket, or produced by it,
      requires actually running the campaign or reports a pass/fail
      based on hardware results. Verify this explicitly before closing
      the ticket.
      — Verified: every AC above, and the new "Bench Campaign
      Procedure"/"Evidence Template" sections, only ask that a written
      procedure and a fill-in-the-blank template exist. The issue
      file's own new "No campaign has been run, and no result is
      reported here" subsection states this explicitly; the Evidence
      Template section is blank fields, not a filled report.
- [x] Ticket frontmatter's `depends-on: ['001', '002']` reflects the
      real dependency (the procedure names both tools by their shipped
      CLI shape).
      — Already correct in this ticket's frontmatter; unchanged.

## Implementation Plan

**Approach:** Write the procedure directly into
`otos-on-vevov-move-goto-world-pose-square-tours.md` (the issue file)
as a new section, in the style sprint 006 ticket 006 and sprint 004
ticket 005 already established for this project's hardware handoffs —
short, actionable, no re-derivation of methodology already settled
elsewhere in the issue.

**Files to modify:**
- `clasi/sprints/011-.../issues/otos-on-vevov-move-goto-world-pose-square-tours.md`
  — add the Bench Campaign Procedure section.

**Testing plan:** none — this ticket produces documentation, not code.
Do not run `pytest`/host tests for this ticket beyond confirming no
unrelated regressions from this sprint's other tickets.

**Documentation updates:** the issue file itself (above) is the
deliverable. `design/tools-root-DESIGN.md`'s "Campaign tooling and
bench-handoff procedures" section already names this procedure at
planning time — no further overlay edit needed unless the procedure's
actual shape (repetition count, exact command sequence) differs from
what that section describes, in which case update it and regenerate
its `.diff.md` by hand.

## C++11 Gate Coverage

Not applicable — documentation only, no source touched.
