---
title: "tovez's left and right wheels are not matched, and lag/stop_distance are chassis-wide constants that cannot express it"
status: pending
created: 2026-09-05
---

# tovez's wheels are not matched

Four independent acceptance gates, all measured on 2026-09-05 against
camera truth, each report the same left/right asymmetry. None was
designed to look for it.

MEASURED tovez 2026-09-05, firmware 1.20260904.5 (commit 38808e1),
`rotational_slip` 0.962, captures under
`captures/session-b-20260905/ticket016/`:

| gate | observation | capture |
|---|---|---|
| G5 | per-wheel step lag **left 0.168 s mean vs right 0.096 s**, left slower in 8 of 8 trials with no exceptions | `g5/` |
| G3 | 600 mm leg `dh` flips sign with drive direction (- + - + - +); mean magnitude 3.19 deg, signed mean only -0.215 deg | `g3-600/` |
| G2 | reverse arcs 93.1 mm mean endpoint error vs forward 16.5 mm; every reverse `dh_err` negative | `g2/` |
| G1 | pivot wheel-speed peaks left 56-89 mm/s vs right 102-138 mm/s for equal commanded magnitude | `g1-slip0962/` |

A single left/right response mismatch explains all four.

## What it is NOT

- **Not `twist_hold_gain`**, where sprint 031 spent its tuning effort.
- **Not `rotational_slip`**. That is a scale factor; it cannot produce
  a sign flip that tracks drive direction. (Correcting it from an
  unknown prior value to 0.962 did cut G1's mean|err| from 4.604 to
  1.531 deg -- worth baking on its own merits -- but it left G1's sd at
  1.775 deg, and it does nothing for G2/G3.)

## The blocking problem

`MotionLimits::lag`, `MotionLimits::stopDistance` and
`MotionEngine::travelCalib_` are each ONE chassis-wide constant. There
is no per-wheel field anywhere, so the asymmetry above is not
expressible in the current config surface.

`lag` currently reads 0.13 on tovez -- almost exactly the average of
the two measured wheels (0.168 and 0.096), i.e. wrong for both by
roughly 40% in opposite directions.

## Proposed

1. Split `lag` into per-wheel fields (`lag_l` / `lag_r` or an array),
   and probably `stop_distance` with it. The seed measurement already
   exists in `g5/`.
2. Re-run G1/G2/G3/G6 after the split, before touching any other knob.
3. Only then revisit `twist_hold_gain`.

## Acceptance

- [ ] The wire exposes a per-wheel lag (and stop_distance) field.
- [ ] tovez's measured 0.168 / 0.096 s are baked and the build reports
      them back.
- [ ] G3's per-leg `|dh|` and G2's forward-vs-reverse gap are
      re-measured against the same bars and the change is recorded,
      pass or fail.

UNVERIFIED: that the split actually closes the gates. What is measured
is the asymmetry, on four gates, with the captures named above.
