---
id: '002'
title: Distance-chosen default cruise speed (cruise==0 sentinel)
status: done
use-cases:
- SUC-003
depends-on:
- '001'
github-issue: ''
issue: trajectory-shaping-constant-acceleration-profiles-speed-chosen-by-distance.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Distance-chosen default cruise speed (cruise==0 sentinel)

## Description

Every wire move that sends `cruise == 0` ("use the default") resolves
to a flat, distance-independent speed today (`Rig::defaultCruiseMmS_`,
`src/shims.cpp` — seeded 150 mm/s, read via `engineDefaultCruiseMmS()`
and the `onMoveX`/`onGoToR`/`onGoToW`/`onWheelsX` call sites in
`src/comms/wire_adapter.cpp:397-399` and siblings). Nothing stops that
flat default from asking a move to travel farther than it can brake
from before its own stop point.

This ticket resolves the same sentinel to a distance-aware default for
the taper-shaped move family only (`moveX()`/`goToR()`/`goToW()`, which
`goToWorld()` also reaches via `goToR()`); `wheelsX()`/`wheelsV()` keep
today's flat sentinel unconditionally — see sprint.md's Design
Rationale ("only moveX()/goToR()/goToW() get the distance-aware
default") for why: `wheelsX()`'s two per-wheel distances have no single
"leg length" the braking formula is defined over.

Depends on ticket 001 for `aDecelMmS2_`/`vMaxMmS_`/`brakeFrac_` and
their accessors.

## Acceptance Criteria

- [x] `MotionEngine` gains a resolver (e.g.
      `defaultCruiseForDistance(float distanceMm) const`) implementing
      `v_default(D) = min(vMaxMmS_, sqrt(2 * aDecelMmS2_ * brakeFrac_ *
      D))`, living in `motion_engine.{h,cpp}` (not `shims.cpp`/
      `wire_adapter.cpp`) so it shares its constants with ticket 001's
      taper formula and cannot drift from it — see sprint.md's Design
      Rationale.
  - [x] When `aDecelMmS2_ == 0` (legacy), this resolver is not
        consulted at all — the existing flat
        `Rig::defaultCruiseMmS_`/`engineDefaultCruiseMmS()` path is the
        only one exercised, unchanged.
- [x] `onMoveX` (`wire_adapter.cpp`) passes its own `distance` argument
      into the new resolver when `cruise == 0` and `aDecelMmS2_ > 0`;
      falls back to `engineDefaultCruiseMmS()` when `aDecelMmS2_ == 0`.
- [x] `onGoToR`/`onGoToW` do the same, using the call's own chord
      length (`hypot(x, y)`) as `D`.
- [x] `onWheelsX`/`onWheelsV`'s `cruise == 0` resolution is completely
      unchanged (still `engineDefaultCruiseMmS()` unconditionally) —
      add or confirm a test pinning this so a future change cannot
      silently widen scope here.
- [x] `Rig::defaultCruiseMmS_` (ordinal 15, `SET default_cruise`) is
      not removed and not repurposed — it remains the legacy/
      `WHEELS_*` default exactly as today.
- [x] A resolved default cruise of `0` (e.g. `D == 0` or
      `aDecelMmS2_`/`brakeFrac_` misconfigured to yield 0) is treated
      the same way an explicit `cruise <= 0` already is at each call
      site (`Wire::Result::kRange` per the existing `onMoveX`/
      `onWheelsX` pattern) — never silently commands nothing while
      reporting success.

## Implementation Plan

**Approach**: Add the resolver as a `const` method on `MotionEngine`
next to `effectiveTrackWidth()` (same "derived, never cached" pattern).
Update the three wire-handler call sites to branch on `aDecelMmS2_ >
0.0f` (readable via ticket 001's getter) before choosing which
resolution path to call.

**Files to modify**:
- `src/motion/motion_engine.h`/`.cpp` — the new resolver method.
- `src/comms/wire_adapter.cpp` — `onMoveX`, `onGoToR`, `onGoToW` call
  sites (confirm `onWheelsX`/`onWheelsV` are untouched).

## Testing

- **Existing tests to run**: `tests/host/test_motion_engine_deadline_boundary.py`,
  any existing wire-adapter host tests covering `onMoveX`/`onGoToR`/
  `onGoToW`'s `cruise == 0` path (grep `tests/host/` for
  `cruise == 0`/`resolvedCruise` coverage before assuming none exists).
- **New tests to write**: a resolver-level unit test (monotonic in
  `D`, respects the `vMaxMmS_` ceiling, matches
  `sqrt(2*aDecelMmS2_*brakeFrac_*D)` within floating-point tolerance)
  and a wire-handler-level test confirming `onWheelsX`'s sentinel is
  untouched. The full "never needs to brake harder than its own
  `aDecelMmS2_`" end-to-end proof is ticket 004's job.
- **Verification command**: `uv run pytest tests/host/ -k "cruise or default_cruise or motion_engine"`
