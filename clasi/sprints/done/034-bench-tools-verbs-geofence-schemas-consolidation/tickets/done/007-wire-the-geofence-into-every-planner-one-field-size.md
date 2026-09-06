---
id: '007'
title: Wire the geofence into every planner; one field size
status: done
use-cases:
- SUC-002
depends-on:
- '003'
github-issue: ''
issue: tools-v6-verbs-geofence-pose-csv-schema.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Wire the geofence into every planner; one field size

## Description

Sprint 018 ticket 002 added the geofence -- `LIMITS = (67.15, 44.65)`,
`MARGIN = 12.0`, `clears_margin(rows)` and `check_path(waypoints)` --
and `tests/tools/test_field.py` pins it, including the good part:
`check_path()` walks the *segments*, not just the endpoints. And
`grep -rn 'check_path\|clears_margin' tools tests` returns
**`field.py` and `test_field.py` only**. Zero callers. The planners the
rule file addresses still drive unchecked:
`tour_run.place()` (`RUN:goto`), `reposition.Repositioner.go()`
(`RUN:goto:{x}:{y}` to any caller-supplied point), and whatever survives
ticket 003. The recorders never call `clears_margin()` on the camera rows
they already hold.

`.claude/rules/playfield-testing.md` is explicit that this check is
mandatory and that the geofence is *not* the primary defence: "Before
sending ANY commanded motion, compute the full projected path from a
**measured** start pose (a camera fix, never an assumption) through
every planned leg and turn, and confirm every waypoint clears the
margin." Driving off the playfield is a failure, not a synonym for
driving.

**Two field sizes are both "enforced".**
`tests/host/test_run_tour_programs.py` carries `_FIELD_MM = (600.0,
400.0)` and `_MARGIN_MM = 50.0` with the comment "per the stakeholder
2026-09-01: 120 x 80 cm ... Both numbers live here too because this test
is what enforces them", against `field.py`'s 134.3 x 89.3 cm / 12 cm
margin, which is pinned to the rule file.

They are not the same field, and the difference is not symmetric.
Usable half-extents:

| source | x | y |
|---|---|---|
| `test_run_tour_programs.py` (`_FIELD_MM - _MARGIN_MM`) | 55.0 cm | **35.0 cm** |
| `field.py` (`LIMITS - MARGIN`) | 55.15 cm | **32.65 cm** |

x agrees to 1.5 mm. **y is 2.35 cm tighter under `field.py`.** So
unifying can fail a `.tour` figure that passes today.

## Acceptance Criteria

- [x] `Repositioner.go()` refuses a target whose projected path fails
      `check_path([current, target])`, naming the offending waypoints.
- [x] `tour_run.place()` does the same.
- [x] Every surviving tool that commands motion to a coordinate calls it.
      Enumerate them yourself against the tree you find -- ticket 003 has
      deleted `tour_square.py` and `tour_closedloop.py` by now, so the
      issue's list is out of date.
- [x] The recorders (`tour_run`, `tour_watch`) print `clears_margin()`
      on the camera rows they already hold, in their score line.
- [x] `field.py` exposes the usable half-extent as a **derived** value
      (`LIMITS` minus `MARGIN`), not a second hand-typed pair.
- [x] `tests/host/test_run_tour_programs.py` imports it;
      `_FIELD_MM` and `_MARGIN_MM` are gone.
- [x] **`field.py` still imports nothing that does I/O.** No `socket`,
      no `pyserial`, no `aprilcam`. This is the invariant that lets
      `tests/calibration/*` and `tests/host/*` both import it on a
      machine with no robot attached. Wire the geofence by having the
      *planners* call `field.check_path()` -- never by teaching
      `field.py` about a link.

## Implementation Plan

### Approach

1. Add the derived usable-extent accessor to `field.py`.
2. Point `test_run_tour_programs.py` at it and **run that file**.
3. Wire `check_path()` into the planners. A refusal must be loud and
   name the points; a silent clamp would be worse than no check.
4. Add `clears_margin()` to the recorders' score line.

### Open Question 1 -- the decision rule, stated in advance

If a `.tour` figure now fails the tighter y limit, **that is a finding
about the tour, not a reason to loosen the margin.**

- Exactly one tour fails -> re-size it, or add it to `_UNSIZED` **with a
  written reason** in the same comment block that explains the existing
  entries. Record which, and why, in the ticket.
