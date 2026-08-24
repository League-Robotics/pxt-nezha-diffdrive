---
id: '001'
title: 'goTo geometry: pivot-split fix, short-arc normalization, arrive tolerance'
status: done
use-cases:
- SUC-001
depends-on: []
github-issue: ''
issue: goto-geometry-pivot-split-miss.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# goTo geometry: pivot-split fix, short-arc normalization, arrive tolerance

## Description

`MotionEngine::goToR()` (`src/motion_engine.cpp`) encodes its target as a
constant-curvature arc (`theta = 2*atan2(y,x)`, `s = R*theta`) that only
reaches `(x, y)` when executed as one blended segment. `moveX()`'s own
`|rotation| >= 50°` pivot-first split instead reissues that same
`(s, theta)` as pivot-then-straight — a different endpoint. Three
CONFIRMED defects result (code review R-02/R-03/R-04, KERN-02/03/04):

1. **Pivot-split miss.** `goToR(100, 100)` → pivot 90°, drive 157.1 mm
   → ends at (0, 157.1), a 115 mm miss on a 141 mm hop. Affects both
   `GO_TO_R`/`GO_TO_W` (wire) and the block API's `go to`/`start go to`
   (`main.ts` → `shims.cpp:_startMove` → `moveX`).
2. **Long-way-around degeneracy.** A target behind the robot
   (`goToR(-100, 1)`) gives `theta ≈ 358.85°`, `R ≈ 5000 mm`,
   `s ≈ 31.3 m` — a ~359° pivot plus a 31 m leg, bounded only by the
   caller's timeout.
3. **Dead `arrive` tolerance.** The only no-op guard is exact float
   equality (`x == 0 && y == 0`); `arrive` is parsed and discarded.
   Being 0.5 mm off target can trigger up to a 180° pivot.

**Fix, at the module level** (see this sprint's architecture overlay,
`design/DESIGN.md` §3, for the full write-up): `goToR()` owns its own
split decision instead of inheriting `moveX()`'s generic one. When
`|theta| >= kTurnFirstAngleRad` (the existing 50° threshold), issue
pivot = `atan2(y, x)` (the line-of-sight bearing — half of `theta`)
followed by chord = `hypot(x, y)` straight: turn-then-chord reaches
`(x, y)` exactly, unlike the arc's own pivot-then-arc-length split.
Normalize `theta` to the short arc (±180°) *before* making the split
decision, so a behind-the-robot target pivots at most ~180° instead of
the long way around. Honor `arrive` as a radial no-op gate:
`if (hypot(x, y) <= arrive) return;` — still single-shot, no
supervisory re-solve (a caller wanting repeat-until-arrival re-issues
`goToR()` itself, unchanged).

**C++11 gate coverage:** `motion_engine.cpp`/`.h` are covered by
`tests/host/test_cxx11_syntax_gate.py` — this ticket's entire code
change lands inside that gate. A green host suite for this ticket IS
evidence of target-build viability (unlike tickets 002/003/004/005/007,
which touch `shims.cpp`/hardware ports outside the gate).

## Acceptance Criteria

- [x] `goToR(100, 100, ...)` (bearing 45°, above the 25°/50° split
      threshold) reaches within tolerance of (100, 100) — not the
      pre-fix (0, 157.1) miss. Host test asserts the kinematically
      integrated endpoint of the issued segment(s).
      (`test_go_to_r_pivot_split_reaches_target_above_threshold`)
- [x] `goToR(-100, 1, ...)` (target behind the robot) issues a
      short-arc pivot (≤ ~180°), not a ~359° pivot plus a 31 m leg.
      (`test_go_to_r_behind_robot_near_axis_avoids_long_way_around_runaway`
      for this exact input — implementation note: this specific input
      normalizes to a ~-1.15° PLAIN-arc rotation, i.e. a near-straight
      ~100 mm reverse rather than a literal large pivot, which still
      satisfies the "≤180°" bound this AC states; a genuinely large
      (116.57°), unambiguously-split "behind" pivot is covered
      separately by `test_go_to_r_behind_robot_splits_into_bounded_pivot`)
