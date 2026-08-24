---
id: '006'
title: Brick-reset bench experiment handoff checklist
status: done
use-cases:
- SUC-005
depends-on:
- '005'
github-issue: ''
issue: brick-reset-odometry-teleport.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Brick-reset bench experiment handoff checklist

## Description

`brick-reset-odometry-teleport.md`'s hardware premise — whether a
Nezha brick MCU reset mid-session actually restarts the 0x46 encoder
counter near zero — cannot be confirmed or ruled out without a real
robot. Sprint 004 ended at a verified build precisely because hardware
validation is the stakeholder's own follow-up; this ticket follows the
same precedent (sprint 004's ticket 005 — "Phase C Bench Checkpoint").

**This ticket does NOT run the bench experiment.** Its acceptance
criteria are about producing a clear, actionable handoff — a written
checklist the stakeholder (or a future hardware-validation sprint,
e.g. sprint 011) can execute — not about the experiment's outcome.
**No acceptance criterion below requires a robot.** If any criterion
you're tempted to add would require one, it does not belong in this
ticket.

The experiment itself, verbatim from the issue and
`verify-kernel.md`'s own framing: power-cycle the brick mid-drive
while watching DIAG ordinals 10/11 and pose, following this project's
measurement doctrine (prove the DIAG-capture instrument is watching
before interpreting the fault — see `docs/design/` bench-tooling
material, or `project-knowledge`/memory notes on this project's own
"measurement before diagnosis" doctrine).

## Acceptance Criteria

- [x] `brick-reset-odometry-teleport.md` (the issue file, now living
      under this sprint's `issues/` directory) has a clear "Bench
      Checklist" section added, listing: the exact hardware step
      (power-cycle the brick mid-drive), the DIAG ordinals to watch
      (10/11 per the issue's own citation) plus pose, the instrument-
      first verification step (confirm DIAG capture is running and
      receiving data BEFORE the power-cycle, per this project's
      measurement doctrine), and the specific numbers to record
      (position delta, DIAG 10/11 values before/after, whether ticket
      005's new rebaseline DIAG counter fires).
- [x] The checklist states plainly what a "confirmed" vs. "ruled out"
      result looks like for this experiment (e.g. confirmed: DIAG
      counter fires and pose does NOT teleport; ruled out: no
      discontinuity signature at all, or the counter behaves
      differently than hypothesized).
- [x] The checklist references ticket 005's shipped fix by name/path
      so whoever runs the bench knows what code is already in place to
      observe (do not ask the bench operator to also design the fix —
      that already shipped).
- [x] No acceptance criterion in this ticket, or produced by it,
      requires actually running the experiment or reports a
      pass/fail based on hardware results. Verify this explicitly
      before closing the ticket.
      — Verified: every AC above, and the new "Bench Checklist"/
      "Design Note" sections in the issue file, only ask that a
      written procedure exist. The issue file's new "No bench run has
      been performed, and no result is reported here" subsection
      states this explicitly.
- [x] Ticket frontmatter's `depends-on: ['005']` reflects the real
      dependency (the checklist references ticket 005's fix by name).
      — Already correct in this ticket's frontmatter; unchanged.

## Implementation Plan

**Approach:** write the checklist directly into
`brick-reset-odometry-teleport.md` (the issue file) as a new section,
in the same style sprint 004's ticket 005 used for its own hardware
handoff notes (check that ticket's `done/` copy for the established
format/tone if unsure). Keep it short and actionable — a person on the
bench should be able to follow it without re-reading the whole issue
or this ticket.

**Files to modify:**
- `clasi/sprints/006-motion-correctness-goto-geometry-and-odometry-truth/issues/brick-reset-odometry-teleport.md`
  — add the Bench Checklist section.

**Testing plan:** none — this ticket produces documentation, not code.
Do not run `pytest`/host tests for this ticket beyond confirming no
unrelated regressions from the sprint's other tickets.

**Documentation updates:** the issue file itself (above) is the
deliverable. No `src/DESIGN.md` overlay change — this ticket has no
architectural content.
