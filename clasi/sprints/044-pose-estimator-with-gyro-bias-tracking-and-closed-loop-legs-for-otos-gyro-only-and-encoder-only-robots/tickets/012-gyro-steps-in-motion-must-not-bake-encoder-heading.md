---
id: "012"
title: "Gyro steps in motion must not bake encoder heading"
status: open
use-cases: [SUC-001, SUC-002]
depends-on: ['010']
github-issue: ""
issue: otos-fusion-drifts-worse-than-the-sensor-and-legs-miss-cross-track.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Gyro steps in motion must not bake encoder heading

## Description

Found on hardware on 2026-10-28 (overnight acceptance run, tovez, sprint
044 build 2d95673, `captures/sprint044-acceptance-20261028/tovez-drift1.jsonl`).

In motion, `PoseEstimator` checks the gyro change against the encoders
(`consistent()`: within `gateSlack` 1 deg + `gateFraction` 30% of the
encoder turn). Around pivot starts and stops the OTOS heading lags the
encoders (10 Hz reads, chip latency), so a few samples fail the gate.
`rejectJump()` then keeps the output on the encoders. After
`confirmSamples` consistent samples it counts a "step" and re-anchors at
the CURRENT (encoder-derived) heading. Whatever the encoders mis-measured
over the rejected interval (pivot slip) is baked in permanently. That is
the same failure as the old `fuseHeading()`, at lower rate.

Evidence (tovez, 52 legs, 14.6 m, 12 min):
- Each of the 4 steps leaves the estimator +1.41 / +1.55 / +1.62 / +1.70
  deg away from the raw OTOS. All have the same sign, and each is
  preceded by exactly 4 rejects.
- The 52 legs without a step: estimator minus OTOS turn is -0.02 +- 0.05
  deg per leg.
- Against the camera, heading error regressed on time and cumulative
  turn: the raw OTOS gives +15.2 deg/h and +1.07% scale (resid 0.77
  deg); the estimator gives +37.5 deg/h and +0.98% (resid 0.87). So the
  steps make the estimator WORSE than the raw sensor (2nd-half rms 5.97
  vs 3.35 deg).
- vevov streamed TLM through a 90 deg pivot
  (`captures/sprint044-acceptance-20261028/vevov-stream-pivot1.jsonl`):
  the OTOS heading lands +5.5 deg one read (0.15 s) after the wheel counts
  freeze. The estimator total still matched (90.72 vs 90.79 deg), because
  that read arrived before the 0.25 s rest dwell. The lag is real and
  large.

In a pivot the gyro is the better instrument: about +-1 deg per pivot,
against several degrees of encoder slip. The encoders must not be able
to overrule it.

Change:
- While moving, a gyro change that disagrees with the encoders but whose
  implied rate since the anchor is physically plausible (below a named
  `maxPlausibleRate`, comfortably above the engine's omega ceiling, e.g.
  2x `omegaMax`) is real rotation the encoders missed. Accept it into the
  heading (and the bias motion fit), not hold it.
- Only an implausibly fast jump (a sensor glitch) takes the existing
  reject/confirm path. When such a jump is confirmed as a step, the
  heading must come from the gyro since the last accepted anchor
  (excluding only the glitch itself), never from the encoders over the
  rejected interval.
- Rest-time behaviour (hold, ZARU, steps at rest, ticket 010 disturbance
  gate) is unchanged.
- Keep `rejectedCount()` / `stepCount()` meaning "rejected sample" /
  "confirmed glitch", so TLM `rej` and `step` stay interpretable.

## Acceptance Criteria

- [ ] SimGyro gains a read-latency option (the gyro lags truth by N
      reads, or by a time). With 1-2 reads of lag, 5% rotational slip and
      a 150 deg/h bias, a sequence of 20 pivots (mixed signs, 45-180
      deg) leaves estimator heading within 0.5 deg of truth in Optical
      and GyroOnly, with zero steps.
- [ ] Regression: the pre-fix behaviour (step baking encoder slip) is
      reproduced by the new test against the old gate and fixed by the
      new one; say so in the ticket.
- [ ] A true glitch (an instantaneous 10 deg jump that holds) is still
      rejected and counted as a step, and the heading does not take the
      glitch.
- [ ] Ticket 002/003/007/008/010/011 suites stay green, including the
      real-capture replay.
- [ ] Hex builds via `tools/make_deploy.py`
