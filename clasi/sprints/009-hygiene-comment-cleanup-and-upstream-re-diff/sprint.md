---
id: 009
title: 'Hygiene: comment cleanup and upstream re-diff'
status: roadmap
branch: sprint/009-hygiene-comment-cleanup-and-upstream-re-diff
use-cases: []
issues:
- comment-cleanup-work-order.md
- vendored-kernel-upstream-rediff.md
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sprint 009: Hygiene: comment cleanup and upstream re-diff

> **Arc position.** Fifth and closing sprint out of the 2026-08-23 code
> review (`docs/code-review/2026-08-23/review.md`), after sprint 004
> (radio/wire transport, ticketing), sprint 005 (bench tooling, roadmap,
> blocked on 004's hardware checkpoint), sprint 006 (motion correctness,
> roadmap), sprint 007 (student API, roadmap), and sprint 008 (wire
> hardening, roadmap). It runs **deliberately last, not by triage order but
> by necessity**: sprints 006-008 rewrite many of the same regions this
> sprint's comment audit covers (`shims.cpp`, `wire_handler.*`,
> `wire_adapter.*`, `protocol.*`, the settle-tick loop). Comment cleanup
> against pre-fix code would be thrown away or re-diffed the moment any of
> those three sprints lands; running it last means the audited work order
> applies once, to the code as it actually ends up, with no rework. This
> is also why the sprint is behavior-neutral by design — a hygiene pass
> that changes behavior would need to be re-validated against whatever
> 006-008 changed underneath it, defeating the point of going last.

## Goals

Theme: **comments say only what's true and load-bearing, and the vendored
kernel's relationship to its upstream is documented and current.** Two
issues, one theme (the codebase's *written record* — comments and
provenance — catches up to what the code actually does), zero behavior
change:

- Apply the audited 135-item comment work order (11 DELETE, 123 REWRITE,
  1 ADD out of ~854 blocks across 59 files) from
  `docs/code-review/2026-08-23/raw/comment-audit.md`, corrected by
  `docs/code-review/2026-08-23/raw/verify-comments.md` wherever the two
  disagree. Spot-verification already found 8 of 16 sampled rewrites would
  have lost load-bearing content (worst case: a wrong calibration constant
  baked into the rotationalSlip derivation), so the correction pass is not
  optional cleanup — it is the difference between a hygiene sprint and a
  silent regression sprint.
- Restore the five truncated `diffdrive.h` comments (lines 81, 84, 90, 91,
  125) from the upstream text already recovered in verify-comments.md, and
  re-diff `src/diffdrive.h/.cpp` against current upstream
  `League-Robotics/radio-robot` `src/firm/diffdrive/` to catalogue every
  remaining divergence as deliberate (documented) or accidental (fixed or
  backported) — closing the possibility that a lossy vendoring step lost
  code deltas along with comment text, the way it lost the
  `fullDutyVelocity = 0` "uncalibrated -> VELOCITY refused" contract that
  the cruise-sentinel bug later tripped over.
- Fix the provenance pointers themselves: `src/DESIGN.md` and
  `overview.md` §Provenance both still name an old upstream path; the
  upstream kernel has moved to `src/firm/diffdrive/`
  (`differential_drive.h`), and two places name a repo variant that
  doesn't exist. State the maintenance boundary (what may be edited here
  vs. upstream) alongside the corrected path.
- Distill the audit's five recurring comment anti-patterns
  (ticket-archaeology headers, reviewer-justification essays, stale
  cross-layer claims, diff restatement, orphaned comments) into a short
  comment-standards section of `docs/code-review/guidelines.md`, so the
  next round of work doesn't regenerate the same noise this sprint
  deletes.

## Problem

Two related but independent gaps, both filed as LOW-priority findings
from the 2026-08-23 review's comment-hygiene dimension (R-28 and the
comment work order in `review.md` §"Comment hygiene (work order)"):

1. **Signal-to-noise in comments.** The audit classified ~854 comment
   blocks across 59 files and found ~16% pure noise, concentrated in the
   wire-layer headers (`serial_transport.h` 83%, `wire_adapter.h` 71%,
   `tests/host/README.md` 60%): ticket archaeology, restated diffs,
   reviewer-justification essays, and cross-layer claims that no longer
   match the code. Left alone, this noise compounds — every future editor
   reads it, half-trusts it, and sometimes copies the pattern forward.
2. **Unverified vendoring boundary.** The kernel (`src/diffdrive.h/.cpp`)
   was vendored from `League-Robotics/radio-robot` at some point in the
   past, but the copy is known-lossy: five comments are truncated
   mid-sentence, and one of the lost halves encoded a real behavioral
   contract, not just prose. If comment text was truncated during
   vendoring, code deltas may have been dropped too, and nobody has
   re-diffed against upstream to check. The provenance pointers that are
   supposed to document this boundary (`src/DESIGN.md`,
   `overview.md` §Provenance) also point at a path upstream no longer
   uses.

## Solution

Two issues, worked together because they share a "read the written
record, correct it against ground truth, don't change behavior" shape,
and because both touch `src/diffdrive.h` (the re-diff restores the same
five comments the work order's item list also names — doing this once,
not twice):

- **`comment-cleanup-work-order.md`**: apply `comment-audit.md`'s
  delete/rewrite/add work order, with every item — sampled or not —
  checked against `verify-comments.md`'s corrections and, for anything
  outside the 27 already spot-checked, against the same test
  spot-verification applied: does the replacement preserve every
  invariant, unit, measured value, and derivation the original comment
  carried? Restore (not paraphrase) the five upstream-truncated
  `diffdrive.h` comments per item 3 of the issue. Fix
  `tests/host/README.md`'s stale "does NOT cover yet" section per the
  audit. Fold the five anti-patterns into `docs/code-review/guidelines.md`
  as a follow-up in the same work, so the standard is written down once
  the noise it targets has actually been removed.
