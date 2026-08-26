---
status: done
sprint: '015'
tickets:
- 015-001
- 015-002
---

# The student `go to` block drives to the wrong place -- measured 112 mm off a 141 mm hop

Priority: **Critical** -- it is a student-facing block, the error is large and
systematic, it is the same defect the 2026-08-23 review reported and sprint 006
fixed on only one of the four paths that carry it, and no test can see it.

## Measured

Real `MotionEngine` + real kernel + ideal wheels, via
[`docs/code-review/2026-08-26/raw/goto_probe.cpp`](docs/code-review/2026-08-26/raw/goto_probe.cpp):

```
blocks/motion.ts startGoTo(10,10) -> startMove(s=15.708 cm, theta=90.000 deg)
  block `go to`  : ends at (3.0, 156.9) mm, heading 89.1 deg   -> MISS 112.5 mm on a 141.4 mm hop
  wire GO_TO_R   : ends at (101.5, 97.5) mm, heading 43.8 deg  -> miss 2.9 mm

blocks/motion.ts startGoTo(-10,1) -> startMove(s=307.2 cm, theta=348.6 deg)  [target is 10.0 cm away]
  block `go to`  : ends at (3009.8, -617.1) mm  -> MISS 3172.4 mm; drove 3.07 m of arc
  wire GO_TO_R   : ends at (-99.5, 10.1) mm     -> miss 0.5 mm
```

The second case leaves the playfield to reach a point 10 cm behind the robot.

## Mechanism

`startGoTo` (`src/blocks/motion.ts:183`) encodes the target as a
constant-curvature arc -- `theta = 2*atan2(y,x)`, arc length `s = R*theta` --
and hands `(s, theta)` to `startMove` -> `MotionEngine::moveX()`. That pair is
only self-consistent when executed as **one blended arc**. `moveX` splits any
`|rotation| >= 50 deg` (`kTurnFirstAngleRad`) into pivot-then-straight, which
pivots `theta` and then drives `s` -- the *arc length* -- as a *straight line*.
Different endpoint, and the pivot over-rotates by `theta - bearing`.

`startGoTo` also never wraps `theta` to the short arc, so a target behind the
robot becomes a near-360 deg turn around a huge circle.

This is not a defect in `moveX` -- pivot-then-straight is its documented,
measured reduction. The defect is handing it an (arc-length, arc-angle) pair.
`MotionEngine::goToR()` is the one caller that knows not to: sprint 006 gave it
its own split (pivot to the line-of-sight bearing, drive the straight-line
chord) plus `wrapToPi()`. That fix reached the wire path only.

Affects `goTo`, `startGoTo`, `whileGoingTo` -- three of the six Move-palette
blocks -- for any target more than 25 deg off the bow.

## Why nothing catches it

- Host tests exercise `MotionEngine` directly and deliberately stay **below**
  the 50 deg split threshold. The threshold is the bug.
- No TypeScript in this repo is executed by any test (see
  `no-lint-or-typecheck-gate.md`).

## What to change

Preferred: `startGoTo` should not compute an arc at all. Add a `//%` shim onto
`MotionEngine::goToR()` -- `engineGoToR()` already exists in `shims.cpp` for the
wire and merely lacks the annotation -- and have `startGoTo` call it with the
cm->mm conversion. One implementation, the fixed one, for both callers;
`goTo`/`whileGoingTo` inherit it.

Fallback: port `wrapToPi()` and the bearing/chord split into `startGoTo`.

**Either way this needs a regression test above the 50 deg threshold.** Its
absence is the entire reason this survived six sprints.

Full derivation, per-site code and the four-copy table:
[`docs/code-review/2026-08-26/raw/correctness-geometry.md`](docs/code-review/2026-08-26/raw/correctness-geometry.md).
