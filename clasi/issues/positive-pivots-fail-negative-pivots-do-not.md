---
status: pending
---

# Positive (CCW) pivots fail; negative (CW) pivots do not

## Description

Commanded positive pivots on vevov fail often and in two distinct ways.
Commanded negative pivots have never failed. Measured against the
overhead AprilCam, which is independent of the robot's own sensors.

Tally across every uncontaminated run, 2026-08-20:

| direction | ok | failed |
|-----------|----|--------|
| +180 deg  | 3  | **5**  |
| -180 deg  | 8  | 0      |

The cleanest single run, with encoder deltas read from DIAG alongside
the camera (a 180 deg pivot needs ~2129 counts per wheel):

| # | commanded | camera | enc dL | enc dR | verdict |
|---|-----------|--------|--------|--------|---------|
| 1 | +180      | 233.2  | -2444  | +3761  | FAULT   |
| 2 | -180      | -176.4 | +2083  | -2183  | ok      |
| 3 | +180      | **-1.7**   | **0** | **0** | FAULT |
| 4 | -180      | -171.8 | +2106  | -2395  | ok      |
| 5 | +180      | **-2.4**   | **0** | **0** | FAULT |
| 6 | -180      | -174.5 | +2155  | -2350  | ok      |

Two failure modes, distinguishable by the encoder columns:

1. **Gross over-rotation** (row 1). The wheels really turned, but far
   too much and asymmetrically: 3761 counts right against 2129 needed.
2. **Complete no-op** (rows 3, 5). **Exactly zero encoder counts on
   both wheels.** The robot never moved; the move started, commanded
   nothing, and reported completion. This is the more tractable lead --
   a move that commands nothing and then claims success is a defect in
   the move engine's start path, not in the drivetrain.

The healthy rows double as confirmation of the corrected geometry:
-180 commanded gives -172 to -176 physical at ~2100 counts per wheel,
within 1% of prediction.

## Cause

Not identified. What the evidence rules OUT:

- **Not the encoder wedge.** `wpk` stayed pinned at 19/54 and `egl` at
  (0,1) through all six pivots -- those are historical values from
  before the run, not new events. An earlier note in this repo blamed
  the wedge; that was wrong.
- **Not the OTOS.** The camera certified it at 1.001-1.005 over ten
  pivots. The sensor reports the truth.
- **Not a first-move-of-session effect.** An earlier revision of this
  issue claimed the fault followed session starts rather than
  direction. That reading came from runs where +180 happened to be
  first, and from one run contaminated by the camera daemon being
  stopped mid-measurement (a stopped daemon read as "robot did not
  move"). Both framings are withdrawn.

Worth examining first, given the zero-count mode: `startMove`'s target
and baseline computation for a positive yaw, and whatever completion
test `serviceMove` applies on its first pass. Something makes a
positive-yaw move satisfy its own completion condition immediately.
Note the failures cluster after a preceding negative pivot, so the
reversal path (`lastNonzeroSign_`, the dwell, the sigma-delta carry) is
also in scope.

## Verification

`/tmp/pivot_probe.py` in the originating session drove this; the
durable pieces are `tools/camlink.py` (camera, with an explicit
daemon-down error) and `tools/pivot_truth.py`. A fix means positive
pivots match negative ones in both camera degrees and encoder counts.

Robot must be ON THE FLOOR -- the bench stand holds the wheels off the
ground, so nothing rotates and every reading is zero -- and inside the
camera's field of view, with a CALIBRATED daemon serving world_xy.

## Related

- `rotationScrub` was corrected 1.040 -> 0.952 in the same session
  (camera-measured steady-state under-rotation). Separate defect, and
  the old value had the sign of the effect backwards.
- Supersedes `intermittent-cw-pivot-abort-wheel-reversal.md`, which
  described a direction-dependent pivot fault -- the same phenomenon,
  though that file named the opposite direction.
