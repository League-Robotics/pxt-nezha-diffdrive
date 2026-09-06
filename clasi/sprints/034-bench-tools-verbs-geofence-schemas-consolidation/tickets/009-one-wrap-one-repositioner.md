---
id: 009
title: One wrap(); one repositioner
status: done
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

- [x] `field.wrap()` is the one implementation. Every other definition
      and every inline `(d + 180) % 360 - 180` in `tools/` and
      `tests/calibration/` imports it.
- [x] The boundary convention is **decided and documented on
      `field.wrap()`** -- which end is closed, and what happens at
      exactly +/-180. Changing a caller's boundary behaviour is a real
      behaviour change; if adopting `field.wrap`'s `(-180, 180]` flips a
      result somewhere, say so in the ticket record rather than
      absorbing it silently.
- [x] `park.py`'s comment explaining why not to add another one is
      updated to point at the single owner (or kept if still accurate).
- [x] One repositioning loop remains, in `reposition.py`, carrying
      **`place()`'s ordering**: position first, then heading, never a
      re-checking loop that can undo a good heading.
- [x] The ordering rationale and the "98 and 94 degrees instead of west"
      measurement move with the code -- that citation is the evidence for
      the design and must not be lost (`.claude/rules/measurement-citations.md`).
- [x] `tour_run.py` uses the surviving `Repositioner`; `place()` is gone.
- [x] `Repositioner` keeps the `check_path()` refusal ticket 007 gave it.

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

## Implementation record

### Boundary convention: `(-180, 180]`, upper end CLOSED

`field.wrap()` keeps its existing interval and now documents it on the
function itself: `wrap(180) == +180`, `wrap(-180) == +180` -- exactly
half a revolution reads as a LEFT turn, never a right one; just past
either end flips sign (`wrap(180.0001) == -179.9999`); every multiple of
360 lands on 0.

Chosen deliberately, not inherited. The alternative (the modulo idiom's
`[-180, 180)`) loses to it because `turn_total(commanded, measured)` is
`commanded + wrap(measured - commanded)`, so a commanded +/-180 met by
an exact +/-180 measurement must report the half-turn that was asked
for; `[-180, 180)` reports its mirror for the +180 command. It is also
`math.atan2()`'s own range, which every circular mean in `field.py`
already returns.

**Flipped expectations: none.** No existing test changed. The only
value that differs between the two conventions is exactly +/-180, and
no caller in the tree can reach it from a measurement -- a float
difference of two camera or encoder headings is never exactly 180.0.
It is reachable only from an integer COMMANDED angle, and the three
places that combine a commanded angle with a measurement are
sign-symmetric about it (`field.turn_total()`;
`field_dance.turn()`'s `err = wrap(got - deg)`, where `got` is a float;
`turn_calibration`'s rest-to-rest snap
`wrap(b-a) + 360*round((unw - wrap(b-a))/360)`, where the `round()`
term absorbs a +/-360 shift in the first term). `tests/calibration/
turn_calibration.py`'s gates are unchanged and green.

One doc/code disagreement was found and closed rather than preserved:
`leg_analysis._wrap_deg()`'s docstring **claimed** `(-180, 180]` while
its body returned `[-180, 180)`. Adopting the shared function makes the
code match what that docstring always said.

New pins in `tests/tools/test_field.py`: half a revolution is `+180` at
+/-180, +/-540, +900; `wrap()` never returns `-180`; and
`turn_total(+/-180, +/-180)` keeps the commanded sign.

### `otos_levercal.py`

Folded in. Its `atan2(math.sin(x), math.cos(x))` was a fourth spelling
and it **agreed** with `field.wrap()` exactly (`atan2`'s range IS
`(-pi, pi]`) -- which is precisely why it was converted rather than
left alone: a lookalike costs the next reader a derivation even when it
is correct. It now computes `yaw_deg = wrap(math.degrees(course - h0))`
and derives the radian value from that.

### Retired copies (7 files)

`leg_analysis._wrap_deg` (3 call sites), `linefollow/stage.py::wrap`,
`turn_calibration.py::wrap`, and the inline idiom in
`linefollow/camlog.py`, `linefollow/follow.py`,
`linefollow/sensor_run.py`, `turn_calibration.py` (x2) and
`field_dance.py` (x4). `camlog.py` and `sensor_run.py` gained the
`sys.path` insert to `tools/` the others already had.
`turn_calibration.py` re-exports the shared `wrap` deliberately --
`mount.py` and `distance.py` reach it as `tc.wrap`.

`park.py`'s comment was updated to name the single owner, the
convention, and the new guard.

### One repositioner

`place()` is deleted; `reposition.Repositioner.go()` is the only loop
and now carries `place()`'s two-phase ordering -- position to
completion, THEN heading, never interleaved, so **no `RUN:goto` is ever
sent after a `RUN:face`**. `go()`'s signature, `check_path()`'s refusal
(ahead of the seed) and the class's existing accept-path behaviour are
unchanged; the "98 and 94 degrees instead of west" citation moved into
`go()`'s docstring beside the ordering it justifies, and into the
module docstring.

`tour_run.py` gained `make_repositioner()` (tol_cm 2.5, **tol_deg
1.5** -- the deliberate departure from the class default that its old
call site carried), `START = (50.0, 30.0, 180.0)`, and
`report_start_pose()` for the console line `place()` used to print.

Two behaviours of `place()` were NOT carried over, both deliberately:
its `link.send_until()` retransmits (the class uses `send()` +
`_wait()` on the robot's own `GOTO:end`/`FACE:end` markers, which is
what `tour_practice` has always run on) and its `time.sleep(0.7)`
settle after each move (`fix()` medians 8 fresh camera samples, ~2 s at
the camera's ~4 Hz, entirely after the end marker -- a strictly longer
settle than the sleep it replaces).

### Tests

- `tests/tools/test_angle_wrap_ownership.py` (new): source-level guard
  -- no private `wrap`/`_wrap_deg` and no inline idiom under `tools/`
  or `tests/calibration/`; every converted file really imports the
  shared one (checked with `ast`, since several use the parenthesised
  multi-line import form and several open a daemon/serial connection at
  module scope so cannot be imported); `field.wrap()` documents its
  interval and its +/-180 result. The owner and the guard are the only
  files allowed to name the retired idiom in prose.
  `tests/host/`'s radians-domain `_wrap_to_pi` is out of scope by
  design -- a different function against the C++ kernel's convention.
- `tests/tools/test_reposition.py`: two new ordering tests naming the
  98/94 case -- a good heading is never re-commanded, and no `goto`
  follows a `face`. **Verified discriminating**: replaying the
  pre-merge interleaved loop against the same fake camera issues
  `seedxy, goto, seedxy, face, seedxy, face, seedxy, goto, seedxy` --
  a goto after the pivot, which is the defect.
- `tests/tools/test_tour_run_geofence.py`: retargeted, no assertion
  dropped. The refusal/ordering assertions now live on the surviving
  loop in `test_reposition.py`; this file keeps the `tour_run` half --
  `place()` is gone rather than renamed, `tour_run.Repositioner` **is**
  `reposition.Repositioner` (a copied loop passes a name check and
  fails this), the geofence still holds through `tour_run`'s own
  repositioner, its 1.5 deg tolerance survived, and
  `report_start_pose()` still flags a bad staging.

Verification: `uv run pytest tests/tools tests/calibration -q` ->
**597 passed**. `ruff check` clean on every touched file (two
pre-existing `F401`s remain in untouched test files).
