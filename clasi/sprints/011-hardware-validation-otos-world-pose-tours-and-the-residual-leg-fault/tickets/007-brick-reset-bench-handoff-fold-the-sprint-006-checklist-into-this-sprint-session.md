---
id: '007'
title: 'Brick-reset bench handoff: fold the sprint 006 checklist into this sprint
  session'
status: in-progress
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

- [x] Re-verify, against current `src/`, that the checklist's cited
      symbols still exist and mean what the checklist says: DIAG
      ordinal 27 (`probe(27)`), `EncoderGlitchArmor::evaluate()`'s
      `kAccept`/`kAcceptAsRebaseline`/`kRejectPending` outcomes,
      `nezha_port.cpp`'s `encOffset_` re-anchor on
      `kAcceptAsRebaseline`, and `kMaxDeltaCounts = 5000`. Note in this
      ticket's own notes if anything has drifted since sprint 006
      closed (expected: nothing, since no sprint between 006 and 011
      has touched these files — confirm rather than assume).
- [x] A short section is added to `brick-reset-bench-measurement.md`
      (not a rewrite of the archived checklist — a pointer plus
      sequencing) stating: run this alongside tickets 005/006's
      procedures in one combined bench session, and restating the four
      questions from that issue inline so a bench operator sees them
      without following two links.
- [x] The four questions (does the armor fire on a real reset? does
      pose stay continuous? no false positives during normal driving?
      are rebaseline and reject distinguishable via `probe(27)` vs.
      `probe(23)`/`probe(24)`?) are each restated with what a
      confirmed vs. ruled-out answer looks like, matching the level of
      specificity the archived sprint 006 checklist already used.
- [x] No acceptance criterion in this ticket, or produced by it,
      requires actually running the experiment or reports a pass/fail
      based on hardware results.

## Notes (verification results, 2026-08-25)

Re-verified all four cited symbols against `src/` at commit `940f997`
on this sprint branch — each read directly, not assumed:

- **DIAG ordinal 27 / `probe(27)`** — confirmed. `src/shims.cpp:812-814`,
  `diagValue()`'s `case 27`, returns
  `left.rebaselineCount_ + right.rebaselineCount_`; the `probe(int)`
  shim at `shims.cpp:1078` forwards to `diagValue()` unchanged.
- **`EncoderGlitchArmor::evaluate()`'s three outcomes** — confirmed.
  `src/encoder_glitch_armor.h:50-60` declares the
  `kAccept`/`kAcceptAsRebaseline`/`kRejectPending` enum exactly as
  described; `:107-130` is `evaluate()`'s body, and the two-strike
  logic (first implausible read -> `kRejectPending`, second
  self-consistent implausible read -> `kAcceptAsRebaseline`) matches
  the checklist's description precisely.
- **`nezha_port.cpp`'s `encOffset_` re-anchor on
  `kAcceptAsRebaseline`** — confirmed. `src/nezha_port.cpp:261-277`;
  the formula itself is line 275:
  `encOffset_ = raw - static_cast<int32_t>(lastPosition_) * fwdSign_;`,
  matching the checklist's "map to the position already held, not to
  zero" description.
- **`kMaxDeltaCounts = 5000`** — confirmed. `src/encoder_glitch_armor.h:98`,
  with its full derivation comment intact above it.

**One correction to the "expected: nothing has touched these files"
assumption in this ticket's own acceptance criterion**: that is not
quite right. `git log` shows `shims.cpp` and `nezha_port.cpp` were
each touched by intervening tickets after sprint 006 closed (sprint
007 ticket 007's DIAG case-25 reorder, sprint 009 tickets 007/008's
comment cleanup + provenance-name sweep, sprint 010 ticket 004's I2C
bus-hang guard investigation). However, `git blame` on the four
specific cited spans (the `case 27` block, `evaluate()`'s three
`return` statements, the `encOffset_` re-anchor line, and
`kMaxDeltaCounts`) shows every one of them still traces to `bffac352`
(006-005, 2026-08-24) — none of the later touches landed on these
particular lines. So: the files moved around them, but the four cited
symbols themselves did not drift in name or meaning. No drift found.

The bench-session section (four questions restated with
confirmed/ruled-out criteria, sequencing note to run alongside tickets
005/006, and a caution block for the radio-relay/camera/i2cf points
measured on vevov 2026-08-25) was added to
`clasi/sprints/011-hardware-validation-otos-world-pose-tours-and-the-residual-leg-fault/issues/brick-reset-bench-measurement.md`
under the heading "Ticket 007 handoff: re-verified against `src/`,
sequenced into this sprint's bench sitting." No hardware was touched;
no experiment was run; no pass/fail is recorded anywhere in this
ticket or the issue file.

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
