# vevov travel scale after the 2026-08-28 wheel change

Stakeholder fitted smaller wheels. Measured over the micro:bit radio
relay (torture 192.168.1.12:8760, channel 4 group 10), camera
`arducam-ov9782-usb-camera`, AprilTag 53 registered to vevov's centre
of rotation (x -5.34, y -0.19, z 11.86 cm, yaw -89.86 deg).

Commands sent RAW -- no travel correction applied -- so
`scale = measured / commanded` is exactly the factor `travelCalib_` is
wrong by. Scripts: scratchpad `run100.py`, `run100b.py`.

| run | commanded | measured | scale | instrument |
|---|---|---|---|---|
| 1 | 100 cm | **90.4 cm** | 0.9040 | stakeholder's TAPE |
| 1 | 100 cm | 89.72 cm | 0.8972 | camera (same physical run) |
| 2 REV | 90 cm | 80.92 cm | 0.8991 | camera |
| 3 FWD | 90 cm | 80.76 cm | 0.8973 | camera |

Run 2 and 3 waited on `STATUS active=0` rather than a fixed sleep, and
reported `reason=stop` / `reason=aborted` -- not `timeout` -- so the
commanded distance was clocked and the runs are usable for scale.

Camera reads 0.76% short against the tape on the same run (89.72 vs
90.4). Field scale itself checks out: ArUco 4 at x=+67.2 and ArUco 8 at
x=-67.3 give 134.5 cm against a 134.3 cm field (0.15%), so the residual
is most likely the z=11.86 cm parallax correction, not world scale.
**Anchored on the tape: scale = 0.904.**

    travelCalib_  0.7878  ->  0.7878 * 0.904 = 0.7122 mm/deg
    implied wheel diameter  90.28 mm  ->  81.60 mm

UNVERIFIED: the 81.6 mm diameter is inferred from travel, not measured
with calipers. Stakeholder asked to confirm.

## Knock-on for rotation -- NOT yet applied

Pivot sweep before this correction (scratchpad `vscrub.py`, four sizes
40/70/100/130 mm, 16 pivots, |resid| <= 0.86 deg):

    |d_theta| = 0.8055 deg/mm * d + 6.08 deg      (d = COMMANDED mm)

Those commanded mm are 10% short, so per TRUE mm the slope is
0.8055/0.904 = 0.8910 deg/mm, giving effective track
2/radians(0.8910) = **128.6 mm**. With the current (stale) caliper
trackWidth_ 114.2 that implies rotational_slip ~0.888, but the
stakeholder MOVED THE WHEELS, so 114.2 is not known to still hold.
Per motion_engine.h:477-484, rotation must be re-measured after the
travel fix lands rather than corrected twice. `rotational_slip` is
wire-settable (`SET rotational_slip`); `travelCalib` is not.

Also unexplained, and not folded into any constant: a fixed **+6.08
deg per pivot** that does not scale with pivot size (gopiv shows the
same shape at +10.2 deg).

## The +6.08 deg fixed term is a WHEELS_X ARTEFACT, not the robot

Measured 2026-08-28 after the bake was flashed, same session, same
camera, over the radio relay. Scratchpad `verify_cal.py` (WHEELS_X) and
`verify_movex.py` (MOVE_X), uncorrected commands both.

| verb | commanded | measured | error |
|---|---|---|---|
| `WHEELS_X` pivot | 90 deg | 93.35 / 99.53 / 101.31 / 99.36 | **~+8 deg** |
| `MOVE_X 0 +-1571` | 90.01 deg | 90.76 / 90.76 / 89.95 / 90.76 | **+0.75 deg** |
| `WHEELS_X` straight | 80 cm | 79.43 / 79.46 | -0.7% |
| `MOVE_X 800 0` | 80 cm | 78.71 / 78.66 | -1.6% |

So the "+6.08 deg fixed per-pivot term" recorded above -- and the
+10.2 deg claimed for gopiv -- is NOT a physical property to be
explained or corrected. It is specific to the WHEELS_X path, which
drives two independent per-wheel position targets; MOVE_X's coordinated
rotation does not exhibit it. gopiv's figure was also taken through
`wheels_x()`, so it is very likely the same artefact and should be
re-measured through MOVE_X before anyone treats it as real.

MECHANISM UNVERIFIED (per-wheel stopping overshoot is a guess; nothing
here isolated it). The operational conclusion does not depend on it:
**turn with MOVE_X, not WHEELS_X.** Note also the sign convention
differs -- `MOVE_X` positive rotation increases yaw, while a `WHEELS_X`
+d/-d pair DECREASES it.

Travel calibration is confirmed at both layers (-0.7% and -1.6%), so
the travelCalib/trackwidth/slip bake stands.

STILL UNTESTED on this chassis: `MOVE_V`, `GO_TO_R`, `GO_TO_W`. Note
`GO_TO_W` picks OTOS when connected and falls back to encoder odometry
otherwise; vevov reports `otos=0`, so it would run open-loop on
drifting odometry.
