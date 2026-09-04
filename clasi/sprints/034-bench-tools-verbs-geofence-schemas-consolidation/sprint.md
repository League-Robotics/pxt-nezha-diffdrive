---
id: '034'
title: 'Bench tools: verbs, geofence, schemas, consolidation'
status: roadmap
branch: sprint/034-bench-tools-verbs-geofence-schemas-consolidation
use-cases: []
issues:
- code-review/tools-v6-verbs-geofence-pose-csv-schema.md
- code-review/analysis-fixes-total-turn-score-corners-leg-analysis.md
- code-review/tools-consolidation-inprocess-aprilcam-wrap-link-layer.md
- code-review/host-harness-gaps.md
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sprint 034: Bench tools: verbs, geofence, schemas, consolidation

## Goals

Drift-test `robotlink.py`'s `_V6_VERBS` table against the firmware's
own verb table so a `MOVE_X` sent through `Link` can no longer be
silently dropped for lacking a sequence id (the table currently names
non-firmware verb spellings and omits `MOVE_X`/`MOVE_V`/`GO_TO_R`
entirely). Wire the existing but zero-caller geofence (`field.py`) into
every tool that commands motion (`tour_run.place()`,
`Repositioner.go()`, `tour_closedloop`), and unify the two different
field sizes currently in play. Collapse the three incompatible pose-CSV
schemas (`tour_capture`/`tour_watch`/`tour_practice`) into one, with a
header line the reader keys on instead of guessing by column count.
Fix the four analysis bugs the review found: `total_turn()`'s inability
to resolve a ±180° pivot that over-rotates, `score_corners()`'s
whole-run search that can starve later corners, a heading-only miss
mislabeled as overrun/truncation, and a printed conclusion still scaled
by the retired `rotationScrub` constant. Consolidate the tools that
have accreted duplicate implementations: import aprilcam in-process
(dropping `camproc.py`'s subprocess-into-a-second-venv, whose premise —
a separate venv requirement — no longer holds), one `wrap()` instead of
four, one link layer instead of four (with three relay addresses and
two sequence-id schemes), one repositioning loop, deletion of dead
tools kept "for reference" but still executable against a stale relay
address, and a `tools/DESIGN.md` truth pass (it currently omits 11 of
30 tools). Close the host-harness gaps the baseline run surfaced: the
`tsc` gate should skip with a reason instead of failing red when
`node_modules` is absent, `run_tour.py`'s travelCalib mirror should be
pinned, ruff should be gated in CI, `motion_lib` compiles should be
session-scoped instead of recompiled eleven times per session, and the
seven `pxt.h`-bound translation units compiled by nothing should either
get a `pxt.h` stub or a documented reason they don't.

## Problem

`tools/robotlink.py:120-123`'s `_V6_VERBS` names `MOVE/PIVOT/GO_TO/ARC`
— not the firmware's actual verb spellings — and omits
`MOVE_X`/`MOVE_V`/`GO_TO_R` outright; a `MOVE_X` sent through `Link`
gets no `#id` attached and is silently dropped by the robot, the exact
failure mode `.claude/rules/mcp-required.md`-adjacent bench rules exist
to prevent (a command that appears sent but never executes). The
geofence from a prior review (08-26 D-08) exists with zero callers;
`tour_run.place()`, `Repositioner.go()`, and `tour_closedloop` all
drive unchecked, and a second, different field size lives hard-coded in
a test file. Three different pose-CSV schemas (mm/centidegree vs
cm/degree) coexist across three capture tools, and `tour_chart.py`
picks a reader by counting columns — a `tour_watch` CSV silently plots
10× too small with no error raised. `total_turn()`'s `round(0.5) = 0`
means a 183° physical pivot reads as −177°, flipping the accuracy
ratio's sign. `score_corners()`'s first-corner search spans the whole
run and can starve every corner after it. A heading-only miss gets
mislabeled by the sign of a sub-tolerance distance error.
`rotation_check.py` still scales its printed conclusion by
`rotationScrub 1.040`, a retired constant. On the consolidation side:
08-26's Q-06/Q-09 findings that justified `camproc.py`'s subprocess
shape are gone now that `aprilcam[daemon]` is a direct dependency of
this venv; four `wrap()` implementations disagree on boundary
semantics; the link layer is written four times with three different
relay addresses and two sequence-id implementations, one of which
documents an ordering bug the other still has; `truth_check.py` is dead
on arrival (v1 JSON keys against a hard-coded port) and duplicates
`pivot_truth.py`; five reference-only tools remain executable against a
stale relay address; `tools/DESIGN.md` is missing over a third of the
tool inventory. On the harness side, the baseline run for this review
was 922 passed / 1 failed, and the failure is an environment
precondition (`tsc` absent) surfacing as a red test rather than a skip.

