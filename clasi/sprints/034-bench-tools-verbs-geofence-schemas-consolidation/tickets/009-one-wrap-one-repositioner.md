---
id: 009
title: One wrap(); one repositioner
status: in-progress
use-cases:
- SUC-002
- SUC-004
depends-on:
- '001'
- '003'
- '007'
github-issue: ''
issue: tools-consolidation-inprocess-aprilcam-wrap-link-layer.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# One wrap(); one repositioner

## Description

**Four `wrap()` implementations survived the sprint-005 consolidation,
and two of them disagree about the boundary.** Verified against the tree
2026-09-06:

| where | form | range |
|---|---|---|
| `tools/field.py` `wrap` | loop | `(-180, 180]` |
| `tools/leg_analysis.py` `_wrap_deg` | `(d + 180) % 360 - 180` | `[-180, 180)` -- **opposite closed end** |
| `tools/linefollow/stage.py` `wrap` | same expression | `[-180, 180)` |
| `tests/calibration/turn_calibration.py` `wrap` | same expression | `[-180, 180)` |

plus the same expression written inline in `tools/linefollow/camlog.py`,
`follow.py`, `sensor_run.py` and `tests/calibration/field_dance.py`.
`tools/park.py` carries a comment explaining why not to add another one.
A disagreement at exactly +/-180 is not academic on this fleet: 180 deg
pivots are in the standard `PIVOTS` list.

**Two repositioning loops, and one of them has the bug the other
documents.** `tour_run.place()` says, in its own comment: *"POSITION
first, then heading, and never the other way round ... a loop that
re-checks both and picks one will answer a good heading with another
goto and undo it. Two runs started facing 98 and 94 degrees instead of
west that way."* `reposition.Repositioner.go()` is **exactly that
loop** -- goto if `derr > tol`, then face if `herr > tol`, repeat.
`tour_practice.py` uses `Repositioner`; `tour_run.py` uses `place()`.

## Acceptance Criteria

- [ ] `field.wrap()` is the one implementation. Every other definition
      and every inline `(d + 180) % 360 - 180` in `tools/` and
      `tests/calibration/` imports it.
- [ ] The boundary convention is **decided and documented on
      `field.wrap()`** -- which end is closed, and what happens at
      exactly +/-180. Changing a caller's boundary behaviour is a real
      behaviour change; if adopting `field.wrap`'s `(-180, 180]` flips a
      result somewhere, say so in the ticket record rather than
      absorbing it silently.
- [ ] `park.py`'s comment explaining why not to add another one is
      updated to point at the single owner (or kept if still accurate).
- [ ] One repositioning loop remains, in `reposition.py`, carrying
      **`place()`'s ordering**: position first, then heading, never a
      re-checking loop that can undo a good heading.
- [ ] The ordering rationale and the "98 and 94 degrees instead of west"
      measurement move with the code -- that citation is the evidence for
      the design and must not be lost (`.claude/rules/measurement-citations.md`).
- [ ] `tour_run.py` uses the surviving `Repositioner`; `place()` is gone.
- [ ] `Repositioner` keeps the `check_path()` refusal ticket 007 gave it.

## Implementation Plan

### Approach

1. `wrap()` first -- it is mechanical and low-risk. Note
   `tools/linefollow/` and `tests/calibration/` both already do a
   `sys.path` insert to reach `tools/`, so the import path exists.
   `otos_levercal.py` uses `atan2(sin, cos)`, which is a different
   formulation of the same thing -- fold it in too, or record why not.
2. Then the repositioner. Move `place()`'s body into
   `Repositioner.go()`, keeping `place()`'s ordering and losing
   `go()`'s. Keep `go()`'s signature if callers depend on it.
3. Check `tour_practice.py` still behaves -- it is the existing
   `Repositioner` caller and its behaviour changes here.

### Files

- `tools/field.py` (the owner -- document the boundary),
  `tools/leg_analysis.py`, `tools/park.py`, `tools/otos_levercal.py`,
  `tools/linefollow/{stage,camlog,follow,sensor_run}.py`,
  `tests/calibration/{turn_calibration,field_dance}.py`.
- `tools/reposition.py`, `tools/tour_run.py`, `tools/tour_practice.py`.
- `tests/tools/test_field.py`, `tests/tools/test_leg_analysis.py`,
  `tests/calibration/test_turn_calibration_gates.py`.

### Re-anchoring

Line numbers in the issue are from 2026-09-02 and predate the
`tests/playfield` -> `tests/calibration` move, so its `field_dance.py`
citations point at a path that no longer exists (`tools/field_dance.py`
is a shim now; the real module is
`tests/calibration/field_dance.py`). Grep for `def wrap`, `def _wrap`,
`% 360 - 180`, `def place`, `class Repositioner`.

### Depends on

Tickets 001 (adds `turn_total()` beside `wrap()` in the same file), 003,
and 007 (adds the `check_path()` refusal this ticket must preserve).

## Testing

- **Existing tests to run**: `uv run pytest tests/tools
  tests/calibration -q` (foreground, scoped).
- **New tests to write**:
  - `wrap()` at the boundaries: exactly +180, exactly -180, 180.0001,
    -180.0001, 540, -540, 0. Assert the documented convention explicitly
    so the next consolidation cannot quietly flip it.
  - A source-level guard that no file under `tools/` or
    `tests/calibration/` defines its own `wrap`/`_wrap_deg` or writes
    the inline expression -- the same shape as ticket 003's guard.
  - `Repositioner.go()`: a synthetic case where the heading is already
    good and the position is not -- assert it does **not** issue a
    heading command that undoes the good heading. This is the "98 and 94
    degrees" regression; name it in the test.
- **Verification command**: `uv run pytest tests/tools tests/calibration -q`
