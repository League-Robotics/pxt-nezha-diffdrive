---
id: '006'
title: Comment standard in guidelines.md plus the archaeology-marker ratchet test
status: done
use-cases: []
depends-on: []
github-issue: ''
issue: comment-standard-and-archaeology-ratchet.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Comment standard in guidelines.md plus the archaeology-marker ratchet test

## Description

Comment volume in project-owned `src/` is 1.22 lines per code line, against
0.05 in the vendored kernel beside it (`src/core/diffdrive.{h,cpp}`) -- a
24x gap on the same readers in the same repo. Sprint 009 ran a dedicated
cleanup sprint and bought 8%; every file touched by sprints 010-013 is now
*above* its pre-cleanup count. A cleanup without a write-time rule provably
does not hold.

**Stakeholder decision is already made** (recorded on the
`stakeholder_approval` gate, `get_sprint_phase("017")`): adopt the
write-time comment standard, plus a mechanical budget test starting at the
measured 363 archaeology markers, ratcheting DOWN only. **The bulk ~470-line
cleanup itself is explicitly OUT OF SCOPE for this sprint** -- do not touch
comment volume beyond what's needed to land the standard and the test. This
ticket lands the guard, not the fix; the fix is a later sprint's work,
listed in `docs/code-review/2026-08-26/raw/comment-audit.md` section 10.

**Exception, also already decided and in scope for sprint 015 (not this
ticket)**: the two *wrong* comments in `blocks/motion.ts` (the namespace
docstring's fiber claim, and `isMoving()`'s "checks state only" claim) are
corrected in sprint 015 alongside the code they describe -- not here. Do not
fix them in this ticket even though they're mentioned in the source issue.

## What to change

### 1. Add the write-time standard to `docs/code-review/guidelines.md`

Add this as a new section (or extend the existing comment-hygiene section
if one exists) verbatim or near-verbatim -- this exact text was approved by
the stakeholder:

> A comment must state something a competent reader cannot recover from the
> code in front of them: a unit, a sign convention, an invariant, a
> measured hardware fact, a wire layout, or a hazard.
>
> Sprint numbers, ticket numbers, issue filenames, code-review IDs, and
> "this used to be X" belong in the commit message. Git already stores
> them, and a reader who wants them can `git log -L`.
>
> If the comment is longer than the code it describes, it is a design-doc
> section wearing a comment's clothes. Move it, or cut it to the fact.

Also worth including (from the audit's own analysis, useful context for
future authors): a short "what good looks like" pointer at the keep-list
examples in `comment-audit.md` section 8 (e.g. `motion_engine.h`'s
`travelCalib_`/`rotationalSlip_` comments, `nezha_port.cpp`'s bus-hang
guard) -- comments that state a measured hardware fact a reader cannot
recover from the code, which is the standard in practice.

### 2. Add the archaeology-marker budget test

A host test in the `test_pxt_manifest_completeness.py` style -- no
compiler, reads `src/` as text, milliseconds. Count comment lines matching
any of: `sprint N`, `ticket N`, `R-NN`, `KERN-NN`, `WIRE-NN`, `BLK-NN`,
`API-NN` (and, per the fuller pattern list in `comment-audit.md` section 5,
also consider `MOD-NN`, `DES-NN`, `PY-NN`, and any `.md` filename mention --
the ticket instructions name the shorter list; the audit's own regex is
slightly broader, use the broader one since it's what produced the 363
baseline number) across `src/`, **excluding the vendored**
`src/core/diffdrive.{h,cpp}`. Assert `total <= 363`.

The audit document gives a reference implementation shape:

```python
_MARKERS = re.compile(
    r"\bsprint \d|\bticket \d|\bR-\d\d|KERN-\d\d|WIRE-\d\d|BLK-\d\d|API-\d\d",
    re.I)
_BUDGET = 363          # measured 2026-08-26; ratchet DOWN, never up
```

Verify the count against the current tree before hardcoding 363 -- sprints
015/016 may have shifted the number slightly since the 2026-08-26
measurement (this ticket does not intentionally add or remove archaeology
markers, but other tickets' comment edits, e.g. ticket 003's S10 pass or
ticket 005's stale-reference fixes, could incidentally touch a marker-bearing
line). Use whatever the actual current count is as the budget if it differs
from 363, and note the discrepancy in the ticket's completion notes.

## Acceptance Criteria

- [x] `docs/code-review/guidelines.md` contains the write-time comment
      standard, in the approved language above (verbatim or near-verbatim).
- [x] A new host test asserts the archaeology-marker count across
      project-owned `src/` (excluding vendored `core/diffdrive.{h,cpp}`) is
      `<= ` the measured baseline, ratcheting down only -- raising the
      budget requires an explicit, reviewed change to the test's constant,
      not a silent increase.
- [x] The test passes against the current tree as of this ticket's
      completion.
- [x] No bulk comment cleanup is performed -- comment volume should be
      approximately unchanged except for incidental edits from other
      tickets in this sprint.
- [x] `blocks/motion.ts`'s two wrong comments are explicitly NOT touched
      here (confirm they're left for sprint 015).
- [x] No firmware behavior is changed.

## Completion notes (2026-08-26)

- **Standard**: added verbatim as a new "Write-time standard"
  subsection at the top of `docs/code-review/guidelines.md`'s existing
  section 6 (Comment hygiene), ahead of the review-time delete/keep
  rubric -- the write-time rule is what an author follows while
  writing; the existing section is what a reviewer checks afterward.
  Cross-referenced the ratchet test and the sprint-009-regrew-back
  rationale inline, both requested as "worth including."
- **Ratchet budget re-measured, not reused**: 388, not the briefing's
  363. Replicated `comment-audit.md` section 5's own broader marker
  regex (the one that produced 363, not section 9's narrower sketch)
  against the CURRENT tree, scoped to project-owned `src/` excluding
  vendored `core/diffdrive.{h,cpp}` (measured 2 marker lines there,
  matching the audit's own count exactly -- confirms the methodology
  replicates correctly). Per-file counts mostly match the audit
  closely or exactly (`wire_handler.h` 47/47, `motion_engine.h` 37/37,
  `radio_transport.h` 20/20, `serial_transport.h` 16/16,
  `protocol.cpp` 14/14, `protocol.h` 5/5, `heading_wrap.h` 5/5,
  `encoder_glitch_armor.h` 9/9, `encoder_pose_source.h` 6/6 all exact),
  with the rest higher by a handful of lines each and `blocks/sim.ts`
  roughly doubled (10 vs 5) -- consistent with ordinary comment edits
  landing across sprints 015-017 between the 2026-08-26 audit and this
  measurement, not a scanning discrepancy. Sanity-checked the test
  itself both ways: confirmed it fails when the budget is set one
  below the measured count (388 vs budget 387), and confirmed it
  passes at 388, before settling on 388 as the committed budget.
- **No cleanup performed**: this ticket added two new test files
  (`test_archaeology_marker_budget.py`) and a guidelines.md section;
  it made no edits to any `src/` comment. `blocks/motion.ts` was not
  touched (its two wrong comments remain for sprint 015, as decided).

## Testing

- **Existing tests to run**: `uv run pytest tests/host/` (full run, since
  the new test reads across all of `src/` and any incidental comment edits
  from concurrent tickets could shift the count).
- **New tests to write**: the archaeology-marker budget test, e.g.
  `tests/host/test_archaeology_marker_budget.py`.
- **Verification command**: `uv run pytest tests/host/test_archaeology_marker_budget.py`.
