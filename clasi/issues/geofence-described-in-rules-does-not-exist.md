---
status: pending
sprint: 018
---

# The geofence the operating rules rely on does not exist anywhere in the code

Priority: **Medium** -- a safety control the operating procedure believes it
has.

`.claude/rules/playfield-testing.md` states:

> Field is **134.3 x 89.3 cm**, AprilTag-1-centred, so limits are
> **+/-67.15 / +/-44.65 cm**. Keep a **12 cm margin**.
>
> Before sending ANY commanded motion, compute the full projected path from a
> **measured** start pose ... and confirm every waypoint clears the margin.
> **The geofence is what catches *unexpected* drift on top of that** -- it is
> not the primary check.

A repo-wide search for `geofence`, `67.15`, `44.65`, `134.3`, `89.3` across
`*.py`, `*.ts`, `*.cpp`, `*.h`, `*.md` returns hits **only in that rule file**
(and its worktree copies).

`tools/field.py` owns playfield geometry -- `DOTS`, `ORDER`, `RECT`,
`score_corners()`, `path_deviation()`, `closure()` -- and is imported by every
tour and ground-truth tool. It has no field boundary and no margin.

So the sentence describes a safety net that is not there.

## What to change -- pick one, deliberately

- **Build it.** `tools/field.py` is the obvious home: `LIMITS = (67.15, 44.65)`,
  `MARGIN = 12.0`, a `clears_margin(rows)` the recorders call, and a
  `check_path(waypoints)` the planners call before arming a run.
- **Or correct the rule** to say the pre-flight path check is the *only* guard,
  so nobody plans a run believing a second one is watching.

Either is fine. Leaving the sentence as-is is not --
`block-go-to-misses-its-target.md` documents a command that drives 3 m to reach
a point 10 cm away, which is exactly the "unexpected drift" case the rule says
is covered.
