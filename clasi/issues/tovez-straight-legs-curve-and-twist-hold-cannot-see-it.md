---
title: "tovez's straight legs curve ~1.1%; twist hold cannot correct an encoder-invisible curvature by construction"
status: pending
created: 2026-09-05
---

# tovez's straight legs curve, and the knob sprint 031 tuned cannot see it

Full analysis: `docs/sprint-031-postmortem.md` section 2.2. This issue
replaces an earlier one titled "tovez's wheels are not matched, and lag
is chassis-wide" -- that framing rested on a per-wheel step-lag fit that
cannot distinguish motor response from encoder sampling order
(`diffdrive.cpp:522` refreshes left before right every cycle) and is
withdrawn.

## What is measured

MEASURED tovez 2026-09-05, `captures/session-b-20260905/ticket016/g3-600/g3-legs.csv`,
six alternating +-600 mm legs at 100 mm/s:

- heading change flips sign with drive direction (- + - + - +); mean
  magnitude 3.19 deg, signed mean -0.21 deg -- a body-frame curvature,
  not drift;
- forward legs curve UNIFORMLY (lateral 18-24 mm vs the 17.8 mm a
  uniform 3.4 deg arc predicts);
- 3.4 deg over 600 mm on a 114.2 mm track = **1.1% differential ground
  travel**.

## Why raising `twist_hold_gain` could not fix it

`src/core/diffdrive.cpp` ~615-641 holds ENCODER twist,
`0.5*((posR-posR0)-(posL-posL0))` in counts, to a reference integrated
from the commanded twist. If the ground disagrees with the encoders (a
~0.5 mm tire-radius difference, or asymmetric scrub), the error twist
hold sees is zero and it does nothing at any gain. Tickets 012 and 015
tuned this gain.

## Open question (decided by `captures/session-b-20260905/discriminator-20260905/` if present)

- (A) encoder-INVISIBLE: encoder `h` ~ 0 across a leg the camera says
  turned 3 deg. Fix: a per-robot `straight_trim` biasing the twist
  reference (sprint 031's late ticket).
- (B) twist hold SEES it and cannot hold: encoder `h` tracks the camera.
  Fix: headroom / speed-floor interaction in the trim clamp, not a
  constant.

## Also recorded, not release-blocking

- Reverse legs have a different profile (heading change concentrated
  late in the leg, lateral 5-8 mm); G2's reverse arcs 2-5x worse than
  forward. Unexplained.
- G5 per-wheel step-lag fit: left 0.11-0.225 s, right 0.05-0.15 s, left
  slower 8/8. An OBSERVATION only; see the sampling-order caveat above.
- Pivot repeatability sd ~1.8 deg after the slip fix; `stop_distance` 0
  and `lag` 0.13 (the step value, not a pivot fit) are the S10.2 knobs.