- [x] A target at/just below the 25°/50° threshold still uses the
      plain single-segment arc reduction, unchanged from before this
      ticket (no regression to `tests/host/test_motion_engine_reductions.py`'s
      existing below-threshold coverage).
- [x] Seeding the robot at (or within `arrive` of) the target makes
      `goToR()` a no-op — no segment is issued. Test both exact-zero
      and noise-offset (e.g. (0.02, 0.05) mm with `arrive` ~10 mm)
      cases. (`test_go_to_r_arrive_gate_is_a_no_op`, plus a
      just-outside-tolerance counter-test)
- [x] `theta` normalization to the short arc is itself covered by a
      dedicated test independent of the split behavior (e.g. a
      below-threshold target behind the robot still takes the short
      turn, not the raw `2*atan2` value before normalization).
      (`test_go_to_r_theta_normalized_independent_of_split_decision`,
      goToR(-100, 0.05) -- isolates theta as the only value
      normalization changes, since this input's distance always uses
      the |y| < 0.1 straight branch regardless of theta)
- [x] `motion_engine.h`'s `goToR()` doc comment is updated to describe
      the new split-ownership and `arrive` behavior (it currently
      says "arrive accepted but unused").
- [x] Existing `tests/host/test_motion_engine_gotow.py` and
      `test_motion_engine_reductions.py` pass unchanged except where
      this ticket's fix corrects previously-wrong expected behavior.
      (all pre-existing tests pass with unmodified expectations; only
      the "must stay under the pivot-first threshold" dodge comment in
      `test_go_to_r_arc_hand_computed` was reframed per the
      implementation plan, pointing at the new above-threshold tests)

## Implementation Plan

**Approach:**
1. In `MotionEngine::goToR()`, compute `theta` and normalize it to
   (−π, π] before any split decision (this also fixes KERN-03's
   long-way-around case, since the split logic downstream only ever
   sees a bounded angle).
2. Replace the current "compute `(s, theta)` then hand to `moveX()`"
   flow with a split decision made *inside* `goToR()`: below threshold,
   keep today's plain single-segment arc reduction (`moveX(s, theta,
   ...)`); at/above threshold, call `moveX()` with the bearing-pivot +
   chord decomposition (`moveX(0, bearing, ...)` then, via `moveX`'s
   existing pending-phase queuing, `moveX(chord, 0, ...)` — or
   equivalent, whichever preserves `moveX`'s one-caller-visible-call/
   one-shared-deadline contract; do not change `moveX()`'s own
   generic split behavior, since `moveX()` is called directly by
   `shims.cpp::startMove()` for block-driven moves with distance/yaw
   inputs of its own, a different contract than `goToR`'s x/y target).
3. Add the `arrive` radial no-op gate ahead of the split decision.
4. Update `motion_engine.h`'s doc comments for `goToR()` (arrive now
   honored; split ownership moved).

**Files to modify:**
- `src/motion_engine.cpp` — `goToR()` split/normalize/arrive logic.
- `src/motion_engine.h` — doc comment updates.
- `tests/host/test_motion_engine_reductions.py` and/or
  `test_motion_engine_gotow.py` — new above-threshold, behind-robot,
  and arrive-tolerance cases; verify the existing below-threshold
  dodge comment (`"must stay under the pivot-first threshold"`) is
  either removed or reframed now that above-threshold is covered.

**Testing plan:** host-only (`tests/host`), per sprint Test Strategy.
Kinematically integrate the issued segment(s) using the same formulas
`verify-kernel.md`'s KERN-02 arithmetic uses, and assert the endpoint
is within a small tolerance of the target — do not merely assert "no
crash."

**Documentation updates:** `motion_engine.h` doc comments (above).
No canonical design-doc overlay edit needed beyond what this sprint's
`design/DESIGN.md` overlay already states at the architecture level —
this ticket implements that write-up, it does not change it.
