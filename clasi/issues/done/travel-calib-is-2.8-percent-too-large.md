---
status: done
sprint:
---

# `travelCalib` is ~2.8% too large — the robot drives short, and the 2026-08-19 tape measurement moved it the wrong way

## Summary

vevov travels **2.76% less than its odometry believes**. The motion
control itself is fine (commanded 85 cm -> odometry 85.10 cm, 0.1%);
the error is entirely in the constant that converts shaft degrees to
millimetres. `travelCalib_` should be **0.7878**, not 0.8102.

The value being replaced came from a single tape measurement on
2026-08-19 that *raised* the constant (0.7837 -> 0.8102). This
measurement says that raise was in the wrong direction, and lands
within 0.5% of the 0.7837 it replaced — so this is close to a revert.

## Measurement (2026-08-25, playfield, overhead AprilCam)

Twelve `RUN:straight` legs, three distances, both directions, each
bracketed by camera fixes taken **at rest**. `RUN:straight` is the clean
probe: test.ts documents it as wheels-only — no OTOS, no world frame, no
heading correction, and it does not steer.

| commanded | odometry believes | camera measures | cam/enc |
|---|---|---|---|
| 30 cm | 30.20 | 29.58 / 29.49 | 0.980 / 0.976 |
| 55 cm | 55.20 | 53.61 / 53.59 | 0.971 / 0.971 |
| 85 cm | 85.10 | 82.76 / 82.72 | 0.973 / 0.972 |

**The camera's own scale was verified in the same session** against
three fixed field-tag pairs of known separation: **+0.13%, −0.09%,
−0.11%**. A 2.8% camera scale error would have produced exactly this
symptom, and it is ruled out.

## It is SCALE, not offset — which is what makes `travelCalib` the right knob

Fitting `shortfall = a + b·distance`:

- free intercept: `b = 3.07%`, `a = −0.20 cm`
- through-origin (physically motivated): **`b = 2.7608%`**, residuals
  all under 0.21 cm

A stopping/deadline overshoot would have concentrated in `a` and left
`b` near zero. It did not. `0.8102 × (1 − 0.027608) = 0.7878`.

## Predictive confirmation

The model predicts that commanding `85 / 0.9724 = 87.4 cm` yields 85.0 cm
of real travel. Measured: **85.10 and 85.08 cm** — 0.1% off prediction.
(At 30.9 cm commanded the prediction was 30.05 and it measured
30.43/30.26, ~1% long, consistent with the small negative intercept
above; short legs are slightly less affected.)

## Knock-on for rotation — do not fix this twice

Heading is (wheel travel)/track, so this scale error propagated into
rotation identically. Isolated camera-truthed 90° pivots measured
camera/encoder **0.9805 before this change**. Since
`0.9805 / 0.9724 = 1.0093`, once travel is corrected the robot should
**over**-rotate by ~0.9%, and that residual — not the raw 0.9805 — is
what `rotationalSlip_` would have to answer for. **Re-measure rotation
after the travel fix lands, before touching `rotationalSlip_`.**

## What this does and does not buy

- **Accuracy: yes.** The robot will go where it is told. A commanded
  100 cm leg currently comes up ~2.8 cm short.
- **Closure: mostly no.** A uniform scale error shrinks the whole
  rectangle without stopping it closing, so tour closure is dominated by
  the rotation term, not this one. Do not expect the 3–25 mm closure
  spread to improve much from this alone.

## Status

Changed in `src/motion_engine.h` with the full derivation in its own
comment. **Not yet verified on hardware** — flashing needs a USB
connection and vevov was on battery on the playfield. `travel_calib` is
not in the v6 wire `GET`/`SET` field table (only `rotational_slip` is),
so it cannot be set at runtime to test without a flash; adding it there
would make exactly this kind of calibration checkable without a rebuild
and is worth considering.

Verification plan once flashed: re-run the same twelve legs and confirm
cam/enc lands within ~0.5% of 1.0, then re-measure isolated pivots to
get the true `rotationalSlip_` residual.

## Resolution (2026-08-26, sprint 020)

Verified on hardware. MEASURED vevov 2026-08-26,
`captures/travelcalib-verify-20260826.csv`: twelve `RUN:straight` legs
(30/55/85 cm, both directions, camera fixes at rest) on firmware
67455bf carrying `travelCalib_ = 0.7878`: mean cam/enc **0.9920**
(was 0.972) — the 2.76 % error is gone. Residual −0.53 % scale
+ 1.3 mm/leg fixed is at the camera's own current resolution
(fixed-tag placement scatter bounds camera scale at ~±0.5 %; see
`captures/travelcalib-verify-20260826-camscale.txt`). Constant left
untouched per this issue's own no-split-the-difference rule.
