---
status: pending
sprint: '006'
---

# goTo geometry: pivot-split miss, long-way arcs, and a dead arrive tolerance

Priority: **High** — code review 2026-08-23, R-02 + R-03 + R-04 (annex
`correctness-kernel.md` KERN-02/03/04; all CONFIRMED by independent
re-derivation, arithmetic in `verify-kernel.md`).

Three related defects in the `goTo` path (blocks `go to`/`start go to` via
`main.ts` → `shims.cpp:411` → `MotionEngine::moveX`, and wire `GO_TO_R`):

1. **Pivot-split miss (R-02).** The arc encoding (`theta = 2·atan2(y,x)`,
   arc length s) is only consistent when executed as one constant-curvature
   arc. `moveX`'s ≥50° pivot-first split executes theta as a pivot then s as
   a straight leg: `goToR(100,100)` → pivot 90°, drive 157.1 mm → ends at
   (0, 157.1), a 115 mm miss on a 141 mm target. Host tests deliberately
   stay below the 50° threshold, so the suite is green.
2. **Long-way-around degeneracy (R-03).** A target behind the robot:
   `GO_TO_R -100 1` → θ=6.263 rad, R=5000 mm, s=31.3 m — a ~359° pivot plus
   a 31-metre leg, bounded only by the caller's timeout.
3. **`arrive` accepted but discarded (R-04).** The documented at-target
   no-op requires float-exact pose equality, unreachable with measured pose:
   being 0.5 mm off the target can trigger up to a 180° pivot.

## What to do

- Recompute the post-pivot leg toward the actual target (or split the arc
  geometrically instead of kinematically).
- Normalize theta to ±180° and take the short arc; clamp or reject
  pathological radii.
- Implement the arrival-tolerance check (`arrive` is already parsed).
- Add host tests **above** the 50° split threshold and for behind-the-robot
  targets — the existing suite's silence here is what let this ship.
