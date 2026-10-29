---
id: "013"
title: "Bias blend lets the motion fit drown rest observations"
status: done
use-cases: [SUC-001]
depends-on: ['012']
github-issue: ""
issue: otos-fusion-drifts-worse-than-the-sensor-and-legs-miss-cross-track.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Bias blend lets the motion fit drown rest observations

## Description

Found on hardware on 2026-10-28 (overnight acceptance, sprint 044 build
2d95673).

`GyroBiasTracker::rate()` blends the rest (ZARU) rate and the motion-fit
rate by inverse variance:
- the rest weight is `memory / noiseDensity^2`;
- the motion weight is `motionTrust / (p11 * residual * kTimeScale^2)`.

Once the robot has moved a dozen times, the motion weight is many orders
of magnitude larger. The RLS covariance treats strongly time-correlated
residuals (encoder slip) as white, so its rate variance is tiny. On top
of that, `noiseDensity` (0.00117 rad/sqrt(s)) is 12-20x the measured
heading random walk (ticket 003: 0.003-0.006 deg/sqrt(s) on the fleet
bench captures), which shrinks the rest weight by another 150-400x.
Result: once a robot has driven, rest observations no longer move the
bias.

Evidence:
- vevov, stationary since 23:22 (`captures/sprint044-acceptance-20261028/vevov-rest1.jsonl`):
  - the raw OTOS heading drifts at ~29 deg/h (102.87 -> 104.86 deg
    between 1.7 and 5.7 min), wheels unchanged, dist 0;
  - TLM `bias` sits fixed at 33 cdeg/min (~20 deg/h), the value it had
    at the end of the last motion;
  - at boot, before any motion, idle ZARU did learn (29-30 cdeg/min
    within 8 min).
- tovez (`tovez-drift1.jsonl`): the bias column wandered +29 -> -63
  cdeg/min while the camera says the gyro bias was about +15 deg/h
  (+25 cdeg/min). The motion fit (fed encoder-slip-corrupted intervals,
  see ticket 012) dominated.

Change (choose and justify, citing captures):
- Rest evidence must dominate whenever the robot has rested recently.
  The motion fit is a fallback for long stretches without rest
  (gyro-only robots driving continuously). Options:
  - a motion weight with a realistic noise model (e.g. residual
    correlation / effective sample count);
  - cap the motion weight relative to the rest weight;
  - decay the motion weight with time since the robot last moved;
  - use the motion fit only when the rest memory has gone stale.
- Set `noiseDensity` from the measured value (cite ticket 003's fleet
  numbers).

## Acceptance Criteria

- [x] Host: after 50 legs whose encoders carry 5% rotational slip
      (a motion fit corrupted as in the field), a 5 min rest with a
      30 deg/h true bias brings `rate()` within 3 deg/h of truth
      (today it stays at the motion value)
- [x] Host: a gyro-only robot driving continuously for 10 min with no
      rest still learns a constant 50 deg/h bias within 10 deg/h
- [x] Ticket 002/003/012 suites stay green (stationary criterion,
      replay)
- [x] Hex builds

## Result

The motion weight is capped at (moved / `restStale`)^2 times the rest
weight (`restStale` 300 s; `moved` = driving time since the last rest
observation), and only when rest evidence exists. `noiseDensity` is
0.012 deg/sqrt(s) (fleet 0.0032-0.0057, `fleet-*.jsonl`). Test
`test_gyro_bias_blend.py`: with leg-dependent slip (1.1 and 1/1.1) the old
blend leaves the rate 440 deg/h off after a 5 min rest; the new one is
within 3 deg/h. `test_constant_bias_is_learned_from_motion_alone` gyro
noise lowered from 0.6 to 0.06 deg/s (0.006 deg/sqrt(s) at 100 Hz, the
worst fleet value): at 0.6 the sim gyro is 20x noisier than any fleet robot
and rest evidence rightly cannot lead. The replay noise-density test now
asserts the fleet is under half the assumed value.
