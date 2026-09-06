---
id: '003'
title: Fix arc-move (combined distance+yaw) abort in the motion engine
status: open
use-cases: []
depends-on: []
github-issue: ''
issue: arc-moves-abort-distance-never-driven.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Fix arc-move (combined distance+yaw) abort in the motion engine

## Description

`move()` calls with BOTH distance and yaw nonzero abort: distance never
drives (x stays ~0) and yaw terminates early — the tighter the arc, the
earlier. Measured on tovez 2026-08-25 (wire pose h is centidegrees):

| command | believed end pose | verdict |
|---|---|---|
| `move(0, 180)` (pivot) | Δh = 18076 (180.76°), x,y ≤ 14 mm | correct |
| `move(20, 0)` (straight) | 200.3 mm on 200 mm commanded | correct |
| `move(20, 90)` (arc) | Δh = 7733 (77.3°), x ≈ 0, y = 19 mm | wrong |
| `move(20, 180)` (arc) | Δh = 256 (2.56°), x = 0, y = 1 mm | very wrong |

Isolated pivots and isolated straights are correct. Only the combined
case fails, and it fails worse for larger rotations.

### Investigation leads (in priority order — verify against telemetry
before committing to a fix; none of these is confirmed)

1. **Shared-deadline-across-two-phases (planning-time lead, most
   consistent with the measured pattern)**: `shims.cpp`'s `startMove()`
   (lines 379-440) computes ONE flat timeout backstop
   (`duration*1000 + 1500ms`, line 436-437) sized for a single BLENDED
   (simultaneous) distance+yaw segment. But `MotionEngine::moveX()`
   (`motion_engine.cpp:150-171`) actually SPLITS any combined move with
   `|rotation| >= kTurnFirstAngleRad` (50°, motion-api.md S3.3) into
   TWO SEQUENTIAL phases via `queuePivotThenStraight()` (pivot alone,
   then straight alone, each using the same `cruiseMmS`). Two
   sequential phases each carry their own ramp-up (`rampMs_`) and
   end-of-move taper overhead (`serviceMove()`,
   `motion_engine.cpp:269-368`); a budget sized for ONE simultaneous
   segment's overhead may not cover TWO. This is consistent with
   "tighter arc completes earlier": both repro cases (90° and 180°)
   exceed the 50° split threshold, so both go through
   `queuePivotThenStraight()`, and 180° (the larger rotation) fails
   worse. **Verify by instrumenting or logging which of
   `serviceMove()`'s three abort conditions actually fires** —
   `expired` (line 344/360), `out.stallHalted`, or `wrongWay` — for
   each repro case. If `expired` fires during or right after phase 1
   (the pivot), this lead is confirmed.
2. **Stall latch tripping on the slow inner wheel** (from the issue's
   own triage) — an arc's differential wheel speeds mean one wheel
   moves much slower than the other; if the kernel's stall detector
   is tuned around a single-wheel-speed assumption, the slow wheel
   could false-trip `out.stallHalted`.
