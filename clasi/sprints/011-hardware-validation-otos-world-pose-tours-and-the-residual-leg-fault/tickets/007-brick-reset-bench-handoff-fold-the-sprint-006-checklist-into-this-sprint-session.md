---
id: '007'
title: 'Brick-reset bench handoff: fold the sprint 006 checklist into this sprint
  session'
status: open
use-cases:
- SUC-007
depends-on: []
github-issue: ''
issue: brick-reset-bench-measurement.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Brick-reset bench handoff: fold the sprint 006 checklist into this sprint session

## Description

**This ticket does NOT run the bench experiment.** Sprint 006 already
shipped the fix (`EncoderGlitchArmor`, `kAcceptAsRebaseline` re-anchoring
`encOffset_`, DIAG ordinal 27 — sprint 006 ticket 005) and already wrote
the full bench checklist (sprint 006 ticket 006, archived at
`clasi/sprints/done/006-.../issues/brick-reset-odometry-teleport.md`).
`brick-reset-bench-measurement.md` (this sprint's linked issue) is the
successor that carries only the part needing a robot — it already
points at the archived checklist and asks four specific questions.

This ticket's job is narrow: (1) confirm the archived checklist is
still accurate against current `src/` (not assumed — re-check the cited
symbols), and (2) fold its steps into this sprint's combined bench
session alongside tickets 005 and 006's procedures, since all three
run on the same robot (vevov) in the same physical sitting. **No
acceptance criterion below requires a robot.**

## Acceptance Criteria

- [ ] Re-verify, against current `src/`, that the checklist's cited
      symbols still exist and mean what the checklist says: DIAG
      ordinal 27 (`probe(27)`), `EncoderGlitchArmor::evaluate()`'s
      `kAccept`/`kAcceptAsRebaseline`/`kRejectPending` outcomes,
      `nezha_port.cpp`'s `encOffset_` re-anchor on
      `kAcceptAsRebaseline`, and `kMaxDeltaCounts = 5000`. Note in this
      ticket's own notes if anything has drifted since sprint 006
      closed (expected: nothing, since no sprint between 006 and 011
      has touched these files — confirm rather than assume).
- [ ] A short section is added to `brick-reset-bench-measurement.md`
      (not a rewrite of the archived checklist — a pointer plus
      sequencing) stating: run this alongside tickets 005/006's
      procedures in one combined bench session, and restating the four
      questions from that issue inline so a bench operator sees them
      without following two links.
- [ ] The four questions (does the armor fire on a real reset? does
      pose stay continuous? no false positives during normal driving?
      are rebaseline and reject distinguishable via `probe(27)` vs.
      `probe(23)`/`probe(24)`?) are each restated with what a
      confirmed vs. ruled-out answer looks like, matching the level of
      specificity the archived sprint 006 checklist already used.
- [ ] No acceptance criterion in this ticket, or produced by it,
      requires actually running the experiment or reports a pass/fail
      based on hardware results.

## Implementation Plan

**Approach:** Read the archived checklist
(`clasi/sprints/done/006-.../issues/brick-reset-odometry-teleport.md`)
and `brick-reset-bench-measurement.md` (this sprint's copy) side by
side; confirm the cited symbols against current `src/`; add the
sequencing/restatement section to this sprint's issue copy. Do not
duplicate the archived checklist's full text — reference it and
restate only the four questions plus the sequencing note, matching
sprint 006 ticket 006's own economical style.

**Files to modify:**
- `clasi/sprints/011-.../issues/brick-reset-bench-measurement.md`

**Testing plan:** none — this ticket produces documentation, not code.
Do not run `pytest`/host tests for this ticket beyond confirming no
unrelated regressions from this sprint's other tickets.

**Documentation updates:** the issue file itself (above) is the
deliverable. `design/tools-root-DESIGN.md`'s "Campaign tooling and
bench-handoff procedures" section already names this ticket's role at
planning time.

## C++11 Gate Coverage

Not applicable — documentation only, no source touched (this ticket
re-verifies existing symbols by reading, it does not modify them).
