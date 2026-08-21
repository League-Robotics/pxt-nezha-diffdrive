---
status: pending
---

# First pivot of a session grossly over-rotates

## Description

The first commanded pivot after a session begins turns far more than
asked. Measured on vevov against the overhead AprilCam (independent of
the robot's own sensors), commanded +180 deg:

| run | 1st pivot | 2nd | 3rd | 4th | 5th | 6th |
|-----|-----------|-----|-----|-----|-----|-----|
| A   | **262.2** | -177.6 | 164.5 | -162.6 | 164.2 | -165.0 |
| B   | **232.5** | -174.1 | 165.3 | -166.4 | — | — |

Reproduced on two independent runs. The second pivot is also slightly
transitional (0.987, 0.967 of commanded) before the robot settles into
its steady-state 0.915 ratio.

This is NOT direction-dependent. An earlier reading of the same data
concluded "+180 fails, -180 works", which was wrong -- +180 merely
happened to be first in both runs.

The same signature appears elsewhere in the session's data, always on
the FIRST move after a fresh start or a `seedPose`:

- lever-arm calibration: the first 45 deg pivot read 100.7 deg, the
  remaining seven all read ~42 deg.
- encoder-only square tour: leg 1 measured 226 mm for a commanded 600
  and its turn read 161.6 deg for a commanded 90; legs 2-4 measured
  589/597/588 mm.

## Cause

Not yet identified. The direction of the error is informative: the
robot turns MORE than commanded, and a move ends when the encoder
delta reaches its target, so the encoders must be UNDER-counting early
in the first move -- the move keeps running because the counts have not
arrived yet.

That points at the first-sample baseline rather than at the control
law: `NezhaMotorPort` holds `lastPosition_`/`sampleTimeUs_` from
whenever it last collected, and a stale or missed first sample would
under-report the initial delta. Note this is the opposite sign from the
steady-state error (the robot under-rotates once warm, which is the
scrub constant, fixed separately).

Worth ruling out first, cheaply: whether `basic.pause`/idle before the
first move lets the brick sleep (the known auto-sleep wedge), and
whether the accel ramp's first tick interacts with a stale sample.

## Verification

`tools/pivot_truth.py` reproduces it directly -- it drives alternating
pivots over the relay while sampling the overhead camera, and prints
camera / gyro / wheels side by side. A fix means the first row's
`cam/cmd` sits near 1.0 like the rest:

    python3 tools/pivot_truth.py --reps 3

Robot must be ON THE FLOOR (the bench stand holds the wheels off the
ground, so nothing rotates) and inside the camera's field of view.

## Related

- The steady-state under-rotation found in the same session was a
  separate defect: `rotationScrub` was 1.040 with the sign of the
  effect backwards, now 0.952 (camera-measured). See shims.cpp.
- The OTOS is NOT implicated: it agreed with the camera to within
  0.5% across ten pivots (gyro/camera 1.001-1.005).
- Supersedes the framing in
  `intermittent-cw-pivot-abort-wheel-reversal.md`, which described this
  as a direction-dependent fault.
