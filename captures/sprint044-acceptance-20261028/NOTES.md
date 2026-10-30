# Sprint 044 overnight acceptance, 2026-10-28/29

Boards: vevov (tag 53, WiFi 10.55.82.20, its Pi Zero `zilch` went
unreachable at ~23:05) and tovez (tag 52, serial via Pi Zero `null`).
Both flashed with sprint branch 2d95673 (hexes in this folder), camera
arducam-ov9782-usb-camera. Lanes: vevov x < -15, tovez x > +15.

## Setup findings

- tovez's tag 52 registration was 180 deg off: the 3 cm test drove +y
  while the camera said it faced -y. Re-registered with mount_yaw +pi/2
  (mount_x -4.1 kept); the repeat test agreed (bearing 101 deg, facing 97-102).
- The motor kernel is lazy: STATUS reads ready=0 connL=0 connR=0 until
  the first motion command, while idle OTOS reads already run (bias
  learned at boot).
- On the new firmware, idle bias learning works: vevov at 8 min after
  boot, raw OTOS 2.12 deg, estimator held at 0, bias 29 cdeg/min
  (17 deg/h).

## vevov OTOS lever arm is ~10 cm, not 5.27 or 4.3

- `vevov-drift1.jsonl` legs 1-3: the OTOS (and estimator) leg distance
  was 24% short, 18% long and 13% short against the camera.
- `vevov-straight1.jsonl`: on straights, OTOS/camera = 0.959-0.982, so
  linear scale is ~3% short. That is not enough to explain the misses.
- `vevov-pivots1.jsonl`: in-place pivots. The camera centre moves
  <= 1 cm, but the OTOS centre track moves 6.2 cm per 90 deg and 8.8 per
  180. The residual arm fit is (-4.38, +0.46) cm, rms 0.24, with test.ts's
  -5.27 cm applied.
- `vevov-cal0.txt` (RUN cal 0, arm zeroed): the sensor arm fit is
  (-10.25, +0.28) cm, rms 0.18. vevov's OTOS sits ~10 cm behind the
  pivot centre. The handoff's 4.3 cm came from a fit that assumed the
  firmware arm was zero; test.ts had already applied -5.27.
- vevov's arm is still zeroed until reboot or RUN arm.
- Needed: bake `otos_arm_x: -102.5, otos_arm_y: 2.8` for vevov. A linear
  scale bake (~1.035) needs a new key, since there is no chip linear-scalar bake.

## tovez: estimator heading worse than raw OTOS (fixed by ticket 012)

- `tovez-drift1.jsonl`, first 52 legs / 14.6 m / 12 min: estimator
  heading 2nd-half rms 5.97 deg vs raw OTOS 3.35. Error regressed on
  time and cumulative turn:
  - raw OTOS: +15.2 deg/h, +1.07% scale;
  - estimator: +37.5 deg/h, +0.98% scale.
- 4 "steps" each left the estimator +1.4..+1.7 deg off the OTOS, all the
  same sign, each after exactly 4 rejects; sum +6.28 deg.
- Non-step legs: estimator minus OTOS turn = -0.02 +- 0.05 deg per leg.
- Cause: the in-motion gate rejects the lagging OTOS at pivot ends, and
  the step confirm re-anchors on the encoder heading
  (`vevov-stream-pivot1.jsonl` shows the OTOS landing +5.5 deg one read
  after the wheels stop).
- tovez's OTOS turn gain is 1.0103 against the camera. It needs
  `otos_angular_scale` ~0.990, and its config has none.

## Bias stops adapting once a robot has moved (ticket 013)

- `vevov-rest1.jsonl`: stationary, wheels unchanged, dist 0, estimator
  heading held exactly (460.15 the whole time). But TLM `bias` is fixed
  at 33 cdeg/min (~20 deg/h) while the raw OTOS drifts ~29 deg/h
  (102.87 -> 104.86 deg between 1.7 and 5.7 min).
- Cause (code reading): `GyroBiasTracker::rate()`'s inverse-variance
  blend. The motion-fit weight treats correlated encoder-slip residuals
  as white and is orders of magnitude above the rest weight. The rest
  weight also uses `noiseDensity`, 12-20x the measured value (ticket 003).