- More than one fails -> **stop and throw a ticket exception**
  (`throw_ticket_exception`, `thrown_by="programmer"`,
  `surface="user-visible"` -- it touches behaviour described in the
  sprint's Use Cases). More than one failure would mean the 120 x 80 cm
  envelope was not conservative, and the stakeholder's 2026-09-01
  direction needs revisiting. That is not a programmer's call.
- **Never** change `field.py`'s `LIMITS` or `MARGIN` to make a tour fit.
  Those are measured facts about the room, cited to
  `.claude/rules/playfield-testing.md`.

### Files

- `tools/field.py` -- the derived accessor.
- `tools/reposition.py`, `tools/tour_run.py`, `tools/tour_watch.py`, and
  whatever else the enumeration turns up.
- `tests/host/test_run_tour_programs.py` -- import, delete the private
  pair.
- `tests/tools/test_field.py`, `tests/tools/test_park.py` (park.py is
  pure geometry over the same field -- check it does not carry a third
  copy).

### Re-anchoring

The private field size is at `test_run_tour_programs.py:247-248` today,
**not** the `:171-172` the issue cites. Grep for `_FIELD_MM`,
`check_path`, `clears_margin`, `RUN:goto`.

### Depends on

Ticket 003.

## Testing

- **Existing tests to run**: `uv run pytest tests/tools/test_field.py
  tests/host/test_run_tour_programs.py tests/tools/test_park.py -q`
  (foreground, scoped). **Run `test_run_tour_programs.py` early** -- it
  is where Open Question 1 resolves.
- **New tests to write**: `Repositioner.go()` with an injected fake link
  refuses an out-of-bounds target and **sends nothing** (assert on the
  fake's sent lines, not just on the return value); it accepts an
  in-bounds one; a target inside the limits whose *path* leaves them is
  refused, exercising the segment walk `check_path` already does.
- **Verification command**: `uv run pytest tests/tools/test_field.py
  tests/host/test_run_tour_programs.py -q`

## Implementation record

### Open Question 1 -- outcome: NO tour failed the tighter y limit

`tests/host/test_run_tour_programs.py` now derives its limits from
`field.usable_half_extent()` (55.15 x 32.65 cm = 551.5 x 326.5 mm half-
extent, vs the deleted private pair's 550.0 x 350.0). Every sized
`.tour` and every referenced spline path still fits; nothing was
re-sized and nothing was added to `_UNSIZED`. `LIMITS` and `MARGIN`
were not touched.

The "either orientation" allowance is what carries it -- the tall
figures are staged across the field's long axis, where the y limit
never applies to their long dimension:

| tour | half-extent [mm] | under 550/350 | under 551.5/326.5 |
|---|---|---|---|
| circle | 300.0 x 300.0 | fits | fits |
| diamond | 318.2 x 318.2 | fits | fits |
| infinity | 250.0 x 500.0 | fits | fits (rotated) |
| snake | 125.0 x 500.0 | fits | fits (rotated) |
| square | 300.0 x 300.0 | fits | fits |
| spline -> complex.path.json | 360.9 x 262.8 | fits | fits |

(`square_cw`, `square_smooth`, `complex_spline`, `tag_spline` and
`fault_wedge` remain in `_UNSIZED`, unchanged; their extents were
checked anyway and all clear the tighter limit too.) So the exception
path was not needed: no `_UNSIZED` addition, no re-size, no exception
thrown.

### Which tools now call the gate

`field.require_clear_path(waypoints, what=...)` wraps `check_path()`
and raises `field.PathRefused` naming the refused move, the offending
points and the usable extent. It refuses; it never clamps.

- `tools/reposition.py` -- `Repositioner.check_path()`, called from
  `go()` BEFORE the seed (ticket 009 merges `place()` into this class
  and inherits the method).
- `tools/tour_run.py` -- `place()`, same helper; `main()` catches
  `PathRefused` and abandons the run instead of tracebacking.
- `tools/tour_practice.py` -- inherits it via `Repositioner.go()`;
  catches, prints, skips the run.
- `tests/calibration/turn_calibration.py` -- already called
  `check_path()` directly at seven sites; left as is.

Enumerated against the tree (post-ticket-003) and NOT wired, because
they command only RELATIVE motion with no coordinate to check:
`pivot_truth.py`, `turn_sweep.py`, `rotation_check.py`,
`arc_capture.py`, `tour_capture.py`, `otos_levercal.py`,
`otos_bench.py` (drum rig, not the robot), `tools/linefollow/*`,
`tests/calibration/{distance,mount,lag_measure,field_dance}.py`.
`tools/park.py` sends nothing (pure planner) and carries no field-size
copy of its own.

### Recorders

`tour_run.py` and `tour_watch.py` both print `clears_margin()` on the
camera rows they already hold, in their score line, with the usable
extent: `geofence: clear|LEFT THE MARGIN (usable +/-55.15 x +/-32.65 cm)`.

### Tests

- `tests/tools/test_field.py` -- `usable_half_extent()` is derived and
  agrees with `clears_margin()` on both axes; `require_clear_path()`
  names the move/points/extent, catches a legal TARGET reached by an
  illegal PATH (an out-of-margin start), walks multi-leg routes, never
  rewrites the caller's waypoints; a drift guard fails if the tour
  sizing test regrows a private field size; a source test asserts
  `tools/field.py` imports nothing but `math`.
- `tests/tools/test_reposition.py` (new) and
  `tests/tools/test_tour_run_geofence.py` (new) -- injected fake link
  and camera; every refusal case asserts `link.sent == []`, one test
  pins that the refusal precedes `RUN:seedxy`, and both accept paths
  (the NE staging dot) still drive.

Verification: `uv run pytest tests/tools/test_field.py
tests/host/test_run_tour_programs.py -q` -> 83 passed;
`uv run pytest tests/tools tests/host/test_run_tour_programs.py -q` ->
534 passed; `uv run pytest tests/calibration -q` -> 32 passed. Ruff
clean on every touched file. No version bump.
