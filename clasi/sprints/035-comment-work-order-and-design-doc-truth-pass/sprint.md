---
id: '035'
title: Comment work order and design-doc truth pass
status: roadmap
branch: sprint/035-comment-work-order-and-design-doc-truth-pass
use-cases: []
issues:
- code-review/comment-work-order-factual-fixes-untracked-citations.md
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sprint 035: Comment work order and design-doc truth pass

## Goals

Apply the code review's 53-block comment boil-down work order (18 in
the motion-and-kernel annex, 12 in comms, 10 in blocks-and-test, 13 in
tools-and-tests) using the guidelines' safety rules: re-anchor by
content rather than line number, treat every item as a possible no-op,
and check each replacement against the *current* code before landing
it — the same discipline sprint 009's comment cleanup ran. Fix the
sixteen comments the review found factually wrong today (wrong file
names, wrong ordinal numbers, "not consulted by anything yet" where it
now is, "handlers run on their own fiber" where they've run on the
protocol fiber since sprint 028, retired radio channel numbers, a cited
function that doesn't exist, and others listed in review section 5).
Track or relocate the six `MEASURED` citations to `captures/` directories
that are gitignored and untracked, so a fresh clone can actually follow
them. Extend `test_archaeology_marker_budget.py` to also ratchet
comment *volume* (comment lines / code lines) per file, not only the
sprint/ticket-ID marker count it ratchets today, so this cleanup holds
instead of drifting back up the way it did between the 08-26 and
09-02 reviews. Add the two new anti-patterns the review names — dated
UPDATE paragraphs stacked on one comment, and citations to untracked
artifacts — to `docs/code-review/guidelines.md` as anti-patterns 6 and 7.

## Problem

Comment-only lines per code line in project-owned `src/` are back above
the 08-26 review's level (~1.4 now vs 1.22 then), and every file the
last two sprints touched grew: `comms/radio_transport.h` runs 7.26
comment lines per code line, `motion/motion_engine.h` 4.30,
`comms/protocol.h` 3.72 — against the vendored kernel's 0.03. The
existing archaeology ratchet (`_BUDGET = 388`) only holds the count of
sprint/ticket-ID markers; the new growth is a different shape — dated
capture citations instead of sprint numbers — and is just as long, so
the existing ratchet doesn't catch it. Sixteen comments assert things
that are no longer true: two say the source files are named
`differential_drive.{h,cpp}` when they're `diffdrive.{h,cpp}`; one says
the RUN drop count is "ordinal 30" when the real count is 28 (30 is
`max_yaw_rate`); one says two fields are "not consulted by anything
yet" when `defaultCruiseForDistance()` reads both; one says `goToWorld`
is "capped-curvature" when the cap was removed; one says the move
engine "lives HERE" in a file it moved out of; two mis-cite which
ordinals expose which streaks; three say handlers run on their own
fiber via MessageBus when they've run nested on the protocol fiber
since sprint 028; one says "ANY I2C from a RUN handler hangs the board"
in the same file whose handlers do OTOS I2C on every corner; one cites
a function (`Protocol::formatDiag()`) that doesn't exist; three
describe a two-fiber writer model retired since the emit ring; one
misquotes a version string and what it's tested against; one gets the
same-text dedupe window wrong by 7.5×; one cites retired radio
addresses; one cites a closed issue as live; one calls a cached read a
live I2C burst. Six `MEASURED` citations from `src/` point at
`captures/` paths that are gitignored and untracked, so the evidence
behind those claims cannot be checked from a fresh clone —
`.claude/rules/measurement-citations.md`'s whole premise is that a
citation names an artifact that can be checked.

## Solution

Work through the four annexes' boil-down lists in order, each item
re-anchored by matching its quoted content in the current file (not by
the line numbers the review cites, which may have shifted), verifying
the replacement text is still accurate against the code as it stands
today before landing it, and treating any item whose premise has
already changed as a no-op rather than forcing a stale replacement.
Fix the sixteen factual errors listed in review section 5 as targeted
text edits — no rewrite needed beyond making the claim true. For the
six untracked capture citations: either `git add -f` the small
JSON/Python capture directories they point at, or move the cited
numbers into a tracked `reports/*.md` file and repoint the citation
there. Extend `test_archaeology_marker_budget.py` with a second ratchet
on comment-lines-per-code-line per file, seeded from this sprint's
post-cleanup measurement so future growth is caught the way marker
count already is. Add anti-patterns 6 (dated UPDATE paragraphs stacked
on a comment) and 7 (citations to untracked artifacts) to
`docs/code-review/guidelines.md`, each with the concrete example the
review found (`nezha_port.cpp:11-55`'s three-update stack; the six
untracked `captures/` citations).

## Success Criteria

- The per-file comment-ratio table in review section 5 re-measured
  after cleanup: no project-owned file above 2.0 comment lines per code
  line.
- Every `captures/` path cited as MEASURED from `src/` resolves in a
  fresh clone (either tracked directly or replaced by a `reports/*.md`
  citation).
- All sixteen listed factual errors are fixed and spot-checked against
  current code.
- `test_archaeology_marker_budget.py` fails if a file's comment ratio
  regresses past its sprint-034 baseline.
- `docs/code-review/guidelines.md` lists seven anti-patterns, with 6
  and 7 matching the review's descriptions and examples.

## Scope

### In Scope

- The 53-block boil-down work order across `motion_engine.h`,
  `nezha_port.cpp`, `shims.cpp`, `protocol.h`, `protocol.cpp`,
  `radio_transport.h`, and the `blocks/*.ts`/test-program files named
  in the four annexes.
- The sixteen factual-error fixes listed in review section 5.
- The six untracked capture-citation relocations or `git add -f`s.
- `tests/dev/test_archaeology_marker_budget.py` (or wherever the
  archaeology ratchet lives) — the new comment-volume ratchet.
- `docs/code-review/guidelines.md` — anti-patterns 6 and 7.

### Out of Scope

- Everything in sprints A (motion profile), B (bus/fiber safety), C
  (test program/blocks/simulator), D (odometry, config descriptor
  table, Protocol diet), and E (bench tools). This sprint touches
  comments and documentation only — no behavior change to any file it
  edits. Because of that, sequence this sprint last (or at least after
  A-D land) so the boil-down list's re-anchoring step isn't invalidated
  by code those sprints are still moving; the design doc's own note
  that "re-anchor by content, treat every item as a possible no-op" is
  precisely the discipline that makes running this after the code
  churn settles the safer order, not a strict dependency.
- Any code or test-behavior change; a comment-only sprint asserting a
  behavior change under cover of a "boil-down" would violate the
  sizing decision this sprint is planned under.

## Related Issues

- [`code-review/comment-work-order-factual-fixes-untracked-citations.md`](../../issues/code-review/comment-work-order-factual-fixes-untracked-citations.md)

## Test Strategy

(Describe the overall testing approach for this sprint: what types of tests,
what areas need coverage, any integration or system-level testing needed.)

## Architecture

Not yet written — this sprint is in Roadmap Mode. At detail-planning
time this sprint is expected to size as trivial/small (comment and
documentation edits only, no component or data-model impact), but that
sizing decision is made explicitly when the sprint is detail-planned,
not assumed here.

### Architecture Overview

(High-level structure and component relationships, if applicable.)

### Design Rationale

(Significant decisions with alternatives considered and reasoning, if
applicable.)

### Migration Concerns

(Data migration, backward compatibility, deployment sequencing — or
"None" if not applicable.)

## Use Cases

Not yet written — produced at detail-planning time, sized to the
change.

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
