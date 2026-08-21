---
status: done
---

# First move after an idle gap runs at full duty (the lurch)

## Description

The first move issued after any pause ran at 100% duty instead of the
commanded rate. Captured on vevov, commanded +180 deg at 45 deg/s
after a 70 s idle:

```
tick 0:  duty  -2500/+2500   (25%)
tick 1:  duty  -5000/+5000   (50%)
tick 2:  duty  -7500/+7500   (75%)
tick 3+: duty -10000/+10000  (100%, pinned for 14 more ticks)
```

Wheels reached ~7000 counts/s against a commanded 581 -- about
440 deg/s against a commanded 45. The move ended after 17 ticks
(healthy moves run ~180) because it blew through its encoder target
almost immediately, and momentum carried the robot past. Stakeholder,
watching: *"it lurched really fast ... like you were driving it at a
really high velocity."*

This is the true source of the over-rotations logged all session --
262, 233 and 277 deg for a commanded 180 -- and retroactively explains
the encoder tour's first leg measuring 226 mm for a commanded 600, and
the lever-arm calibration's first pivot reading 100.7 deg for 45.

## Cause

`DifferentialDrive::step()` measured its own cycle period as
`now - previousCycleStart` with **no upper bound**. Nothing steps the
kernel between moves, so the first step after an idle computed `dt`
equal to the entire idle. `positionError()` advances its reference by
`speed * dt`, so a 70 s gap injected roughly **40,000 counts of phantom
position error in a single tick**. The controller then did the only
sensible thing with an error that size: slewed duty to 100% and held
it.

Two earlier diagnoses in this file's history were WRONG and are
recorded here so they are not re-derived:

- *"Direction-dependent -- positive pivots fail, negative do not."* The
  test sequences simply put +180 in the first-after-idle slot more
  often. With the gap fixed, both directions are equally clean.
- *"First move of a SESSION."* It is the first move after any idle
  gap, session start being merely the most common one.

A third claim, that the encoder wedge was implicated, was also wrong:
`wpk` is a cumulative maximum, so it could never have shown a fresh
wedge smaller than the historical 54 -- it neither confirmed nor ruled
anything out.

## Fix

A gap too long to be a control cycle means the kernel was not running,
so there is nothing to integrate across. Beyond 250 ms the cycle now
re-anchors through the same path the very first cycle already uses
(`measuredPeriodUs = 0` -> `dt = 0`; `positionError()` and
`adaptBias()` both re-anchor rather than integrate when `dt <= 0`), and
increments `cycleGapCount` -- surfaced on `Output` and at probe index
26 so the condition is visible rather than inferred.

Commit 704c40d.

## Verification

Bench, same 70 s idle and same command:

| | before | after |
|---|--------|-------|
| peak duty | 100% | 13% |
| ticks saturated | 14 | 0 |
| ticks in move | 17 | 200 |

Playfield, under load, against overhead-camera truth:

| | camera | error | ticks | peak duty | rate |
|---|--------|-------|-------|-----------|------|
| first after 75 s idle | +178.2 | -1.8 | 175 | 12% | ~42 deg/s |
| then -180 | -178.4 | +1.6 | 193 | 13% | ~39 deg/s |
| then +180 | +179.2 | -0.8 | 194 | 12% | ~38 deg/s |
| first after 2nd idle | -179.3 | +0.7 | 185 | 12% | ~40 deg/s |

Reproduce with `RUN:15` / `RUN:16` (instrumented pivots, per-tick duty
and encoder positions dumped after the move) after a 70 s idle, robot
on the floor and in camera view.

## Related

- `rotationScrub` 1.040 -> 0.952 in the same session, camera-measured.
  Separate defect; the old value had the sign of the effect backwards.
  The clean post-fix errors (<= 1.8 deg on a 180 deg pivot) confirm the
  new value.
- `serviceMove` also credited wrong-way rotation as progress
  (`|target| - |progress|`), so a pivot that turned the wrong way
  reported success. Fixed alongside; now signed, with a wrong-way abort
  and counter (probe index 25).
- Supersedes `intermittent-cw-pivot-abort-wheel-reversal.md`.