- Before any motion (boot), idle ZARU learned fine (29-30 cdeg/min).
- The heading HOLD at rest makes this harmless while still; it bites in
  motion, where `heading = gyro - bias*t`.

## tovez baseline, build 2d95673 (before 012/013): `tovez-drift1.jsonl`

114 legs, 36.9 m, 32 min (stopped early for the fix):
- estimator pose err: 2nd-half rms 10.1 cm, max 20.0 cm.
- estimator heading err: end +20.2 deg, 2nd-half rms 19.8 deg. Raw OTOS:
  end +7.3 deg, rms 9.8 deg.
- arrival miss on camera: median 6.2 cm, p90 15.0 cm, max 26.7 cm.
- 16 steps, 84 rejects, wrng 0, dist 0.
- 3 legs ended `stall` (100-102): leg 100 overshot to y -35.3, against
  the table's -y edge, and leg 101 could not move off it. That is a
  symptom of the heading error; stall detection did its job.

## tovez arm is right; vevov's is not

`tovez-pivots1.jsonl` (build 012+013, test.ts arm -5.27 applied): the
residual arm is (0.28, 0.21) cm, |d| 0.35, rms 0.62. tovez's OTOS sits at
the test.ts arm; vevov's sits ~10 cm behind (above). test.ts hard-codes
one arm for every robot. It should come from the per-robot bake
(ticket 010's otos_arm_x/y). All 12 pivots on the fixed build: 0 rejects,
0 steps.

## Tickets 012 + 013 (b10dc22, 63c7b8f); tovez flashed with tovez-012-013.hex

Built with `--bake otos_angular_scale=0.990` (tonight's measured OTOS
turn gain 1.0103 on tovez). Run: `tovez-drift2-fix.jsonl`.

## STATUS `active` drops inside a GO_TO_W (ticket 015); harness fixed

`tovez-status-trace3.jsonl`: through one GO_TO_W (pivot then straight),
`active` went 1 -> 0 at 2.57 s (pivot end / closure dwell) and again at
3.07 s. `done` advanced only at 5.70 s; the last wheel movement was at
5.32 s. `devlink.send_move` returned on the first active=0, so the drift
script took camera fixes and TLM mid-leg and planned the next leg on top
of an unfinished one. That explains `tovez-drift2-fix.jsonl` legs 4-11:
OTOS and encoder distance agreed (~33 cm) while camera chords were
13-26 cm. It also contaminates every earlier GO_TO_W run tonight,
including the tovez baseline `tovez-drift1.jsonl` (its heading and step
findings stand; its arrival-miss numbers are pessimistic).
`goto_probe.py` (`tovez-goto-probe1.jsonl`): once settled, three legs
missed by 1.1 / 1.5 / 0.8 cm, with camera and estimator chords within
~1 cm. send_move now waits for `done` (0bfa558).
Clean re-run: `tovez-drift3-fix.jsonl`.

## vevov stationary (`vevov-rest1.jsonl`, build 2d95673)

28.4 min until a WiFi TLM read failed: the estimator heading was held at
460.15 the whole time while the raw OTOS drifted ~30 deg/h. dist 0 and
step 0 throughout; wheel counts unchanged. The sprint stationary
criterion (< 2 deg / 30 min) is met for the hold. The bias column was
stuck (ticket 013).

## tovez straights (`tovez-straight1.jsonl`, build 012+013)

OTOS/camera 0.977-0.980; the estimator 25.0-25.2 cm against the camera's
25.4-25.6. tovez could use `otos_linear_scale` ~1.021 (ticket 014).

## tovez on 012+013 with the fixed harness: `tovez-drift3-fix.jsonl`

The first 25 legs (`tovez-drift3-fix-legs0-25.jsonl`; 9.6 m, 8 min)
before the camera stall:
- estimator pose err: 2nd-half rms 1.9 cm, max 3.0 cm.
- estimator heading err: end +1.14 deg, rms 1.82 deg. Raw OTOS: end
  +0.15, rms 1.25.
- arrival miss: median 1.01 cm, p90 1.44 cm, max 4.33 cm.
- 0 rejects, 0 steps, 1 disturbance (`dist`; possibly a false trip),
  bias -8.4 deg/h.
- Against the baseline (6.2 cm median, 19.8 deg rms heading), this is
  the sprint 044 target, or within 0.01 cm of it.
- Still open: the estimator heading is slightly worse than the raw OTOS
  (bias estimate?).

Leg 26: the camera reported no motion while the encoders (~34 cm) and
the OTOS (31 cm, +38 deg) moved. The camera fix was stale (camlink
`fix()` kept returning the frozen pose of a stalled stream, and a frozen
pose passes `settled()`). Leg 27 was planned from the wrong pose and
tovez left its lane; the guard stopped it at (-1.9, 39.7), at the table
edge. It was backed off with 5 cm and 20 cm camera-checked reverses to
(17.8, 23.4). Fixes (499ada8): `Cam.fix()` returns None once no frame has
arrived for 2 s, and `otos_drift.py` stops when a leg's camera chord and
OTOS chord differ by > 12 cm.

Next run: `tovez-drift4.jsonl` on build 015 with
`otos_angular_scale=0.990` and `otos_linear_scale=1.021`
(`tovez-015-lin.hex`).

### Interim at 51 legs / 19.6 m / 15 min (`tovez-drift4.jsonl`)

- arrival miss: median 0.97 cm, p90 1.63 cm, max 2.40 cm. MEETS the
  sprint goal (median < 1, p90 < 2).
- estimator heading err: end -1.52 deg, 2nd-half rms 2.03 deg. Raw OTOS:
  end -15.69 deg (drifting -61.5 deg/h after the cold re-flash boot),
  rms 12.5 deg.
- learned bias -61.2 deg/h, matching the raw drift almost exactly
  (ticket 013 working).
- estimator pose err: 2nd-half rms 4.3 cm, max 6.3 cm, never re-zeroed.
- 0 rejects, 0 steps, 0 dist, 0 wrng.

### drift4 stopped at leg 96 (34.1 m, ~45 min): the lights went out

The chord check stopped the run: "camera chord 0.0 cm vs OTOS 28.8 cm".
The frame was black; the garage PIR had switched the lights off. With no
tag, `Cam.fix()` still returned the last pose until 40 tagless frames
had passed. The drift3 leg-26 "stale camera" was most likely the same
cause. Lights back on (Shelly). `devlink.fix` now refuses after 4
tagless frames, which triggers lights-on and a retry.
Legs 0-95 of `tovez-drift4.jsonl` are clean.

### drift4 legs 0-95 (`tovez-drift4-legs0-95.jsonl`, 34.1 m, 28 min, never re-zeroed)

- arrival miss: median 0.99 cm, p90 1.59 cm, max 2.40 cm (goal < 1 / < 2: MET).
- estimator heading err: end -3.26 deg, 2nd-half rms 2.32 deg (goal <= 3: MET).
  Raw OTOS: end -31.1 deg (-66 deg/h cold-start bias), rms 23.2.
- estimator pose err: 2nd-half rms 5.9 cm, max 8.1 cm (goal <= 15 cm: MET over 34 m).
- 0 rejects, 0 steps, 0 dist, 0 wrng, all reasons `stop`.

### drift5 interim (`tovez-drift5.jsonl`, 121 legs, 44.2 m, 36 min, never re-zeroed)

- arrival miss: median 0.91 cm, p90 1.75 cm, max 2.41 cm.
- estimator heading err: end +0.08 deg, 2nd-half rms 2.14 deg. Raw OTOS:
  end -37.6 deg (-62.5 deg/h), rms 26.9.
- estimator pose err: 2nd-half rms 7.3 cm, max 10.1 cm.
- learned bias -62.4 deg/h; 0 rejects, steps, dist and wrng.

## RESULT: tovez 100 m, build 015 + angular 0.990 + linear 1.021 (`tovez-drift5.jsonl`)

273 legs, 100.1 m, 82 min (00:52-02:14), one rebase at the start, never
re-zeroed. Scored by `tests/dev/sprint044_score.py`:

| criterion (sprint 044 / ticket 009) | target | result |
|---|---|---|
| pose err, 2nd-half rms | <= 15 cm | 11.5 cm (max 14.0) |
| heading err, 2nd-half rms | <= 3 deg | 2.35 deg (end -0.14) |
| wrong-way stalls | 0 | 0 (wrng 0; all 273 reasons `stop`) |
| arrival miss | median < 1, p90 < 2 cm | median 0.99, p90 1.76, max 2.88 |

Raw OTOS heading over the same run: end -87.1 deg (-63.9 deg/h), 2nd-half
rms 67.9. Learned bias -66.0 deg/h. 0 rejects, 0 steps, 0 dist.
Against the start-of-night build 2d95673 (`tovez-drift1.jsonl`): median
6.2 cm, heading rms 19.8 deg.

## RESULT: tovez stationary 30 min on the final build (`tovez-rest1.jsonl`)

02:15-02:45, never commanded, idle read path only:
- estimator heading -850.20 the whole time: change 0.00 deg. Camera
  25.2-25.5 deg (+-0.3 single-fix noise). Criterion < 2 deg: MET.
- raw OTOS drifted 142.16 -> 116.23 (-25.9 deg, ~-52 deg/h).
- bias adapts at rest (-109 -> -102 -> -104 cdeg/min), unlike the stuck
  33 on build 2d95673 (ticket 013 verified on hardware).
- dist 0, step 0, wheel counts unchanged.

## Speed 200 (`tovez-drift6-speed200.jsonl`, 49 legs, 17.5 m, 14 min)

Stopped when tovez's Pi Zero `null` dropped off the network (tovez itself
still answers on WiFi; this is the same failure as vevov's `zilch`).
- arrival miss: median 1.07 cm, p90 1.77 cm, max 2.76 cm (median just
  over 1 at speed 200).
- estimator heading err: 2nd-half rms 0.90 deg; raw OTOS end -14.8 deg
  (-65 deg/h).
- estimator pose err: 2nd-half rms 1.6 cm, max 2.1 cm.
- 0 rejects, steps and dist.

## Speed 300 (`tovez-drift7-speed300.jsonl`, over WiFi, 38 legs, 15.1 m, 11 min)

- arrival miss: median 1.14 cm, p90 1.66 cm, max 2.45 cm.
- estimator heading err: 2nd-half rms 1.60 deg; raw OTOS end -12.6 deg.
- estimator pose err: 2nd-half rms 1.7 cm.
- 1 dist (one disturbance flagged mid-run, not investigated), 0 rejects, 0 steps.
Ended at 03:15 when tovez stopped answering on WiFi too (battery,
probably). It is parked safely in its lane at (39.9, -14.7).

## End of night, 03:17

Both robots are unreachable (vevov since ~00:50, tovez since 03:15) and
parked on the table. The garage lights are on.

## 2026-10-29 07:32 tovez disturbance check (ticket 010), Eric handling

`disturb_watch.py`, log `tovez-disturb1.{jsonl,out}`. The bump (camera 0.64 cm, -1.6 deg) was
taken in to 0.17 cm with `dist` raised and wheels still. The lift-and-turn kept heading
(+88.35 camera, +88.73 estimator) but position was off by 3.37 cm as a vector (the
distances matched, the directions didn't). The GO_TO_W back was accurate to 0.57 cm
against the camera, so it ended 3.0 cm from the true start. Tag 52's offset from the
turning centre fits to ~1 cm, so it doesn't account for the 3 cm. STATUS showed
`i2cf=5` at the end. Follow-up: `clasi/issues/lift-corrupts-position-use-the-accelerometer.md`.

## 2026-10-29 08:5x-09:30 accelerometer build on tovez (`tovez-016-accel.hex`)

New TLM FULL columns `ax ay az apk`. 10 min untouched (`tovez-disturb2`):
dist 0, camera drift 0.02 cm, apk 0.5 s medians at most 12 mg. `tovez-disturb3`:
3.4 cm shove absorbed (camera 3.4 cm / -7.0 deg, estimator 3.3 cm / -7.3 deg), apk
up to 3300 mg. A straight 5 cm lift, held ~2 s: apk medians 36-120 mg throughout
the hold, error 1.52 cm and 2.5 deg. Signatures in the lift issue.

## 2026-10-29 i2cf split by cause (`tovez-017-i2cf.hex`)

New TLM FULL `busf stl glt`. Drift run cut at 30 legs (`tovez-drift8-016`) to look at i2cf
(8.6% of cycles vs 4.7% last night). 10 m run `tovez-drift9-017`: i2cf 371 = busf 0,
stl 380, glt 14 over 6604 cycles. Streams `tovez-i2cf-*.jsonl`: stl is tovez's left wheel
not breaking away at low duty (pivot starts, pivot-closure trims). Leg 20 missed by 3.9 cm.
Issue: `clasi/issues/i2cf-counts-stuck-wheels-not-bus-faults.md`.

## 2026-10-29 OTOS arm from config; final tovez run

- `RUN cal 0` on tovez x3 (`tovez-cal0*`): arm (-56.5, -7.6) mm, sd (1.5, 3.8), fit rms 5-8 mm
  (pivot centre wanders). Flown from config (`tovez-018-config-arm.hex`, `tovez-drift10-018`, 15 legs):
  arrival median 2.38 cm, rightward bias 2.1 cm (drift5: 0.84). Config set back to the validated
  (-52.7, -1.2); `tovez-019-config-arm.hex`, built from config alone.
- `tovez-drift11-019`: 33 legs, 17.3 m, 11 min, whole field, ended by a flat battery (null went down
  with it). Pose 2nd-half rms 4.3 cm (max 6.6), heading rms 1.05 deg, arrival median 1.13 / p90 2.18 cm.
  drift5's first 33 legs (12.0 m, x 15-50 lane): 3.8 cm (max 4.8), 0.77 deg, 0.95 / 1.43 cm.
  Tovez parked at (29.6, 26.6).

## 2026-10-29 vevov from config; drift12

`vevov-020-config.hex`: make_deploy from radio-robot-lib vevov.json only (arm -105.9/2.9 mm, linear 1.033, angular 0.992). Flashed on zilch; boot TLM ox/oy 105/-2 = arm applied.

- `vevov-drift12-020`: 92 legs, 48.8 m, 30 min, whole field. Stopped by a >15 s camera tag dropout at rest (robot fine, re-acquired at (25.6,-25.6)). Pose err 2nd-half rms 6.8 cm (max 10.9), heading rms 1.96 deg, miss median 1.57 / p90 3.22 cm, raw OTOS +16 deg/h, wrng/dist 0.
  - First 33 legs (17.3 m, same as tovez-drift11): pose rms 6.1 cm (tovez 4.3), heading rms 0.64 deg (tovez 1.05), raw OTOS +1.4 deg/h, miss 1.68 / 3.20 cm.
- `vevov-drift12b-020`: fresh rebase, 18 legs, 9.3 m, 6 min, ended "no TLM row": Eric moved the network and zilch was unreachable (not the battery). Pose rms 1.5 cm, heading rms 1.29 deg, miss 1.66 / 2.87 cm.
- Leg distance, estimator/camera: vevov 1.013 (drift12), 1.016 (drift12b); tovez 1.007. linear_scale 1.033 reads ~0.7-1.3 % long; candidate 1.020-1.026, not changed.
- `vevov-drift12c-020`: fresh rebase after the network came back, 38 legs, 20.6 m, 13 min; stopped by a camera dropout. Pose rms 7.0 cm (end 10.7), heading rms 2.25 deg (end -3.7: raw OTOS drift ~46 deg/h paused for the last 4 legs while the bias kept correcting), miss 1.61 / 2.91 cm. `dist` 1 was already latched at row 0: set on the unwatched leg during the network outage.
- otos_drift.py now holds still (STOP) and retries the camera for up to 2 min instead of exiting on the first failed fix.
- `vevov-drift12d-020`: 30 legs, 13.4 m, 11 min (time limit). One dropout at leg 6 ridden out by the retry. Pose rms 4.8 cm, heading rms 1.39 deg, miss 1.38 / 2.58 cm.
- All four camera dropouts were in the south band, y -25..-30, with the tag plainly visible in the frame.
- Raw OTOS heading drift grew through the hour: +16 (seg 1), +37 (seg 3), +70 deg/h (seg 4); bias tracking held the fused heading to 1-2 deg throughout.
- Whole hour: 178 legs, 92.0 m; estimator/camera leg distance 1.0139.
