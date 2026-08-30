# Sprint 020 — Playfield accuracy campaigns on corrected motion: findings

**Date:** 2026-08-26/27 (UTC evening). **Robot:** vevov (chip UID
`9906360200052820b8e12372c44f4f67…`, identity confirmed by `HELLO` →
`device NEZHA2 robot vevov 1198504156`). **Firmware:** this repo at
commit `67455bf`, built with `tools/make_deploy.py` (vevov bake:
channel 4, `kProfile` "vevov"), flashed on the field through gauti
(`~/bin/mbflash`, Remount count 0→1, no FAIL.TXT, `RUN:probe` →
`OPROBE:95:1`). **Camera:** `arducam-ov9782-usb-camera`, calibrated and
not stale, AprilTag 1 read world (0.070, 0.032) cm before any run.
**Link:** gauti USB serial (`/dev/ttyACM0`), one scripted session per
command. Measured this session: the DAPLink port-open reset does NOT
fire under gauti's pyserial defaults — keepalive `ack` ids proved one
continuous program lifetime across sessions.

Evidence artifacts (all in `captures/`):

- `travelcalib-verify-20260826.csv` — campaign 1, twelve legs
- `travelcalib-verify-20260826-camscale.txt` — camera scale check
- `gotoworld-arrival-20260826.csv` — campaign 2, ten scored hops,
  abort log, three closure tours
- `leg-vs-pivot-split-20260827.csv` — campaign 3, nine-boundary lap +
  six isolated alternating pivots

## Campaign 1 — travelCalib 0.7878 vs camera truth

Twelve `RUN:straight` legs (30/55/85 cm, both directions), camera fixes
at rest bracketing every leg. Mean cam/enc **0.9920** (30 cm legs
0.9911, 55 cm 0.9915, 85 cm 0.9933). Shortfall fits
`a + b·d` with **b ≈ 0.53 %** (scale) and **a ≈ 1.3 mm** (fixed). No
forward/reverse asymmetry (0.9918 vs 0.9921).

The 2026-08-25 measurement that motivated the change had cam/enc 0.972;
the predicted post-change value was 1.000 ± 0.5 %. Measured 0.992: the
2.76 % error is gone; a ~0.5 % + 1.3 mm residual remains. **But** the
camera-scale confound check (fixed-tag pair separations vs surveyed)
scattered −1.0 %…+1.7 % with inconsistent signs — physical tag
placement scatter (~±3 mm/tag), which bounds the camera's absolute
scale accuracy at ~±0.5 % on this field. The pre-ArUco AprilTag 10/11
ground-truth dots that the original ±0.13 % confound check used no
longer exist.

**Verdict: `travelCalib` 0.7878 is verified to the instrument's current
resolution.** The residual 0.5 % scale cannot be attributed
robot-vs-camera without re-surveying the tag placements; the ~1.3 mm
fixed per-leg component is not expressible as a scale error at all. Per
the issue's own rule, the constant was not touched.

## Campaign 2 — goToWorld absolute arrival on corrected firmware

Ten scored single-`goto` hops at tour-leg scale (42–97 cm legs,
rectangle ±45/±25 after hop 1), each seeded from a camera fix at rest
and scored by an independent camera fix at rest:

median **50.6 mm**, p90 64.6 mm, max 84.7 mm; **0/10 within 20 mm,
5/10 within 50 mm**. The error is dominantly along-track PAST the
target, ~35–44 mm at every leg length.

**Verdict: the fixed ~48 mm overshoot (median 48.1 mm, 2026-08-25)
SURVIVES sprints 015/016 unchanged in both magnitude and character.**
Closure contrast: three seeded `tour:world` runs arrived 29–32 mm from
the final corner and consecutive tours landed 7–12 mm apart — chaining
flatters the fixed overshoot, exactly as the original campaign found.

Two new findings fell out of this campaign:

