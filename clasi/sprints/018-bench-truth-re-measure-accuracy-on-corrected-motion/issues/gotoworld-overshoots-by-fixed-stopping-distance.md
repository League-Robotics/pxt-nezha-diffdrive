---
status: in-progress
sprint: '020'
tickets:
- 018-004
---

# `goToWorld` overshoots its target by a fixed ~48 mm regardless of leg length

Priority: **High** — this is the dominant remaining source of absolute
positioning error, it is systematic rather than random, and it is measured
against overhead-camera ground truth.

## Measured, single hop (isolates it from tour accumulation)

vevov, 2026-08-25, on the mat over radio. Camera recalibrated immediately
before the campaign: 10/10 ArUco ids, reprojection error 1.83 mm. Lever arm
applied (see the `worldReady()` fix, commit 27cf24b — without it this
measurement is meaningless).

```
seed from camera : robot (49.01, 20.01, 24.00 deg)   camera (48.96, 19.92, 24.0)
RUN:goto:50:30   : robot reports "arrived" at (51.03, 34.33)
camera afterwards: (50.42, 34.76) heading 74.65 deg
```

Robot belief vs camera: **7.6 mm** position, **0.83 deg** heading. The sensing
is fine. The robot simply stopped in the wrong place.

Commanded hop: (49,20) -> (50,30), **10.05 cm**. Actually travelled **14.8 cm**.
It landed **~4.8 cm past the target, along the direction of travel.**

## It is a fixed distance, not a percentage

Across n=10 camera-scored `RUN:tour:world` runs the absolute arrival error at
the final corner clustered at **median 48.1 mm** (min 40.8, p90 67.4) — with
legs of 100 cm and 60 cm, not 10 cm. A proportional error would scale with leg
length; this does not. **0 of 10 runs** landed within the 20 mm target;
6 of 10 within 50 mm.

Closure (|end - start| over the same run) was much better — median **15.3 mm**,
6/10 inside 20 mm — because a fixed overshoot at every corner largely cancels
around a closed loop. **Closure flatters this defect; absolute arrival exposes
it.** Any acceptance gate built only on closure will not see it.

## It is specific to `goToWorld`, NOT the base motion path

`RUN:straight:20` measured **19.55 cm** against 20 cm commanded on the same
robot in the same session (camera-verified) — no meaningful overshoot.
`RUN:straight` calls `startMove(d, 0)` directly. `goToWorld` goes through the
arc-planning path (`tickedMove`/`legToward`). The difference is in the latter.

That narrows where to look and rules out `travelCalib` as the cause: a wrong
travel scalar would distort `RUN:straight` too, and it does not.

## Note on travelCalib while we are here

Unrelated but found during the same hunt, and worth fixing separately:
`src/motion_engine.h:460` defaults `travelCalib_ = 0.7878f`, while
`src/DESIGN.md` line 164 states the vevov bake is **0.8102 mm/deg**. Nothing
calls `setWheelCalibration`, so 0.7878 is what runs. **The doc and the code
disagree by 2.8%.** The straight-line measurement above (19.55 vs 20.0 cm,
-2.3%) is consistent with the code value being slightly small, but one 20 cm
sample is not a calibration — a proper multi-distance fit is needed before
changing either number. Do not "fix" this by copying the doc value in.

## Suggested approach

1. Establish whether the overshoot is the ramp-down/taper stopping distance not
   being subtracted from the planned segment, or a late `serviceMove()`
   completion. `tools/leg_analysis.py` already classifies exactly this as
   `straight-overrun` (sprint 011 ticket 002) — feed it these captures.
2. Whatever the fix, re-measure with the SAME single-hop camera protocol above,
   not with closure, for the reason given.
3. n=10 is enough to see a 48 mm systematic bias but not to tune against; the
   sprint 011 campaign procedure's repetition counts apply.

## Related

- `first-camera-scored-tour-fails-closure-gate.md` — the run that surfaced this.
- `intermittent-cw-pivot-abort-wheel-reversal.md` — separate; a CW `RUN:face:90`
  silently did nothing during this session (1 of ~15 runs also showed a 45.8 cm
  corner excursion), consistent with that issue rather than this one.
- `tour-corner-fixes-are-stale-cache.md` — the stale `ox/oy/oh` projection also
  showed up inside `tour_run.py`'s own output during this campaign, as corner
  rows whose robot position was pinned at the seed value.
