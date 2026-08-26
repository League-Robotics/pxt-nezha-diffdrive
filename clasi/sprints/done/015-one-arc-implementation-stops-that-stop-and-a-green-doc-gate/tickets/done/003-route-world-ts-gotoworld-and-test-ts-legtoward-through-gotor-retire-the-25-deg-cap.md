---
id: '003'
title: Route world.ts goToWorld and test.ts legToward through goToR; retire the 25
  deg cap
status: done
use-cases: []
depends-on:
- '001'
github-issue: ''
issue: tour-legs-share-the-arc-split-defect.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Route world.ts goToWorld and test.ts legToward through goToR; retire the 25 deg cap

## Description

`tour-legs-share-the-arc-split-defect.md` documents the same arc-length-vs-
chord confusion as `block-go-to-misses-its-target.md`, on two more call
sites, both already using ticket 001/002's fixed pattern of computing a
body-frame `(bx, by)` point in cm — so both can be fixed by calling
`startGoTo(bx, by)` (the corrected, `goToR`-backed reduction from ticket
002) instead of hand-rolling an arc pair and driving it through
`startMove`/`moveX`.

**`test/test.ts` `legToward()` (`:144-172`)**, reached via `RUN:tour:robot`
(the robot-relative accuracy campaign): pivots when `|bearing| >= 50 deg`,
then falls through to `theta = 2 * bearing` (up to 100 deg) fed to
`tickedMove()` -> `startMove()` -> `moveX()`. For any residual bearing in
`[25 deg, 50 deg)`, `moveX` splits — exactly the "small residual, curve it
out" case the function's own comment says it is designed for. Worked
example in the issue: bearing 30 deg over distance `d` = 60 cm — intended
endpoint (0.866d, 0.500d), actual endpoint (0.524d, 0.907d), a **32 cm
miss**. This is a genuine tour-accuracy bug, not just a mislabeled
edge case: `tourRobot()`'s legs are what the drivetrain accuracy campaign
attributes heading error to, and this defect injects heading error
specifically on the legs — the same signature
`rotation-error-is-injected-by-the-legs-not-the-pivots.md` describes, so
until this is fixed the two causes cannot be told apart from tour data.