1. **`RUN:goto` (closed profile) terminates legs early.** 5 of 15 goto
   calls ended 5–11 cm into the leg with a normal `GOTO:end`, honest
   believed pose, and **no latched state** (in-session `STATUS`:
   `flags=0x31` = ready|connL|connR only; one timestamped abort died at
   t = 0.50 s against a ~4.3 s deadline, so not a timeout). Three
   4-leg `tour:world` runs under the open profile had zero aborts.
   Filed: `clasi/issues/goto-under-closed-profile-terminates-legs-early.md`.
2. **OTOS belief drift of 1.3–6.4 cm per hop**; the two worst arrivals
   (63.8, 84.7 mm) were both westward legs along the north side and
   carried the two largest belief errors.

## Campaign 3 — leg-vs-pivot rotation split, per-boundary fixes at rest

Nine-boundary lap (4 legs + 4 pivots, one command per session, camera
fix at rest at every boundary, yaw unwrapped) plus six isolated
alternating ±90° pivots. A sunbeam over the NE corner blinded the tag
at westward headings there, so the lap started at NW facing south and
boundary b6 was lost (pivot 3 merges with 25 cm of leg 4); leg 3 was
shortened to 52 cm to respect the 12 cm margin after northward drift.

- **Legs** inject heading the encoders never see: **+1.80, +0.67,
  +0.97, −1.26°** per leg (camera Δh minus encoder Δh). Real, up to
  1.8°/leg — but direction-dependent, not the uniform per-leg bias the
  "+7° from the legs" hypothesis needed. Net +2.2°/lap.
- **Pivots** now **over-rotate: mean cam/cmd 1.0230** over nine clean
  90° pivots (CCW 1.0220 n=6, CW 1.0252 n=3, asymmetry within noise).
  The 2026-08-25 isolated-pivot result (0.9852 under-rotation) is
  **inverted** on current firmware. The sign and roughly two-thirds of
  the size match travelCalib 0.8102→0.7878 propagating into rotation
  (predicted ≈1.013); the remaining ~+1 % says `rotationalSlip_` 0.952
  now over-corrects. Per the standing rule, no constant was changed on
  nine pivots. Pivot slip was 1.16–1.47 cm per 90°, ~3× the 0.09–0.50 cm
  of 2026-08-25.
- Whole lap: camera net 365.10° vs commanded net 355.4° — +9.7°/lap
  over-rotation, vs +3.3° per tour on 2026-08-25.

**Verdict: "rotation error is injected by the legs, not the pivots" is
RETIRED as stated.** On corrected firmware both terms contribute, and
the pivots (~+2.1°/90°, ≈ +8.4°/lap) are now the dominant one. Filed:
`clasi/issues/pivots-over-rotate-on-corrected-firmware.md`.

## Issue reconciliation

| finding | status |
|---|---|
| travelCalib 0.7878 unverified | **verified** (to instrument resolution) — `travel-calib-is-2.8-percent-too-large.md` and `finish-the-vevov-calibration-verification.md` moved to done |
| goToWorld fixed ~48 mm overshoot | **survives** — restated against 67455bf in `gotoworld-fixed-overshoot-survives-corrected-firmware.md` |
| rotation injected by legs, not pivots | **retired** — superseded by `pivots-over-rotate-on-corrected-firmware.md` (legs contribute ±0.7–1.8°/leg, direction-dependent) |
| goto early termination (new) | **filed** — `goto-under-closed-profile-terminates-legs-early.md` |

## Follow-ups not done here (deliberately)

- `tools/robotlink.py` runtime port resolution and promoting the
  campaign harnesses into `tools/` (steps 1 and 4 of the verification
  issue) — tooling, out of scope for the measurement sprint.
- Re-survey the ArUco tag placements (or restore two surveyed
  ground-truth dots) so the camera can again resolve 0.1 %-class scale
  questions.
- The stopping-distance diagnosis for the surviving overshoot belongs
  to the restated overshoot issue, not this sprint.