## Solution

Generate or drift-test `_V6_VERBS` against the firmware's
`kCommandTable` so the two can't silently diverge again. Add one
`check_path()` call to every tool that commands motion, and unify on
one field size (deleting the test file's private copy). Define one
pose-CSV schema with an explicit header line the reader keys on
instead of inferring from column count; migrate the three capture
tools to write it. Fix `total_turn()` to unwrap using the commanded
sign as a prior instead of `round()`'s ambiguity at exactly 180°; give
`score_corners()` a per-corner time or arc-length search window instead
of the whole run; add a heading-miss classification distinct from
overrun/truncation; delete the `rotationScrub` scaling. Import aprilcam
in-process and delete `camlink`/`camproc`'s subprocess shape and the
second `Cam` class; consolidate to one `wrap()` in `field.py`, one
`Link`, one repositioner; delete `truth_check.py` and the five
reference-only tools (git history keeps them if ever needed); rewrite
`tools/DESIGN.md` as a true inventory of what exists. For the harness:
`pytest.skip` with a reason (and install instructions) when `tsc` is
absent; pin the `run_tour.py` travelCalib mirror against its source of
truth; add a `[tool.ruff]` gate to CI; session-scope the `motion_lib`
compile fixture; either compile the seven uncovered translation units
against a `pxt.h` stub or record in `tests/DESIGN.md` why they're
excluded.

## Success Criteria

- A drift test fails if `_V6_VERBS` and the firmware's verb table
  diverge; a `MOVE_X` through `Link` carries a sequence id.
- Every tool that commands motion calls `check_path()` against one
  field size; the test file's private field-size copy is gone.
- One pose-CSV schema with a header line; `tour_chart.py` no longer
  guesses by column count.
- Unit tests on synthetic runs for each analysis fix: `total_turn()`
  resolves a >180° over-rotating pivot correctly; `score_corners()`'s
  window doesn't starve later corners; a heading-only miss is labeled
  distinctly; the retired-constant print is gone.
- `camproc.py`'s subprocess shape and the second `Cam` class are
  deleted; one `wrap()`, one `Link`, one repositioner remain;
  `tools/DESIGN.md` inventories all tools that exist.
- `uv run pytest -q` shows the `tsc` test skipping with a reason (not
  failing) when `node_modules` is absent, and passing when present.

## Scope

### In Scope

- `tools/robotlink.py` verb table and its drift test.
- `tools/field.py`'s geofence wiring into `tour_run.py`,
  `Repositioner`, `tour_closedloop`, and the field-size unification.
- The pose-CSV schema unification across `tour_capture.py`,
  `tour_watch.py`, `tour_practice.py`, `tour_chart.py`.
- `rotation_check.py`, `truth_check.py` (deleted here, not just fixed),
  `field.py`'s `score_corners()`, `leg_analysis.py`.
- The in-process aprilcam consolidation (`camlink.py`, `camproc.py`),
  `wrap()`/`Link`/repositioner consolidation, dead-tool deletion,
  `tools/DESIGN.md`.
- Host harness: `test_typescript_typecheck.py`, `run_tour.py`'s
  travelCalib mirror, ruff CI gate, `motion_lib` fixture scope, the
  seven uncovered translation units.

### Out of Scope

- Everything in sprints A (motion profile — including the two specific
  camlink/robotlink stale-constant fixes already done there as bench-
  acceptance prerequisites; this sprint's `robotlink.py` verb-table
  work and camlink consolidation build on top of that, not instead of
  it), B (bus/fiber safety), C (test program/blocks/simulator), D
  (odometry, config descriptor table, Protocol diet), and F (comment
  work order).
- Any further calibration-constant fixes beyond what's already landed
  in sprint A.

## Related Issues

- [`code-review/tools-v6-verbs-geofence-pose-csv-schema.md`](../../issues/code-review/tools-v6-verbs-geofence-pose-csv-schema.md)
- [`code-review/analysis-fixes-total-turn-score-corners-leg-analysis.md`](../../issues/code-review/analysis-fixes-total-turn-score-corners-leg-analysis.md)
- [`code-review/tools-consolidation-inprocess-aprilcam-wrap-link-layer.md`](../../issues/code-review/tools-consolidation-inprocess-aprilcam-wrap-link-layer.md)
- [`code-review/host-harness-gaps.md`](../../issues/code-review/host-harness-gaps.md)

## Test Strategy

(Describe the overall testing approach for this sprint: what types of tests,
what areas need coverage, any integration or system-level testing needed.)

## Architecture

Not yet written — this sprint is in Roadmap Mode. Architecture (sized
per the effort decision) is produced when this sprint is detail-planned.

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