- **`vendored-kernel-upstream-rediff.md`**: diff `src/diffdrive.h/.cpp`
  against `League-Robotics/radio-robot`'s current `src/firm/diffdrive/`.
  Every divergence gets catalogued as deliberate (documented in place) or
  accidental (fixed or backported — but only where the divergence proves
  accidental; see Scope). Correct the provenance path and repo-variant
  references in `src/DESIGN.md` and `overview.md` §Provenance, and add
  the maintenance-boundary statement (what's edited here vs. upstream)
  that both currently lack.

Because both issues touch the same file (`diffdrive.h`'s five truncated
comments), Detail Mode should sequence the re-diff's comment restoration
and the work order's `diffdrive.h` items as one coordinated ticket-level
edit, not two independent passes that could each partially clobber the
other's changes to the same lines.

## Success Criteria

- All 135 audited comment items applied, with every REWRITE (sampled and
  unsampled) checked against `verify-comments.md` and against the "does
  this preserve every invariant, unit, measured value, and derivation"
  test — zero load-bearing content lost.
- The five `diffdrive.h` truncated comments (lines 81, 84, 90, 91, 125)
  read the full upstream text, not a paraphrase.
- `src/diffdrive.h/.cpp` has been diffed against current upstream
  `League-Robotics/radio-robot src/firm/diffdrive/`; every divergence is
  either documented as deliberate or fixed/backported as accidental.
- `src/DESIGN.md` and `overview.md` §Provenance name the correct upstream
  path (`src/firm/diffdrive/`, `differential_drive.h`) and no longer
  reference a nonexistent repo variant; both state the maintenance
  boundary.
- `docs/code-review/guidelines.md` has a comment-standards section
  covering the audit's five anti-patterns.
- `tests/host/README.md`'s stale coverage section is corrected.
- The scoped test suites for every touched module pass unchanged —
  proving the sprint is behavior-neutral (comments/docs-only, plus any
  accidental-divergence fixes in `diffdrive.*` that the re-diff surfaces).

## Scope

### In Scope

- Comment and doc-text edits across `src/`, `tests/host/`, `tools/`, and
  `test/`, per the audited work order and its corrections.
- `src/diffdrive.h/.cpp`: comment restoration (the five truncated
  comments) plus code changes **only where the upstream re-diff proves a
  divergence is accidental** (e.g., a dropped guard or constant upstream
  still carries) — not a general refactor of the kernel.
- Provenance-pointer corrections in `src/DESIGN.md` and
  `overview.md` §Provenance, including the maintenance-boundary statement.
- A new comment-standards section in `docs/code-review/guidelines.md`.

### Out of Scope

- Any behavior change to `diffdrive.h/.cpp` beyond fixing divergences the
  re-diff shows to be accidental — this is not a place to opportunistically
  "improve" the kernel logic.
- Anything owned by sprints 006, 007, or 008 (motion correctness, student
  API, wire hardening) — this sprint runs after them specifically to avoid
  overlapping their code changes.
- Renumbering, restructuring, or otherwise reorganizing files beyond
  comment/doc-text content.
- New tests beyond what's needed to confirm the scoped modules are
  unchanged in behavior (this is a comment/doc sprint, not a
  test-coverage sprint).

## Test Strategy

Behavior-neutral by construction, so the bar is regression, not new
coverage: run the existing scoped test suites (host tests plus whatever
`test/`/`tools/` coverage exists) for every module touched by the comment
work order and the `diffdrive.*` re-diff, before and after, and confirm
no output changes. Any accidental-divergence fix the re-diff surfaces in
`diffdrive.*` gets its own targeted verification against the specific
behavior upstream defines (e.g., the `fullDutyVelocity = 0` refusal
semantics), since that one class of change is not purely cosmetic. No new
test infrastructure is anticipated; Detail Mode should confirm this
against actual coverage gaps once tickets are scoped.

## Architecture

(Architecture for this sprint's change, sized to the change — a
one-paragraph note for a trivial sprint, a fuller write-up with
component/data-model detail for a substantial one. May read "N/A —
trivial" when the change has no architectural impact.)

### Architecture Overview

(High-level structure and component relationships, if applicable.)

### Design Rationale

(Significant decisions with alternatives considered and reasoning, if
applicable.)

### Migration Concerns

(Data migration, backward compatibility, deployment sequencing — or
"None" if not applicable.)

## Use Cases

(Use cases sized to the change — may read "N/A — trivial" for small
sprints that don't warrant new or updated use cases.)

### SUC-001: (Title)
Parent: UC-XXX

- **Actor**: (Who)
- **Preconditions**: (What must be true before)
- **Main Flow**:
  1. (Step)
- **Postconditions**: (What is true after)
- **Acceptance Criteria**:
  - [ ] (Criterion)

## GitHub Issues

(GitHub issues linked to this sprint's tickets. Format: `owner/repo#N`.)

## Definition of Ready

Before tickets can be created, all of the following must be true:

- [ ] Sprint planning document is complete (sprint.md, including its
      Architecture and Use Cases sections)
- [ ] Architecture review passed (or skipped, for changes with no
      architectural impact)
- [ ] Stakeholder has approved the sprint plan

## Tickets

| # | Title | Depends On |
|---|-------|------------|

Tickets execute serially in the order listed.