**`src/blocks/world.ts` `goToWorld()` (`:153-228`)**: after its own
deliberate 12 deg pre-pivot (`turnFirstDeg`, a SEPARATE, unrelated design
decision — "pointing at the target first makes every drive nearly
straight" — this stays as-is, it is not part of the defect), the residual
bearing is curved out via `s = R*theta`, but CAPPED at `kMaxArc = 25 deg`
so `theta` (= `2*b`) never exceeds exactly 50 deg — which is exactly
`kTurnFirstAngleRad`. The float comparison then fires
(`rot=0.872664630 >= thr=0.872664571 -> TRUE`), so the one leg the cap
exists to make *safe* is the one leg converted into
pivot-50-deg-then-drive-the-arc-length (3.2% long, twice the intended
heading change) — measured on vevov. The cap only binds when the 12 deg
pre-pivot leaves >= 25 deg of residual, so it is a fault case, not the
common path, but it fires on exactly the leg it was meant to protect.

**Fix, both sites**: replace the manual arc-pair computation
(`theta = 2*bearing`/`s = R*theta` in `legToward`; the capped `b`/`radius`
computation in `goToWorld`) with a direct call to `startGoTo(bx, by)` —
already exported from the `diffDrive` namespace, already correct after
ticket 002 — passing the SAME body-frame `(bx, by)` cm point each function
already computes. `goToR` (inside `startGoTo`) owns its own pivot-vs-blend
split at `kTurnFirstAngleRad` and its own short-arc wrap, so it reaches the
target correctly for ANY residual bearing, which is exactly what makes
`world.ts`'s 25 deg cap unnecessary (retiring it, and its numeric collision
with `kTurnFirstAngleRad`, as the sprint's Solution section states) and
what makes `legToward`'s own separate 50 deg pre-pivot-and-`continue` branch
redundant (the pivot-then-drive decision no longer needs to happen in
`test.ts` at all — `startGoTo` already makes it correctly in one call).
`legToward`'s outer `for (attempt < 3)` loop and its "plan from where we
ACTUALLY are" re-measure-per-leg doctrine are unrelated to this defect and
should be preserved in whatever shape makes sense once the inner pivot
branch is gone — the goal is removing the duplicate, broken arc math, not
restructuring the tour's re-measurement strategy.

`world.ts`'s own pre-pivot (`turnFirstDeg = 12 deg`) is untouched by this
ticket — it is a deliberate navigation choice, not the defect.

## Acceptance Criteria

- [x] `src/blocks/world.ts`'s `goToWorld()` no longer computes its own
      capped arc (`kMaxArc`, the `radius`/`2*b` arithmetic) — the residual
      leg after the optional 12 deg pre-pivot is driven via `startGoTo(bx,
      by)` (or an equivalent direct call into the ticket-002-fixed
      reduction), and `kMaxArc` and its clamping logic are removed
      entirely (not just raised) — the sprint's Solution section states
      this cap becomes unnecessary once `goToR` is reachable.
- [x] `test/test.ts`'s `legToward()` no longer computes `theta = 2 *
      bearing` and no longer has its own separate `|bearing| >= 50 deg`
      pre-pivot-and-`continue` branch — the residual leg is driven via
      `diffDrive.startGoTo(bx, by)` (qualified — `test.ts` is outside the
      `diffDrive` namespace), which owns the pivot-vs-blend decision
      internally.
- [x] The issue's worked regression case (bearing 30 deg, d = 60 cm) is
      proven fixed by a host test: today's arc-length reduction misses by
      ~32 cm (0.531d); after the fix, the equivalent `goToR`-backed
      reduction lands within a few mm, matching `goToR`'s already-proven
      precision (ticket 001).
- [x] `world.ts:207`'s own comment recording the measured vevov cap
      collision (`rot=0.872664630 >= thr=0.872664571`) is removed along
      with the code it described, or updated to state that the collision
      no longer applies (cap retired) — do not leave a stale comment
      describing removed logic.
- [x] `turnFirstDeg` (12 deg) and its pre-pivot logic in `goToWorld` are
      unchanged — confirm this explicitly rather than silently touching
      it, since it is a deliberate, unrelated design decision.
- [x] Existing 597-test suite (plus tickets 001/002's new tests) stays
      green.

## Files Expected To Change

- `src/blocks/world.ts` — `goToWorld()`'s residual-arc computation
  replaced by a `startGoTo(bx, by)` call; `kMaxArc` and its clamp logic
  removed; the stale collision comment removed or corrected.
- `test/test.ts` — `legToward()`'s `theta = 2 * bearing` curve math and its
  own `>= 50 deg` pre-pivot branch replaced by a `diffDrive.startGoTo(bx,
  by)` call; the surrounding `for (attempt < 3)` re-measure structure
  simplified to whatever shape remains sensible once the inner pivot
  branch is gone.
- `tests/host/` — new host regression test for the bearing-30-deg/d=60cm
  case (extending the same motion-engine-level harness ticket 001 used,
  since neither `world.ts` nor `test.ts` is TypeScript that any test in
  this repo executes).

## Test Requirement

A test that fails against today's code and passes after: the issue's own
worked example (bearing 30 deg, distance 60 cm, intended endpoint
(0.866d, 0.500d), today's actual endpoint (0.524d, 0.907d), a 32 cm miss)
reproduced at the `MotionEngine`/`goToR` host-test level. The test must
show today's arc-length-through-`moveX` reduction (mirroring `legToward`'s
current math) misses by approximately 0.531d, and the `goToR`-backed
reduction (mirroring the fixed `startGoTo(bx, by)` call both sites now use)
lands within a few mm of the same target. `world.ts`'s cap-collision fix
does not need a separate numeric regression test beyond this — removing
`kMaxArc` removes the class of bug, and the underlying `goToR` correctness
above 50 deg is already covered by ticket 001's tests.
