---
status: pending
sprint: 018
---

# Verify the vevov travelCalib change on hardware, then re-measure rotation

## Description

`src/motion_engine.h`'s `travelCalib_` was changed **0.8102 → 0.7878** and
flashed to vevov (full reprogram confirmed), but the new value has **never
been checked against ground truth**. Until it is, the robot is running an
unverified geometry constant that affects every commanded distance and,
through the kinematics, every commanded rotation.

The change rests on a camera-truthed measurement made on the playfield:

- Commanded 85 cm → odometry believes 85.10 cm (control is fine, 0.1%) →
  overhead AprilCam measures **82.7 cm**. The robot travels **2.76% less
  than it believes**.
- A camera-scale confound was ruled out by checking three fixed field-tag
  pairs of known separation: +0.13% / −0.09% / −0.11%.
- Scale was separated from offset by fitting `shortfall = a + b·distance`
  across 30/55/85 cm: through-origin slope **2.7608%**, residuals under
  0.21 cm. A stopping/deadline bug would have concentrated in `a`; it did
  not. That is what makes `travelCalib` the right knob.
- Confirmed as a prediction rather than a re-fit: commanding 87.4 cm
  produced 85.10 and 85.08 cm against a predicted 85.0.

Note this nearly reverts a 2026-08-19 **tape measurement** that had raised
the constant from 0.7837, i.e. that earlier change appears to have gone the
wrong way. A tape over 80 cm cannot resolve what the camera resolves here.

**Two theories were tested and falsified.** Recorded so they are not
re-tried:

1. *"Straight legs inject the heading error"* — hidden heading change
   (camera minus encoder) was only +0.04°/100 cm averaged, and forward and
   reverse had opposite signs, so it is mild curvature that partly cancels,
   not the ~1.8°/leg the theory needed.
2. *An "81% control overshoot / 19% scrub" split* — invalid, because it was
   derived by subtracting a supposedly wheels-up run that was in fact on
   the table, so it isolated nothing.

## Cause

Distinct from the calibration itself, a tooling gap currently blocks the
verification outright:

`tools/robotlink.py` hard-codes `ZAVAZ_PORT = '/dev/cu.usbmodem2121302'`.
Serial ports here are hub-position-based and change on replug, so this
breaks with a bare `FileNotFoundError` whenever the relay is moved.
`radio-robot-elite/config/devices.json` goes stale the same way — it holds
last-probed ports, and at time of writing both `zavaz` and `vevov` point at
ports that no longer exist. Only `getez` is present, and that is channel 3,
belongs to another robot, and must never be retuned.

## Proposed fix

**1. Resolve the relay port at runtime.** In `tools/robotlink.py`, add a
`resolve_port(board_name, role)` that reads `devices.json`, selects by
board name and role, and verifies `os.path.exists(port)` before returning.
On a missing entry or absent port, fail with a message naming the remedy
(`mbdeploy probe`, run from the radio-robot-elite directory) rather than a
bare `FileNotFoundError`. Keep the explicit `port=` argument as an
override; keep the constant only as a last-resort default. Follow
`camproc.resolve_venv()`'s existing "one place a path is written down"
pattern.

**2. Verify travelCalib (falsifiable).** Twelve `RUN:straight` legs at
30/55/85 cm, both directions, robot on the playfield in camera view, each
leg bracketed by camera fixes **at rest**.

- Predicted: `cam/enc` moves from **0.972 to within ~0.5% of 1.000**.
- If it misses, the scale model is wrong: revert `travelCalib_` to 0.8102
  and reopen `travel-calib-is-2.8-percent-too-large.md`. **Do not tune the
  constant to split the difference** — that is precisely the failure mode
  `motion_engine.h`'s own comment documents across the 1.040 → 0.915 →
  0.952 history.

**3. Re-measure rotation (falsifiable).** Isolated 90° pivots, alternating
direction, camera-truthed.

- Predicted: camera/encoder moves from **0.9805 to ~1.009**, because
  heading is (wheel travel)/track, so the travel scale error propagated
  into rotation identically. That residual — not the raw 0.9805 — is what
  `rotationalSlip_` (currently 0.952) owes; ~0.9% over-rotation implies
  ≈0.943.
- **Do not change `rotationalSlip_` on six samples.** Gather 12+ in both
  directions and account for the CCW/CW asymmetry already observed
  (1.0101 vs 1.0064), which a single scale constant cannot express.

**4. Promote the measurement harnesses into `tools/`**, with
arithmetic-only tests under `tests/tools/` (pre-flight bounds rejection,
the scale-vs-offset fit, unwrapping across the ±180° branch cut). Fold the
pivot harness into the existing `tools/pivot_truth.py` rather than adding a
fourth pivot tool — the repo already carries `pivot_truth.py`,
`rotation_check.py` and `turn_sweep.py`, and sprint 005 consolidated
exactly this kind of sprawl. Reuse `field.wrap()`, `camproc.Cam`,
`tlm.require_stream()` and `robotlink.open_link()`; adding a ninth
`wrap()` is the specific mistake to avoid.

## Verification

- `uv run pytest` — full suite, 540 passing at time of writing.
- Steps 2 and 3 above are the hardware verification. Each states its
  predicted value and its revert path.
- Closure regression: three or more `tour:wheels` runs via
  `tools/tour_capture.py --radio`, charted with `tools/tour_chart.py`.
  Baseline is **closure 3–25 mm, spread 21 mm** over three runs. Expect
  `travelCalib` alone **not** to improve closure much — a uniform scale
  error shrinks the whole rectangle without stopping it closing, so it buys
  absolute accuracy, not closure. The 21 mm spread is the noise floor: a
  change smaller than that cannot be judged on three runs, so use five or
  more before claiming an improvement.
- Before any run, follow `.claude/rules/playfield-testing.md`: confirm the
  room lights are on, do the pre-flight path check from a **measured**
  pose, and confirm which surface the robot is on from the OTOS travel
  column (~112 cm across a tour on the table, ~1 mm on the stand) rather
  than from memory.

## Related

- `clasi/issues/travel-calib-is-2.8-percent-too-large.md` — the measurement
  and derivation behind the constant change.
- `clasi/issues/rotation-error-is-injected-by-the-legs-not-the-pivots.md` —
  where the rotation residual gets recorded.
- `.claude/rules/playfield-testing.md` — field limits, lights, pre-flight
  check, v6 `#<id>` sequencing requirement.
- `src/motion_engine.h` — `travelCalib_` and `rotationalSlip_`, each with
  a load-bearing provenance comment that must be kept accurate.
