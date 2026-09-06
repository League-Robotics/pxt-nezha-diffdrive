---
id: '012'
title: tools/DESIGN.md truth pass and the co-located design docs
status: done
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

- [x] Every file under `tools/` -- including `tools/rogo/`,
      `tools/linefollow/` and `tools/field_calibration.json` -- appears
      in `tools/DESIGN.md` with a one-line statement of what it is for.
      The count is whatever the tree says; **re-count, do not plan
      against "11 of 30"**.
- [x] The inventory describes the **post-sprint** tree: no
      `truth_check.py`, `tour_square.py`, `tour_closedloop.py` or
      `camproc.py`; one `Link`, one `Cam`, one `wrap()`, one
      repositioner, one pose-CSV codec.
- [x] `tools/rogo/` is documented as a **deliberate** standalone
      duplicate -- stdlib-only, pipx-installable, must not import from
      `tools/` -- so the next review does not re-file it as a duplicate
      of `tools/link.py`.
- [x] The `tlm.py` cross-reference resolves: either the "Telemetry
      (tlm.py)" section exists or the citation in `tools/tlm.py` points
      somewhere real.
- [x] The `otos_bench.py` "silent no-op" paragraph is **rewritten**, not
      annotated with a third update. Verify against `test/testrig.ts`
      before writing what it says.
- [x] No stale radio address anywhere in the document.
- [x] The status header carries today's date and an accurate status.
- [x] `tests/tools/DESIGN.md` and `tests/host/DESIGN.md` are updated for
      what this sprint changed (deleted test files, the new
      `tests/host/conftest.py`, the new `tests/tools/test_link.py`).
      `tests/calibration/DESIGN.md` is updated if tickets 006 or 009
      changed those programs.
- [x] `docs/design/design.md`'s tools/tests subsystem sections match.
- [x] Apply the review's remaining comment-hygiene replacements that no
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

## Implementation record

**Inventory count: 39 entries** — 38 `*.py` files under `tools/`
(recursively; no `__init__.py` exists) plus `tools/field_calibration.json`.
Built from the tree (`find tools -name '*.py' -not -path '*__pycache__*'`),
not from the review's "11 of 30". Measured against the pre-edit doc
(`git show HEAD:tools/DESIGN.md`, same boundary regex the new guard
uses): it named **26 of 39**. The 13 with no entry were
`blocks_env.py`, `blocks_toolbox.py`, `fieldlink.py`, `park.py`,
`publish_extension.py`, `rogo/rogo.py` and all seven of
`linefollow/*.py`.

**The guard.** `tests/tools/test_tools_design_inventory.py`, modelled on
`tests/host/test_pxt_manifest_completeness.py`: one parametrized case per
file (so a failure names the tool), a reverse check that no inventory row
points at a missing path, and a third test asserting the table regex still
parses at least as many rows as there are files — without it the other two
pass vacuously the moment the table format changes. 41 tests, all green.
`__pycache__` and `__init__.py` are excluded with the reason in the
docstring.

**The `otos_bench.py` paragraph — verified truth.** The old text was
wrong. `test/testrig.ts` registers a `diffDrive.onRunCommand()` catch-all
and parses the number from `name`, not `arg`: a bare `RUN:20` has no
second colon-part, so the dispatcher's split-on-":" puts `"20"` in `name`,
and `rigExec()` dispatches on it (`test/testrig.ts:44-56, 69`). So
`otos_bench.py`'s numeric vocabulary is LIVE. The "stores the argument,
not the name" claim described the pre-fix state; commit 6e7c7fe (sprint
005 ticket 005) fixed the dispatch. Numeric `RUN:<n>` IS a silent no-op
against `test/test.ts`, which registers only named `onRun()` handlers —
two different programs, two different answers, which is why the rewrite is
a table rather than a sentence. The "Sprint 011 update" annotation and the
whole "Campaign tooling (sprint 011)" section were deleted rather than
extended, per `docs/design/design.md`'s "Subsystem-doc contract".

**Comment-hygiene replacements.**

| # | target | outcome |
|---|---|---|
| 4 | `tlm.py` module docstring | **applied**. Replacement text opens the docstring verbatim (reflowed to 72 cols). The sprint-retrofit narrative is gone; the MEASURED line widths, the POSE/FULL column sets, the "zero OTOS column is valid data" hazard and the `ack`/`nack` filtering invariant are kept — `guidelines.md` §6's own standard protects a measured fact or a hazard. The `duty_pct()` cross-reference to the module's separate header comment still resolves. |
| 5 | `camproc.py` module docstring | **no-op** — ticket 008 deleted the file; the review itself offered "or delete with TL-07". |
| 7 | `leg_analysis.py` module docstring | **applied**. Replacement text opens it verbatim; the sprint-008-precedent and sprint-011-issue narrative is gone; the leg-segmentation mechanism, the OTOS frozen-cache guard with its scope limit, and the heading-convention simplification are kept as invariants. |
| 10 | `tour_capture.py` + `tests/tools/test_tour_capture.py` | **applied** verbatim to both. |
| 11 | `make_deploy.py` module docstring | **applied**. Both the triage narrative and its "Sprint 014" continuation collapse to the one-line pointer. One follow-on fix: a "the shape below" reference in the surviving bullet now names `classify_attempt()`, since "below" no longer described anything. |
| 12 | `arc_capture.py` filter comment | **applied** verbatim. |

**Other truth fixes found while verifying.** `tests/DESIGN.md` claimed
`uv run pytest` "runs `host/` and `tools/` and nothing else" — it does not:
`testpaths = ["tests"]` collects `tests/calibration/test_turn_calibration_gates.py`
too (34 tests, confirmed with `--collect-only`). The table now has a
`calibration/` row and the paragraph describes the actual mechanism (the
`test_` prefix). `tools/rogo/DESIGN.md` said it had no host tests;
`tests/tools/test_rogo.py` has pinned its parsers since 2026-09-02.
`tests/tools/DESIGN.md` said "Five files" for a directory of 31.
`fieldlink.py`'s "66-83% per-line delivery" is quoted in the design doc as
**UNVERIFIED** — the docstring names no capture, and the project's own loss
figure for that desk is attributed to WiFi interference at the relay site.

**Docs edited:** `tools/DESIGN.md` (main deliverable), `tools/rogo/DESIGN.md`,
`tests/DESIGN.md`, `tests/tools/DESIGN.md`, `tests/host/DESIGN.md`,
`tests/calibration/DESIGN.md`, `docs/design/design.md`.
`tools/linefollow/DESIGN.md` was re-checked and needed no change.
Overlay copies under `clasi/sprints/034-.../design/` untouched.

**Tests:** `uv run pytest tests/tools -q` → 608 passed;
`tests/host/test_pxt_bound_exclusion_is_current.py` +
`tests/host/test_wire_constants_drift.py` → 46 passed;
`uv run ruff check tools tests` → clean.
