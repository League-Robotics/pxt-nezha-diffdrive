---
status: done
sprint: '015'
tickets:
- 015-003
---

# `legToward` and `goToWorld` carry the same arc-split defect, in the tours the accuracy campaign runs

Priority: **Critical** -- same mechanism as `block-go-to-misses-its-target.md`,
but on the code paths whose closure numbers are currently being attributed to
the drivetrain.

## `test.ts` `legToward()` -- routine

`test/test.ts:144` pivots when `|bearing| >= 50 deg`, then falls through to
`theta = 2 * bearing`, which runs up to 100 deg. **For any residual bearing in
[25 deg, 50 deg), `moveX` splits** -- precisely the "small residual, curve it
out" case the function's own comment says it is designed for.

Worked case, bearing 30 deg over distance `d`: theta = 60 deg, R = d,
s = 1.047d. `moveX` pivots 60 deg then drives 1.047d straight.

- intended endpoint (0.866d, 0.500d)
- actual endpoint   (0.524d, 0.907d)
- **miss = 0.531 d** -- on a 60 cm leg, **32 cm**

The `for (attempt)` loop does not save it: only the pivot branch `continue`s,
the curve branch `return`s.

`tourRobot()` is reached as `RUN:tour:robot` and is how the robot-relative
accuracy campaign runs. The defect injects heading error **on the legs** (the
pivot over-rotates by `theta - bearing`), which is the exact signature
`rotation-error-is-injected-by-the-legs-not-the-pivots.md` describes.

**This does not refute the drivetrain hypothesis.** It means the two cannot be
told apart from tour data until this is fixed, and it should be ruled in or out
before more bench time goes into the other explanation.

## `world.ts` `goToWorld()` -- boundary collision

`blocks/world.ts:216` caps the arc bearing at `kMaxArc = 25 deg`, so the
rotation handed to `moveX` caps at exactly **50.000 deg** -- and
`kTurnFirstAngleRad` is exactly 50 deg. The float comparison fires:

```
rot = 0.872664630   thr = 0.872664571   rot >= thr -> TRUE
```

So the capped leg -- the one the cap exists to make *safe* -- is the one leg
converted into pivot-50-deg-then-drive-the-arc-length (3.2% long, twice the
intended heading change).

The cap only *binds* when the pre-pivot (fires at bearing >= 12 deg) leaves
>= 25 deg of residual, so this is a fault case rather than the common path.
`world.ts:207` records it as measured on vevov. The more durable problem is the
coupling: two constants, two languages, two files, numerically coincident at a
threshold, with no comment linking them and no test.

## What to change

Fold into `block-go-to-misses-its-target.md`. If both call sites route through a
corrected `goToR`, the `legToward` defect disappears and `goToWorld`'s collision
becomes moot (a correct `goToR` handles any bearing, so the cap is unnecessary).

If they must stay separate: port the bearing/chord split into `legToward`, and
cap `goToWorld` at 24 deg with a comment at each end naming the other constant.

Detail: [`docs/code-review/2026-08-26/raw/correctness-geometry.md`](docs/code-review/2026-08-26/raw/correctness-geometry.md).
