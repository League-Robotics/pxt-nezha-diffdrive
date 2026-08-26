---
id: '004'
title: startMove() budgets the sequential need when the split will fire, not the blended
  max()
status: done
use-cases: []
depends-on: []
github-issue: ''
issue: arc-moves-abort-distance-never-driven.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# startMove() budgets the sequential need when the split will fire, not the blended max()

## Description

`src/shims.cpp::startMove()` (`:379-440`) computes the caller's `timeout` as
`max(dist_duration, yaw_duration) + 1500 ms` — correct for a BLENDED move,
where both axes finish together. But `MotionEngine::moveX()`
(`motion_engine.cpp:166`) splits into pivot-then-straight whenever
`distance != 0.0f && std::fabs(rotation) >= kTurnFirstAngleRad` (50 deg),
which runs the two axes SEQUENTIALLY and needs `dist_duration +
yaw_duration` — `motion_engine.h`'s own comment is explicit that ONE
deadline (set once, in `moveX()`) spans both phases, "NOT reset across a
pivot-to-straight phase transition." Whenever the split fires, `margin =
1500 ms - min(dist_duration, yaw_duration)`, which goes negative whenever
the SHORTER axis alone exceeds 1.5 s.

Measured against the real firmware C++ (`arc-moves-abort-distance-never-
driven.md`, `movex_budget_probe.cpp`), at nominal block-default rates
(15 cm/s, 90 deg/s):

```
move(20, 90)   budget 2833 ms   sequential need 2333 ms   margin +500 ms
move(20, 180)  budget 3500 ms   sequential need 3333 ms   margin +167 ms
move(30, 180)  budget 3500 ms   sequential need 4000 ms   margin -500 ms
move(50, 180)  budget 4833 ms   sequential need 5333 ms   margin -500 ms
move(100, 180) budget 8167 ms   sequential need 8667 ms   margin -500 ms
```

`move(d, 180)` is over budget at ANY distance because `yaw_duration` alone
(2.0 s at 90 deg/s) already exceeds the 1.5 s margin. On hardware this is
worse than the ideal-wheels replay shows: the deadline can bite DURING the
pivot (phase 1 has `distance == 0`, so `pureTurn` is true and the *yaw*
taper's `turnFloor` (0.12) crawl alone costs ~1.25 s, consuming the margin
before phase 2 ever starts) — "distance never driven" was measured
literally true on tovez for `move(20, 90)`.

**The fix (preferred, per the issue)**: in `startMove()`, when
`distanceMm != 0.0f && std::fabs(rotationRad) >= <the 50 deg threshold>` —
the EXACT SAME condition `MotionEngine::moveX()` itself uses to decide to
split — budget `dist_duration + yaw_duration` instead of `max(...)`.
Otherwise (no split), keep `max(...)` unchanged. One deadline per call
either way, matching the existing contract; smallest diff.

**Design note — do not duplicate the magic number blindly.** `moveX()`'s
50 deg threshold is `MotionEngine::kTurnFirstAngleRad`, a `private static
constexpr` member (`motion_engine.h:355`) — `shims.cpp` cannot reference it
directly today. This sprint's whole point is eliminating exactly this
class of defect (two files needing the same threshold with no link between
them — see `world.ts`'s retired 25 deg cap, ticket 003). Prefer exposing a
small public accessor on `MotionEngine` (e.g. a `static constexpr float`
getter) over re-typing `0.8726646f` a second time; if duplication is
judged unavoidable, it must carry an explicit comment naming
`motion_engine.h`'s `kTurnFirstAngleRad` at both ends, matching the
discipline the issue itself asks for ("cap `goToWorld` at 24 deg with a
comment at each end naming the other constant" — the fallback this sprint
did not need for `world.ts`, but the discipline still applies wherever a
threshold value must legitimately live in two places).

Also update the flat `+1500u`'s comment: today it says it "allows for the
end-of-move taper" for a single segment; it needs to say it is now the ONLY
thing paying for an entire second phase when the split fires, matching the
issue's own note.

## Acceptance Criteria

- [x] `startMove()` in `src/shims.cpp` budgets `dist_duration +
      yaw_duration` (plus the existing flat `+1500u` backstop) when
      `distanceMm != 0.0f && |rotationRad| >= <50 deg threshold>` — the same
      condition `MotionEngine::moveX()` uses to decide to split — and keeps
      `max(dist_duration, yaw_duration) + 1500u` otherwise.
- [x] The 50 deg threshold used in `shims.cpp` is either read from a public
      `MotionEngine` accessor or duplicated with an explicit two-sided
      comment linking it to `motion_engine.h`'s `kTurnFirstAngleRad` — not
      a bare, unexplained second `0.8726646f`.
- [x] The `+1500u` backstop's comment in `startMove()` is updated to state
      it now covers an entire second phase's ramp/taper overhead when the
      split fires, not just one segment's.
- [x] `move(30, 180)` — the smallest nominal-rate case unambiguously over
      budget per the issue's measured table — is proven fixed by a host
      test: it reaches its commanded heading AND drives its commanded
      distance, where today's `max()`-based budget truncates it short.
- [x] The non-split cases (`move(20, 90)`, any blended-below-threshold
      move) are unaffected — same `max()` budget, same behavior, no
      regression to the already-passing
      `test_deadline_boundary_pure_pivot_production_timeout_matches_unbounded`/
      `..._pure_straight_..._matches_unbounded` tests in
      `tests/host/test_motion_engine_deadline_boundary.py`.
- [x] Existing 597-test suite stays green.

## Files Expected To Change

- `src/shims.cpp` — `startMove()`'s duration formula (sum vs max, split
  condition) and its `+1500u` comment.
- `src/motion/motion_engine.h`/`.cpp` — only if a public accessor for the
  50 deg threshold is added (preferred over duplicating the raw constant).
- `tests/host/test_motion_engine_deadline_boundary.py` — this file already
  contains a Python mirror of `startMove()`'s current formula
  (`_shim_move_params()`, `:243-283`) and the exact verification technique
  needed (compare a real-timeout run against an effectively-unbounded
  baseline, `_run_leg`/`_drive_to_completion`/`_assert_reached_target`),
  plus a negative-control pattern that already proves a truncated budget
  is detectable
  (`test_deadline_boundary_split_leg_truncates_without_the_margin`). Update
  `_shim_move_params()` to mirror the FIXED formula, and add a new
  `move(30cm, 180deg)`-shaped test case (mirroring `_split_leg_params()`'s
  existing pattern, at this file's own `PRODUCTION_SPEED_MM_S`/
  `PRODUCTION_YAW_RATE_DEG_S` rates) that fails against a reproduction of
  today's `max()`-based budget and passes against the fixed sum-based one.
  Note: the existing `test_deadline_boundary_split_leg_production_timeout_matches_unbounded`
  test already covers a split leg (350 mm / 70 deg) and already PASSES
  today — its rotation is small enough (`yaw_duration` well under 1.5 s at
  production rates) that it does not exercise this defect; the new
  `move(30, 180)`-shaped case is required specifically because 70 deg
  does not reproduce it and 180 deg does.

## Test Requirement

A test that fails against today's code and passes after, for `move(30,
180)` specifically (the issue's own "smallest nominal-rate case
unambiguously over budget"): today's `max()`-based budget (3500 ms) is
below the sequential need (4000 ms), so the split move is cut off by its
deadline before the straight phase completes — the test must show the
commanded heading is not reached and/or the commanded distance is not
driven under today's formula, and that both ARE reached once the budget is
sum-based. `tests/host/test_motion_engine_deadline_boundary.py`'s existing
`_run_leg`/`_drive_to_completion`/`_assert_reached_target` helpers and its
own `..._truncates_without_the_margin` negative-control pattern are the
established, reusable machinery for this — extend that file rather than
inventing a parallel harness.