3. **Completion predicate for combined distance+yaw profiles** (from
   the issue's own triage) — possible off-by-something in how
   `distDone`/`yawDone` combine when both are tracked simultaneously,
   though note that after the pivot-then-straight split, phase 1 is a
   PURE pivot (`distTarget == 0`) and phase 2 is a PURE straight
   (`yawTarget == 0` implied by `startSegment(pendingDistance, 0.0f,
   ...)` — motion_engine.cpp:356) — so if the split is working as
   coded, `serviceMove()` should never actually see a truly-combined
   `distTarget != 0 && yawTarget != 0` profile. Confirming this in
   itself is useful investigation output even if it doesn't turn out
   to be the fix.
4. **Speed floor interacting with the arc's wheel-speed mix** (from
   the issue's own triage) — `kTaperFloor`/`distFloor_`/`turnFloor_`
   interaction in `serviceMove()`'s scale computation.

Do not assume lead 1 is correct — it is a planning-time reading of the
code, not a hardware-confirmed diagnosis. Use this project's
`systematic-debugging` approach: instrument, measure, confirm which
condition actually aborts the move, THEN fix.

### Scope boundary (why this stays inside the existing module pair)

Whichever lead turns out to be correct, the fix is expected to be
expressible as a change to `shims.cpp`'s existing budget arithmetic
and/or values already owned by `MotionEngine`'s `move_` struct — no new
class, no new cross-module dependency, no change to `wire_adapter.cpp`
or `wire_handler.cpp`'s call shape into `startMove()`/`moveX()`. If
investigation shows the real fix needs more than that (e.g., a new
per-phase timeout concept that has to be threaded through the wire
adapter as well), **throw a ticket exception** rather than silently
expanding scope — see this repo's Exception Protocol
(`get_instruction("software-engineering")`).

## Acceptance Criteria

- [ ] Root cause identified and confirmed against actual telemetry
      (not just code reading) — which of `serviceMove()`'s abort
      conditions fires, for each repro case, before the fix.
- [ ] `move(20cm, 90deg)` drives ~20 cm and completes ~90° (camera or
      encoder ground truth), not the measured-defective 77.3°/~0 cm.
- [ ] `move(20cm, 180deg)` drives ~20 cm and completes ~180°, not the
      measured-defective 2.56°/~0 cm.
- [ ] Isolated pivot (`RUN:turn:<deg>`) and isolated straight
      (`RUN:go`) remain correct after the fix — re-measure both, don't
      just assume no regression.
- [ ] Verification uses camera or eyeball ground truth in addition to
      believed (encoder-derived) pose, per this project's
      playfield-testing rule — believed-correct-but-physically-wrong
      is the other half of the original bug report and must be ruled
      in or out on the floor.
- [ ] Any host-level test coverage this fix touches
      (`tests/host/test_motion_engine_*.py`) still passes, and a new
      host test is added if the root cause is reproducible without
      hardware (motion_engine.cpp/h are host-portable by design).

## Implementation Plan

**Approach**: Follow the `systematic-debugging` protocol — instrument
first (confirm which abort condition fires), form a fix hypothesis
from the confirmed cause (starting with the shared-deadline lead
above, but not committing to it), implement the smallest fix that
addresses the confirmed cause, then re-verify all four repro cases
(2 arcs + 2 isolated moves) on tovez with ground truth.

**Files likely to modify** (exact set depends on confirmed root
cause):
- `src/shims.cpp` — `startMove()`'s duration/timeout/cruise
  computation (lines 379-440), if lead 1 is confirmed.
- `src/motion_engine.cpp`/`.h` — `MotionEngine::moveX()`,
  `queuePivotThenStraight()`, or `serviceMove()`, if the fix belongs
  at the engine level instead of (or in addition to) the shim level.

**Testing plan**:
- Host tests: `tests/host/test_motion_engine_primitives.py` and any
  other `test_motion_engine_*.py` files — run scoped to this module,
  per this project's rule that ticket-level test runs are scoped, not
  full-suite (full suite runs once at `close_sprint`).
- Hardware: build, flash to tovez over USB (mbdeploy,
  `built/mbcodal-binary.hex`), drive via `RUN:arc:90` and `RUN:arc:180`
  (`projects/blocktest`), read pose via `TLM POSE #1` serial telemetry
  (remember the v6 sequencing rule — wire commands need `#<id>` or are
  silently dropped as stale retransmits).
- Re-verify `RUN:turn:<deg>` and `RUN:go` in isolation as a regression
  check.
- Camera or eyeball ground truth for at least the two arc repro cases,
  per playfield-testing rules — do not close this ticket on believed
  pose alone.
- Confirm the robot is on the playfield, not the bench stand, before
  any of this hardware verification (bench odometry is not a proxy for
  field accuracy, and OTOS `ox`/`oy` travel is the cheapest
  discriminator per this project's own playfield-testing notes).

**Documentation updates**: Update `motion_engine.h`'s own doc comments
if the fix changes anything about the pivot-then-straight split's
timing contract (the header currently documents the split's endpoint
behavior in detail but says nothing about per-phase timing budgets —
if the fix adds that concept, document it there).
