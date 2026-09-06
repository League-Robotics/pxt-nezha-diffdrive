---
id: '002'
title: Per-corner score_corners() window, and a heading-miss leg class
status: open
use-cases:
- SUC-006
depends-on: []
github-issue: ''
issue: analysis-fixes-total-turn-score-corners-leg-analysis.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Per-corner score_corners() window, and a heading-miss leg class

## Description

Two independent analysis defects, both in the verdict a human reads.

**`score_corners()`'s search window spans the whole run** (08-26 C-16,
still open). The inner loop is `for i in range(used, len(rows))` --
every corner searches to the end of the recording. Concretely: a
`RUN:tour:world` run starts on NE, passes NW at t=5 s (4 cm off),
completes the lap, and its closing leg re-approaches NW at t=38 s
(1.5 cm off, because the tour over-closes). NW scores 1.5 cm at index
~760, `used` jumps to the tail, and SW, SE and NE each search a handful
of remaining samples and report tens of centimetres or `None`. **A
single good run reads as three bad corners.** Separately, `used =
besti` (not `besti + 1`) lets two consecutive corners claim the same
sample. The existing test at `test_field.py` covers only the docstring's
claim -- "a later corner cannot reclaim an earlier one's sample" -- not
this, the reverse.

**A heading-only miss is reported as a distance verdict.**
`leg_analysis.py` classifies on the sign of the distance error whenever
the leg is not `ON_TARGET`, so `believed = (100.5 cm, 30 deg)` against
`commanded = (100 cm, 0 deg)` is labelled `STRAIGHT_OVERRUN` with
`distance_error_cm = +0.5` -- a 30 deg heading miss reported as a 5 mm
overrun. The docstring says the two errors are reported separately so
the residual signature stays visible, but the verdict column, the one
the table sorts on, collapses it anyway.

## Acceptance Criteria

- [ ] `score_corners()` searches corner *k* only within a bounded
      window, not to the end of the run.
- [ ] The TL-08 scenario above scores all four corners; no corner is
      starved by an earlier corner's late re-approach.
- [ ] Two consecutive corners cannot claim the same sample
      (`used = besti + 1`).
- [ ] The existing `test_field.py` corner tests still pass -- the
      monotonicity guarantee they pin is preserved, not traded away.
- [ ] `leg_analysis.py` has a `HEADING_MISS` classification for
      "distance within tolerance, heading outside it", and it is used in
      preference to the distance-sign branch.
- [ ] Both errors continue to be reported separately in their own
      columns; the new class changes the verdict, not the data.

## Implementation Plan

### Approach

**score_corners.** The remedy the review names: search corner *k* in
`rows[used : first_approach(k+1)]`, where `first_approach` is the first
index after `used` at which the robot comes within some radius (the
review suggests 15 cm) of the *next* dot. Alternatively solve the four
corners as one monotone assignment. Either is acceptable; pick one,
state the choice and the constant in a comment on the function, and give
the constant a `// [cm]`-style trailing unit note per
`.claude/rules/no-units-in-identifiers.md` -- the name must not carry
the unit.

**HEADING_MISS.** Add the class alongside `ON_TARGET`,
`STRAIGHT_OVERRUN`, `MID_LEG_TRUNCATION`. The branch order becomes:
on-target; else heading out of tolerance and distance within it ->
`HEADING_MISS`; else the existing distance-sign split. Note the
at-rest heading semantics already documented in `leg_analysis.py`
(end-pose heading vs commanded *bearing*) are correct and unchanged.

### Files

- `tools/field.py` -- `score_corners()`.
- `tools/leg_analysis.py` -- the classification block and its class
  constants.
- `tests/tools/test_field.py`, `tests/tools/test_leg_analysis.py`.

### Re-anchoring

Line numbers in the issue are from 2026-09-02 and have moved --
`score_corners` is at `field.py:191` today, not `:123`. Grep for
`def score_corners`, `used = besti`, and the classification constant
names.

## Testing

- **Existing tests to run**: `uv run pytest tests/tools/test_field.py
  tests/tools/test_leg_analysis.py -q` (foreground, scoped).
- **New tests to write**:
  - The TL-08 scenario as a synthetic row list, written out explicitly
    in the test: NE start, NW passed at t=5 s at 4 cm, a full lap, NW
    re-approached at t=38 s at 1.5 cm. Assert all four corners score and
    that none of SW/SE/NE is `None`.
  - Two corners cannot share one sample index.
  - A leg at `(100.5 cm, 30 deg)` against `(100 cm, 0 deg)` classifies
    as `HEADING_MISS`, and its `distance_error_cm` is still `+0.5`.
  - A genuine overrun (distance out of tolerance, heading in) still
    classifies as `STRAIGHT_OVERRUN`.
- **Verification command**: `uv run pytest tests/tools/test_field.py
  tests/tools/test_leg_analysis.py -q`
