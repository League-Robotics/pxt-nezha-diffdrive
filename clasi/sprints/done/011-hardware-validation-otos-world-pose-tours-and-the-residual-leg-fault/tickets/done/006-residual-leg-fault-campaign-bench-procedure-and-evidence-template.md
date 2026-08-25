---
id: '006'
title: 'Residual leg-fault campaign: bench procedure and evidence template'
status: done
use-cases:
- SUC-006
depends-on:
- '002'
- '003'
- '004'
github-issue: ''
issue: intermittent-cw-pivot-abort-wheel-reversal.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Residual leg-fault campaign: bench procedure and evidence template

## Description

**This ticket does NOT run the bench campaign.** Its acceptance
criteria are about producing a clear, actionable, reviewable procedure
that turns the issue's own "next probes" and this sprint's tooling
(tickets 002-004) into one repeatable session — not about the
campaign's outcome. **No acceptance criterion below requires a
robot.** A hunt sprint cannot honestly promise a root cause (see
`sprint.md`'s own Success Criteria); this ticket's job is to make the
*attempt* well-instrumented and its *success bar* honest
("instrumented and characterized," not "found"), not to guarantee a
result.

Per the issue's own text: the RETIRED THEORIES list (battery sag,
tick-loop starvation, encoder 0x46 latch, direction mirroring,
track/scrub calibration) is closed evidence, not a checklist to redo —
this procedure must say so explicitly and forbid re-running any of
those experiments, per this sprint's own "Do not re-test any RETIRED
THEORY" rule.

## Acceptance Criteria

- [x] A written procedure exists (added to
      `intermittent-cw-pivot-abort-wheel-reversal.md` as a new "Bench
      Campaign Procedure" section) specifying: (1) a repetition count
      sufficient for a real failure rate, not a single pass/fail —
      name a specific minimum, informed by the 2026-08-20 warm
      campaign's own sample size; (2) the exact commands (repeated
      `RUN:tour:world`/`RUN:tour:robot` via `tour_capture.py`); (3)
      per-leg logging via ticket 002's `leg_analysis.py`, explicitly
      capturing the straight-overrun vs. mid-leg-truncation split and
      the heading-closes-but-distance-doesn't signature; (4) how
      ticket 003's and ticket 004's findings feed into what the
      campaign specifically watches for (e.g. if ticket 003 found and
      fixed a `moveDeadline` defect, the campaign's first job is
      confirming that failure mode is gone; if ticket 004 surfaced a
      first-move hypothesis, the campaign explicitly logs whether the
      first move of each session differs from subsequent ones).
      **Done:** repetition count is 20 runs per tour type (derived
      from the 2026-08-20 campaign's own recorded ~30% failure rate,
      since no raw N is preserved in the repo — see "Repetition count"
      step); exact `tour_capture.py --radio` commands given; per-leg
      `leg_analysis.py` logging specified with both distance and
      heading error always recorded; ticket 003 (RULED OUT, not fixed
      — no defect was found) and ticket 004 (code-review-only,
      dedicated first-move-after-boot probe) both fed into named
      "what to watch for" steps.
- [x] The RETIRED THEORIES list is restated inline in the procedure
      (not just referenced), with an explicit instruction: if a
      symptom looks like one of them again, record that as a finding,
      do not re-run the original experiment.
      **Done:** all five restated with their evidence, plus the
      explicit do-not-re-run instruction.
- [x] The procedure states explicit confirmed-vs-ruled-out criteria:
      what result counts as "the fault is fixed" (e.g. failure rate
      drops to noise level across the sample), what counts as "still
      present but narrowed" (e.g. one failure mode gone, another
      persists), and what counts as "a new signature" not covered by
      either prior theory set.
      **Done:** three named buckets (CONFIRMED FIXED / STILL PRESENT
      BUT NARROWED / NEW SIGNATURE), each with a stated numeric or
      structural bar tied to the sample size's own statistics
      (rule-of-three noise floor), not an arbitrary threshold.
- [x] The procedure instructs: if the fault is confirmed fixed, close
      `intermittent-cw-pivot-abort-wheel-reversal.md` directly,
      recording the campaign's numbers. If not, file a sharpened
      successor issue stating plainly what this campaign additionally
      ruled out (building on this issue's own already-retired list)
      and what it narrowed the remaining suspects to — matching this
      sprint's Success Criteria.
      **Done:** Close-out subsection covers both branches explicitly.
- [x] No acceptance criterion in this ticket, or produced by it,
      requires actually running the campaign or reports a pass/fail
      based on hardware results. Verify this explicitly before closing
      the ticket.
      **Verified:** the procedure's own closing subsection ("Verification
      that this ticket needed no robot") states this explicitly; every
      number cited in the procedure is either prior evidence already in
      the issue file (cited by reference) or ticket 003's own host-test
      result (not a robot result). No campaign was run by this ticket.
- [x] Ticket frontmatter's `depends-on: ['002', '003', '004']`
      reflects the real dependency (the procedure names all three
      tickets' tooling/findings by name).
      **Verified:** frontmatter already listed all three; the
      procedure names `leg_analysis.py` (002), the moveDeadline
      RULED-OUT finding (003), and the first-move-after-boot finding
      (004) by ticket number and content throughout.

## Implementation Plan

**Approach:** Write the procedure directly into
`intermittent-cw-pivot-abort-wheel-reversal.md` (the issue file), same
style as ticket 005 and the sprint 006 ticket 006 precedent. Read
ticket 003's and ticket 004's actual findings (by the time this ticket
executes, if sequenced after them as `depends-on` requires) before
writing the "what to specifically watch for" part — do not write it
purely from this planning pass's speculation about what those tickets
might find.

**Files to modify:**
- `clasi/sprints/011-.../issues/intermittent-cw-pivot-abort-wheel-reversal.md`
  — add the Bench Campaign Procedure section.

**Testing plan:** none — this ticket produces documentation, not code.
Do not run `pytest`/host tests for this ticket beyond confirming no
unrelated regressions from this sprint's other tickets.

**Documentation updates:** the issue file itself (above) is the
deliverable. `design/tools-root-DESIGN.md`'s "Campaign tooling and
bench-handoff procedures" section already names this procedure at
planning time — no further overlay edit needed unless its actual shape
differs from what that section describes.

## C++11 Gate Coverage

Not applicable — documentation only, no source touched.
