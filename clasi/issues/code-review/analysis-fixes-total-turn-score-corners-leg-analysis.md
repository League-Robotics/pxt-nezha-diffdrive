---
status: pending
sprint: '033'
---

# Analysis fixes: total_turn +/-180 wrap, score_corners window, heading-only miss label, retired-constant print

Priority: **Medium** · Source: [code review 2026-09-02](../../../docs/code-review/2026-09-02/review.md)

Findings: TL-03, TL-08, TL-10, TL-25 ([tools-and-tests](../../../docs/code-review/2026-09-02/raw/tools-and-tests.md)). Triage #21.

## Description

- `rotation_check.py:108-109`, `truth_check.py:120-124`: `total_turn()`
  cannot resolve a +/-180 deg pivot that over-rotates (`round(0.5) = 0`),
  so 183 deg physical reads -177 and the ratio flips sign.
- `field.py:123-135`: 08-26 C-16 still open; the first corner's search
  covers the whole run and can starve every later corner.
- `leg_analysis.py:237-243` labels a heading-only miss as overrun/truncation
  by the sign of a sub-tolerance distance error.
- `rotation_check.py:122-123` prints a conclusion scaled by the retired
  `rotationScrub 1.040`.

## Remedy

Unwrap with the commanded sign as the prior; a per-corner time or
arc-length window; a heading-miss class; delete the retired constant.
Each with a unit test on a synthetic run.
