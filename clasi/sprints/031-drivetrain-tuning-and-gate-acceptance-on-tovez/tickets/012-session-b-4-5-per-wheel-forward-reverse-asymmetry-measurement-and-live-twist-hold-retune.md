---
id: '012'
title: 'Session B (4/5): per-wheel forward/reverse asymmetry measurement and live
  twist-hold retune'
status: open
use-cases: [SUC-001]
depends-on: ['009']
github-issue: ''
issue: tovez-drivetrain-tuning-and-restated-acceptance-bars.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Session B (4/5): per-wheel forward/reverse asymmetry measurement and live twist-hold retune

**Type: (a) hardware/playfield — team-lead executes personally. Live
`SET` iteration (twist-hold gain), no reflash needed mid-ticket.**

## Description

Six `MOVE_X ±600 0 200` legs on the corrected firmware showed forward
legs turning −6.0/−1.0/−5.6° and reverse legs turning +4.3/+1.7/+5.0°
(`g3-run-north.log`) — one wheel runs faster than the other at the same
command, and the twist hold at gain 2 doesn't cancel it. Per this
sprint's Design Rationale, try the twist-hold gain first (it's already
live-settable via `SET`, `setTwistHoldGain`, no reflash):

1. Measure the per-wheel forward/reverse gain with `WHEELS_V ±v` per
   wheel, encoder vs. camera.
2. Sweep the twist-hold gain and re-run 600 mm legs (3 forward, 3
   reverse) at each candidate value.
3. If the sweep plateaus above the 1° bar, flag it in the closing note
   — ticket 015 then falls back to a baked per-wheel `travel_calib`
   instead (a firmware bake, not fixable by this ticket alone).

## Acceptance Criteria

- [ ] Per-wheel forward/reverse gain measured (encoder vs. camera),
      capture cited.
- [ ] Twist-hold gain swept; the value (if any) that holds six of six
      600 mm legs within 1° both ways is identified.
- [ ] If no twist-hold value achieves the bar, the closing note states
      the best achieved result and explicitly recommends the
      per-wheel `travel_calib` fallback for ticket 015 — do not report
      success on a value that doesn't meet 1° both ways.
- [ ] The converged twist-hold value (or the recommendation to use
      `travel_calib` instead) is written for ticket 015 to bake.

## Testing

- **Existing tests to run**: N/A — hardware tuning session.
- **New tests to write**: none here; any resulting bake gets pinned in
  ticket 015.
- **Verification command**: N/A (hardware ticket).
