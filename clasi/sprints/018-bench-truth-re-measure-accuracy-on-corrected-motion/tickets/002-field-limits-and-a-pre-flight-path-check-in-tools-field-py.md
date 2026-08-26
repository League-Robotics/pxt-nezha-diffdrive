---
id: '002'
title: Field limits and a pre-flight path check in tools/field.py
status: open
use-cases:
- SUC-002
depends-on: []
github-issue: ''
issue: geofence-described-in-rules-does-not-exist.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Field limits and a pre-flight path check in tools/field.py

## Description

`.claude/rules/playfield-testing.md` states field limits of
**+/-67.15 / +/-44.65 cm** (134.3 x 89.3 cm field, AprilTag-1-centred)
with a **12 cm margin**, and says "the geofence is what catches
*unexpected* drift on top of [the pre-flight path check] -- it is not
the primary check." A repo-wide search for `geofence`, `67.15`,
`44.65`, `134.3`, `89.3` across `*.py`, `*.ts`, `*.cpp`, `*.h`, `*.md`
finds those numbers **only in that rule file**. `tools/field.py` owns
all playfield geometry this project has (`DOTS`, `ORDER`, `RECT`,
`score_corners()`, `path_deviation()`, `closure()`) and is imported by
every tour/ground-truth tool, but has no boundary and no margin. The
rule describes a safety net that does not exist anywhere in the code.

`block-go-to-misses-its-target.md` documents exactly the "unexpected
drift" case the rule claims is covered: a command that drives 3 m to
reach a point 10 cm away.

## What to change -- pick one, deliberately (per the issue's own framing)

**Preferred: build it.** `tools/field.py` gains:

- `LIMITS = (67.15, 44.65)` -- `(x_cm, y_cm)` half-extents, matching
  the rule's numbers exactly, with a comment citing
  `.claude/rules/playfield-testing.md` as the source of truth.
- `MARGIN = 12.0` -- cm.
- `clears_margin(rows)` -- given `field.py`'s existing timestamped
  `(t, x_cm, y_cm, yaw_deg)` row convention (same shape
  `score_corners()`/`path_deviation()`/`closure()` already take),
  reports whether every row's `(x, y)` stays within `LIMITS` reduced
  by `MARGIN`. For **recorders** -- flags a capture that came within
  the margin of the boundary, after the fact.
- `check_path(waypoints)` -- given a list of `(x_cm, y_cm)` waypoints,
  checks the FULL projected path (each waypoint, and the straight-line
  segment between each consecutive pair -- not just the waypoints
  themselves) stays within `LIMITS` reduced by `MARGIN`. For
  **planners** -- called before a run is armed, so a leg that clips
  outside the margin between two otherwise-safe waypoints is still
  caught. This is the sharper case: the rule itself says "compute the
  full projected path ... through every planned leg," not "check each
  corner."
- Return shape (bool, or a list of offending points/segments) is an
  implementation choice -- but a caller must be able to act on it by
  refusing to arm the run, per `sprint.md`'s SUC-002 acceptance
  ("a projected path that would breach the margin is refused before
  the run is armed").

**Alternative: correct the rule.** If, on inspection, wiring a real
geofence turns out not to be worth it right now, edit
`.claude/rules/playfield-testing.md` so it says the pre-flight path
check is the ONLY guard, removing the "the geofence is what catches
unexpected drift" claim. This is an acceptable resolution per the
issue, but note it does not, by itself, satisfy `sprint.md`'s SUC-002
success criterion (which wants an actual pre-arm refusal capability)
-- if this path is taken, say so explicitly in the ticket's completion
notes so the gap between "issue closed" and "SUC-002 satisfied" is
visible rather than silently absorbed.

Wiring `check_path()`/`clears_margin()` into any specific tour tool's
call path (e.g. `tour_capture.py`) is OUT OF SCOPE for this ticket --
the issue's own ask is `tools/field.py` gaining the capability, not
every caller adopting it yet. Note it as a natural follow-up in
completion notes.

## Acceptance Criteria

- [ ] `tools/field.py` defines `LIMITS = (67.15, 44.65)` and
      `MARGIN = 12.0`, matching `.claude/rules/playfield-testing.md`'s
      stated numbers, with a comment citing that rule file.
- [ ] `clears_margin(rows)` is implemented, pure (no I/O), and follows
      the module's existing `(t, x, y, yaw)` row convention.
- [ ] `check_path(waypoints)` is implemented, pure, checks waypoints
      AND the segments between them (not just endpoints), and its
      return value lets a caller refuse to arm a run.
- [ ] Unit tests added to `tests/tools/test_field.py` (co-located with
      the existing `field.py` tests) covering at minimum: a path fully
      inside the margin passes; a single waypoint outside
      `LIMITS - MARGIN` fails; a straight-line segment between two
      in-bounds waypoints that clips outside the margin is caught (the
      segment case, not just the endpoint case); the equivalent
      cases for `clears_margin(rows)` against recorded rows.
- [ ] `LIMITS`/`MARGIN` numbers are unit-tested against the exact
      values in `.claude/rules/playfield-testing.md` (a drift guard --
      if the rule's numbers ever change, this test should force the
      module to be updated too, or vice versa).
- [ ] OR, if the "correct the rule" alternative is taken instead: the
      rule file is edited to remove the false "geofence" claim, and
      the ticket's completion notes state explicitly that SUC-002 is
      not satisfied by this path and why that was judged acceptable.

## Testing

- **Existing tests to run**: `uv run pytest tests/tools/test_field.py`
  -- confirm no regression to `wrap()`/`score_corners()`/
  `path_deviation()`/`closure()`.
- **New tests to write**: `tests/tools/test_field.py` gains coverage
  for `LIMITS`, `MARGIN`, `clears_margin()`, `check_path()` per the
  acceptance criteria above.
- **Verification command**: `uv run pytest tests/tools/test_field.py`.
