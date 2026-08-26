---
id: '004'
title: Remove src/DESIGN.md S12-S16; stop the per-sprint append
status: done
use-cases:
- SUC-001
depends-on:
- '003'
github-issue: ''
issue: src-design-md-is-half-sprint-history.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Remove src/DESIGN.md S12-S16; stop the per-sprint append

## Description

`src/DESIGN.md` is 2045 lines, of which S12-S16 ("Sprint 006/007/008/012/013
-- architecture diagram and change summary") are 902 lines, 44% of the
document -- pure sprint-history appendix, not design content. This is the
design-doc analogue of the ticket-archaeology comment anti-pattern
`docs/code-review/guidelines.md` already bans in source, and it fails the
same way: S15 (315 lines) describes sprint 012's split of `main.ts` into
six modules, whose product now lives in `src/blocks/` -- a directory S15
doesn't know exists, because S16 (sprint 013) moved it one sprint later. A
reader has to hold S9, S15, and S16 simultaneously to work out what's
actually true today.

Each of S12-S16 already exists verbatim in its own sprint's
`clasi/sprints/NNN-*/design/` overlay (sprint history is git's job, and
each sprint's own directory already carries this). Deleting S12-S16 from
`src/DESIGN.md` and keeping S1-S11 loses nothing.

**Depends on ticket 003** finishing first -- 003 edits S10 and the header,
and this ticket removes S12-S16; running them in this order avoids the two
tickets conflicting inside the same file.

## What to change

1. Delete S12-S16 from `src/DESIGN.md` entirely. Confirm nothing in S1-S11
   depends on content that only exists in S12-S16 (a quick read-through;
   S1-S11 is described elsewhere as "genuinely good" and self-contained --
   if something does turn out to be load-bearing, migrate that one fact
   into the relevant S1-S11 section rather than keeping the whole
   sprint-history section).
2. **Find and stop the recurrence mechanism.** Something in the sprint-close
   or architecture-consolidation path appends one "architecture diagram and
   change summary" section per sprint to `src/DESIGN.md`. Identify what --
   likely candidates are the `consolidate-architecture` skill or whatever
   `close_sprint`/`review_sprint_pre_close` invokes for architecture
   consolidation. Read how it decided to target `src/DESIGN.md` specifically
   (as opposed to the sprint's own `clasi/sprints/NNN-*/` directory, which
   is where this content already independently lives) and stop it from
   doing so -- either by reconfiguring what it consolidates into, or by
   documenting `src/DESIGN.md`'s S1-S11-only contract somewhere the
   mechanism reads (if it's config-driven), or by whatever mechanism
   correctly prevents the next append. This step matters more than the
   deletion: without it, sprint 018's close silently regrows S12.
3. Record the contract this ticket establishes -- "`src/DESIGN.md` S1-S11
   describes the system; sprint history lives in each sprint's own
   directory, not appended here" -- in `docs/design/design.md`, per this
   sprint's Architecture section, which already names this as the one
   structural decision in scope.

## Acceptance Criteria

- [x] `src/DESIGN.md` S12-S16 are removed; the document contains only
      S1-S11 (renumbered if the removal leaves a numbering gap -- check
      whether S1-S11 cross-reference each other by number and fix if so).
      Note: former S17 ("Sprint 016 -- stop taxonomy," a cross-cutting
      reference table, not sprint archaeology -- kept per this ticket's
      own instructions) is renumbered to S12. All `§12`-`§17`
      cross-references found throughout `src/DESIGN.md`, plus three
      dangling ones in `docs/design/design.md` and `tests/host/DESIGN.md`
      that pointed into the deleted sections, were fixed or dropped (a
      few carried genuinely load-bearing detail -- e.g. the sprint-013
      `#include` path-qualification rule, the stall-latch-vs-e-stop-latch
      separation rationale -- migrated into S1/S9 rather than lost).
- [x] The mechanism that appended one section per sprint is identified and
      is either disabled for `src/DESIGN.md` or reconfigured so a future
      `close_sprint` does not regrow this pattern. **Mechanism**: the
      CLASI-package `architecture-authoring` skill's Mode 2a (used when
      `design_docs_opt_in` is true, as it is here) instructs a sprint's
      architecture author to open the seeded canonical-doc overlay copy
      and "write a complete, updated copy... reflecting the sprint's
      planned changes," reusing Mode 1's from-scratch section list
      (Module Design, Dependency Graph, Migration Concerns, Risk, Design
      Rationale, "Sprint Changes") and diagram requirement. Confirmed by
      reading the sprint 006/007/008/012 overlay `.diff.md` files
      directly: each shows genuine in-place edits to the real sections
      **plus** an appended dated "Sprint NNN -- architecture diagram and
      change summary" block, both committed at `close_sprint`'s
      `design_overlay_apply` step. Sprint 013's instance predates that
      sprint ever seeding an overlay -- a ticket hand-wrote the same
      pattern directly, imitating the visible convention sprints
      006-012 had already established. `.claude/skills/
      architecture-authoring/SKILL.md` is confirmed byte-identical to
      the installed CLASI package's own copy (`diff` returns no
      difference), so it is CLASI-server code outside this project's
      source tree -- no ticket here can change its instructions. Change
      that stops it: the rule is recorded in `docs/design/design.md`'s
      new "Subsystem-doc contract: content, not sprint history"
      subsection for a future sprint's architecture author (human or
      agent) to read and follow instead -- edit sections in place, do
      not add a new dated section, in the overlay or directly in the
      canonical doc.
- [x] `docs/design/design.md` records the "S1-S11 is the contract, sprint
      history lives in `clasi/sprints/`" decision.
- [x] `clasi design validate` still returns `ok: true` after the deletion.
- [x] No firmware source file is touched.

## Testing

- **Existing tests to run**: none directly -- doc-only. Run
  `clasi design validate` to confirm the deletion didn't break the
  validator (ticket 001 should have already made it green).
- **New tests to write**: none required by this ticket's own scope, but if
  the recurrence mechanism turns out to be something a host test *can*
  pin (e.g. a specific script or template file that generates the
  append), consider whether a cheap guard is feasible -- optional, only if
  it's a natural fit once the mechanism is found. Don't force a test onto
  a process step that doesn't have one.
- **Verification command**: `clasi design validate`.
