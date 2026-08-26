---
status: pending
sprint: 018
---

# Rotation error: pivots physically UNDER-rotate, yet a whole tour over-rotates — so the heading error is injected by the LEGS

## Correction notice

An earlier version of this file claimed the pivot error was ~81% control
overshoot and ~19% scrub, derived by subtracting a bench (wheels-up)
measurement from a field one. **That derivation was invalid: the robot
was on the playfield for both, not on the stand**, so the "wheels-up"
term isolated nothing. The numbers below replace it and are all
camera-truthed in a single session.

## Measurements (vevov, 2026-08-25, overhead AprilCam, robot on the table)

Six isolated `RUN:pivot:90` commands, alternating direction, in place:

| quantity | mean ratio |
|---|---|
| encoder / commanded | 1.0049 |
| **camera / commanded** | **0.9852** |
| camera / encoder | 0.9805 |

Consistent across all six (cam/cmd spread 0.975-0.992). **An isolated
pivot physically under-rotates by ~1.5% against command, and by ~2%
against what the encoder believes.**

## The contradiction that matters

A four-pivot `tour:wheels` on the same robot swept, end to end:

| | value |
|---|---|
| encoder | 360.4° |
| camera | 363.7° |

i.e. the tour as a whole **over**-rotates by +3.3°. But if each of its
four pivots under-rotates like the isolated ones above (-0.94° each by
the per-segment pass, -3.8° total), the pivots cannot be the source.
The remaining ~+7° has to be injected during the four straight LEGS --
physical heading change the wheel odometry does not see.

That is consistent with the legs being where the robot scrubs: travel
distance is accurate to 0.5% over 320 cm, so the legs are right about
how FAR they went while being wrong about which way they were pointing.

## Consequences

1. **Do not "fix" the pivots.** They under-rotate slightly; correcting
   them would move the tour's closure the wrong way.
2. `rotationalSlip_` (currently 0.952) models wheel-contact scrub during
   rotation. The isolated-pivot cam/encoder ratio of 0.9805 is the
   measurement that speaks to it -- but see the warning below before
   touching the constant.
3. **The leg-injected heading error is the bigger term and is currently
   unattributed.** Confirming it needs per-boundary camera fixes at REST
   (the playfield rule's nine-pose decomposition), not a continuous
   recording segmented after the fact -- the per-segment pass that
   produced the -0.94° figure has known boundary contamination and its
   leg/pivot split should not be trusted to better than a degree.

## Warning from this file's own history

This project has now changed its rotation constant three times
(1.040 -> 0.915 -> 0.952), each time from a small sample, and
`motion_engine.h` carries a long comment about the dropped middle step
that made two of those wrong. **Six pivots is not enough to move it
again.** Establish the leg-vs-pivot split first, with rest-boundary
camera fixes, then decide which constant (if any) is actually wrong.

## Gotchas found while measuring

- `RUN:pivot` does NOT call `worldReady()`, so the OTOS is never started
  and the telemetry `oh` column reads a flat 0.00 throughout. That is
  the verb's behaviour, not a dead sensor -- the tours do call it.
- Camera yaw must be UNWRAPPED across a pivot; a single before/after
  pair cannot resolve a 180° turn, it lands on the branch cut.
