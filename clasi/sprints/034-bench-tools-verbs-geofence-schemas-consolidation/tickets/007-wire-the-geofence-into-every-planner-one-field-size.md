---
id: '007'
title: Wire the geofence into every planner; one field size
status: in-progress
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

- [ ] `Repositioner.go()` refuses a target whose projected path fails
      `check_path([current, target])`, naming the offending waypoints.
- [ ] `tour_run.place()` does the same.
- [ ] Every surviving tool that commands motion to a coordinate calls it.
      Enumerate them yourself against the tree you find -- ticket 003 has
      deleted `tour_square.py` and `tour_closedloop.py` by now, so the
      issue's list is out of date.
- [ ] The recorders (`tour_run`, `tour_watch`) print `clears_margin()`
      on the camera rows they already hold, in their score line.
- [ ] `field.py` exposes the usable half-extent as a **derived** value
      (`LIMITS` minus `MARGIN`), not a second hand-typed pair.
- [ ] `tests/host/test_run_tour_programs.py` imports it;
      `_FIELD_MM` and `_MARGIN_MM` are gone.
- [ ] **`field.py` still imports nothing that does I/O.** No `socket`,
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
