---
id: '001'
title: One commanded-anchored turn_total(), and delete the retired rotationScrub print
status: open
use-cases: [SUC-006]
depends-on: []
github-issue: ''
issue: analysis-fixes-total-turn-score-corners-leg-analysis.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# One commanded-anchored turn_total(), and delete the retired rotationScrub print

## Description

`total_turn()` cannot resolve a +/-180 deg pivot that over-rotates.
The expression is `revs = round(commanded / 360.0)` then
`revs * 360 + wrap(after - before - revs * 360)`. For `commanded =
+/-180`, `round(+/-0.5)` is **0** under banker's rounding, so the whole
thing collapses to `wrap(after - before)`. A physical 183 deg pivot --
over-rotation is the measured norm on this fleet -- reads **-177 deg**,
and `ratio = gyro / commanded` comes out **-0.98**: the sign flips, and
the printed "mean gyro/commanded" over `PIVOTS = [360, 180, -180]` mixes
sign-flipped terms into an average that means nothing.

The fix is one line and correct for *every* commanded angle, with no
`revs` at all:

    turn = commanded + wrap(delta - commanded)

i.e. anchor the unwrap on the commanded angle instead of asking
`round()` to guess the revolution count. It belongs in `field.py`
beside `wrap()`, which is already the one owner of angle math with no
I/O.

Two smaller defects ride along in the same files:

- `pivot_truth.py` divides `gyro / camdeg`. When the camera saw no
  rotation that is a `ZeroDivisionError` -- and "the camera saw no
  rotation" is precisely the *robot is switched off* case that
  `.claude/rules/playfield-testing.md` says to check first. It must
  report that case, not crash on it.
- `rotation_check.py` prints a conclusion scaled by `rotationScrub
  1.040`, a constant its own module docstring says was retired in
  favour of `rotationalSlip 0.952`. Delete the line.

## Acceptance Criteria

- [ ] `field.turn_total(commanded_deg, delta_deg)` exists beside
      `wrap()`, is documented with the failure it replaces, and does not
      use `round()` or a `revs` term.
- [ ] `rotation_check.py` and `pivot_truth.py` both call it; neither
      keeps a private copy of the arithmetic.
- [ ] A 183 deg physical turn against a 180 deg command reports
      **+183**, not -177. Same for -183 against -180.
- [ ] `pivot_truth.py` reports "camera saw no rotation" (naming the
      robot-is-off check) instead of raising `ZeroDivisionError`.
- [ ] The `rotationScrub 1.040` print is gone from `rotation_check.py`.
- [ ] `tools/truth_check.py` is **not touched** -- ticket 003 deletes it.

## Implementation Plan

### Approach

1. Add `turn_total()` to `tools/field.py` immediately after `wrap()`.
   Signature takes the commanded angle and the measured delta (or
   before/after -- your call, but keep it one obvious call shape) and
   returns the unwrapped physical turn in degrees.
2. Retarget `rotation_check.py`'s `total_turn()` onto it; delete the
   local implementation rather than leaving a wrapper.
3. Retarget `pivot_truth.py`. Note it already special-cases
   `abs(commanded) == 180.0` by choosing the +/-360 branch nearest the
   camera -- that special case becomes unnecessary and should go, since
   `turn_total()` handles every angle uniformly.
4. Guard the `gyro / camdeg` division.
5. Delete the `rotationScrub` print.

### Files

- `tools/field.py` -- add `turn_total()`.
- `tools/rotation_check.py` -- use it; delete the local `total_turn()`,
  the `revs` arithmetic, and the retired-constant print.
- `tools/pivot_truth.py` -- use it; delete the `abs(commanded) == 180`
  special case; guard the zero-rotation division.
- `tests/tools/test_field.py` -- new cases.
- `tests/tools/test_run_verbs.py` -- it already imports `rotation_check`
  and `pivot_truth`; add the source-level assertions there rather than
  creating a new file.

### Re-anchoring

**The line numbers in the issue are from 2026-09-02 and several have
already moved.** Re-anchor by content: grep for `def total_turn`,
`revs`, `rotationScrub`, `camdeg`. Do not `sed -n` on the cited ranges.

## Testing

- **Existing tests to run**: `uv run pytest tests/tools/test_field.py
  tests/tools/test_run_verbs.py -q` (foreground, scoped -- the full
  suite runs once inside `close_sprint`, not per ticket).
- **New tests to write**:
  - `turn_total`: 183 against 180 -> +183; -183 against -180 -> -183;
    177 against 180 -> +177 (under-rotation still works); 363 against
    360 -> +363; 0.5 and exactly 180 as boundary cases; a commanded 0
    with a small measured drift.
  - A regression case named for the defect: assert the *sign* of
    `turn / commanded` is positive for an over-rotating 180 deg pivot.
  - `pivot_truth`: a synthetic run where the camera delta is 0 produces
    a reported result, not an exception.
  - A source-level assertion that `rotationScrub` appears nowhere in
    `tools/rotation_check.py`.
- **Verification command**: `uv run pytest tests/tools/test_field.py
  tests/tools/test_run_verbs.py -q`
