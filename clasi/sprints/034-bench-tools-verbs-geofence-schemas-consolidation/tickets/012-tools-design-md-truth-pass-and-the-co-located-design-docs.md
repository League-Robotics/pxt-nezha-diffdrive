---
id: '012'
title: tools/DESIGN.md truth pass and the co-located design docs
status: in-progress
use-cases:
- SUC-004
depends-on:
- '004'
- '005'
- '006'
- '007'
- 008
- 009
- '010'
- '011'
github-issue: ''
issue: tools-consolidation-inprocess-aprilcam-wrap-link-layer.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# tools/DESIGN.md truth pass and the co-located design docs

## Description

`tools/DESIGN.md` is a sprint log, not an inventory, and it must
describe the tree this sprint leaves behind.

What the review found (2026-09-02), **all of which must be re-checked
against the current tree rather than taken as given**:

- No entry for a third of the tools. As of 2026-09-06 the tree also
  contains `tools/gen_config_field_enum.py`, `tools/wifilink.py`,
  `tools/rogo/` and `tools/linefollow/`, none of which existed when the
  review's "11 of 30" count was taken, and `tests/playfield/` -- which
  the document may still reference -- no longer exists.
- `tools/tlm.py` cites "tools/DESIGN.md's 'Telemetry (tlm.py)' section".
  **No such heading exists.** Either add the section or fix the citation.
- "Known limitation -- the telemetry gap" says `otos_bench.py`'s numeric
  `RUN:<n>` is "a silent no-op" because `testrig.ts` "stores the
  argument, not the name". `test/testrig.ts` parses the number **from
  `name`** and dispatches on it -- the console works. The paragraph then
  declares itself stale in a "Sprint 011 update" without being rewritten.
- The link-layer paragraph still says "channel 4, group 10 -- vevov's
  assignment". vevov is on **37/43** and `robotlink.radio_address()`
  derives it from the name.
- Status header says "Last reviewed 2026-08-24".

## Acceptance Criteria

- [ ] Every file under `tools/` -- including `tools/rogo/`,
      `tools/linefollow/` and `tools/field_calibration.json` -- appears
      in `tools/DESIGN.md` with a one-line statement of what it is for.
      The count is whatever the tree says; **re-count, do not plan
      against "11 of 30"**.
- [ ] The inventory describes the **post-sprint** tree: no
      `truth_check.py`, `tour_square.py`, `tour_closedloop.py` or
      `camproc.py`; one `Link`, one `Cam`, one `wrap()`, one
      repositioner, one pose-CSV codec.
- [ ] `tools/rogo/` is documented as a **deliberate** standalone
      duplicate -- stdlib-only, pipx-installable, must not import from
      `tools/` -- so the next review does not re-file it as a duplicate
      of `tools/link.py`.
- [ ] The `tlm.py` cross-reference resolves: either the "Telemetry
      (tlm.py)" section exists or the citation in `tools/tlm.py` points
      somewhere real.
- [ ] The `otos_bench.py` "silent no-op" paragraph is **rewritten**, not
      annotated with a third update. Verify against `test/testrig.ts`
      before writing what it says.
- [ ] No stale radio address anywhere in the document.
- [ ] The status header carries today's date and an accurate status.
- [ ] `tests/tools/DESIGN.md` and `tests/host/DESIGN.md` are updated for
      what this sprint changed (deleted test files, the new
      `tests/host/conftest.py`, the new `tests/tools/test_link.py`).
      `tests/calibration/DESIGN.md` is updated if tickets 006 or 009
      changed those programs.
- [ ] `docs/design/design.md`'s tools/tests subsystem sections match.
- [ ] Apply the review's remaining comment-hygiene replacements that no
      earlier ticket claimed: #4 (`tlm.py` module docstring), #5 (moot
      if `camproc.py` is deleted -- confirm), #7 (`leg_analysis.py`
      module docstring), #10 (`tour_capture.py` and
      `test_tour_capture.py`), #11 (`make_deploy.py` module docstring),
      #12 (`arc_capture.py`). Each replacement text is supplied verbatim
      in `docs/code-review/2026-09-02/raw/tools-and-tests.md`.

## Implementation Plan

### Approach

1. `ls tools tools/*/` and build the inventory from the tree.
2. Read each tool's module docstring for its one-line purpose. Where the
   docstring and the code disagree, **the code wins** and the docstring
   is fixed here.
3. Rewrite rather than annotate. A "Sprint NNN update" appended beneath a
   stale paragraph is how this document got into its current state.
4. Verify each factual claim before writing it. This document's whole
   defect is claims nothing checked --
   `.claude/rules/measurement-citations.md` applies to design docs as
   much as to code comments: if you assert measured behaviour, name the
   artifact; if you did not run it, write UNVERIFIED.

### Design-doc handling

`tools/DESIGN.md`, `tools/rogo/DESIGN.md`, `tests/host/DESIGN.md`,
`tests/tools/DESIGN.md`, `tests/calibration/DESIGN.md` and
`docs/design/design.md` are seeded into this sprint's design overlay.
**Edit the canonical files** (the ones under `tools/` and `tests/`), not
the overlay copies -- the team-lead syncs the overlay at close.
`tests/DESIGN.md` is **not** in the overlay (a slug collision with
`tools/DESIGN.md`); ticket 011 edits it canonically and the team-lead
syncs it by hand.

### Files

`tools/DESIGN.md`, `tools/rogo/DESIGN.md`, `tests/tools/DESIGN.md`,
`tests/host/DESIGN.md`, `tests/calibration/DESIGN.md`,
`docs/design/design.md`, plus the module docstrings named above.

### Depends on

Tickets 004, 005, 006, 007, 008, 009, 010 and 011 -- this describes the
state they leave.

## Testing

- **Existing tests to run**: `uv run pytest tests/tools -q` (foreground,
  scoped) -- docstring edits can break source-pinning tests.
- **New tests to write**: an inventory-completeness guard, in the shape
  of `tests/host/test_pxt_manifest_completeness.py`: every `*.py` under
  `tools/` (and every subdirectory) is named somewhere in
  `tools/DESIGN.md`, so a tool added without a doc entry fails here. That
  guard is what stops this document decaying again -- it is the most
  valuable line of this ticket.
- **Verification command**: `uv run pytest tests/tools -q`
