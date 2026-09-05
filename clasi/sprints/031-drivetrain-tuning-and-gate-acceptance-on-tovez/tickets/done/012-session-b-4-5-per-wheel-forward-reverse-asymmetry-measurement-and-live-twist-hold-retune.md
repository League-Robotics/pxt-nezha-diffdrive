---
id: '012'
title: 'Session B (4/5): per-wheel forward/reverse asymmetry measurement and live
  twist-hold retune'
status: done
use-cases:
- SUC-001
depends-on:
- 009
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

- [x] Per-wheel forward/reverse gain measured (encoder vs. camera),
      capture cited. INCONCLUSIVE result, honestly recorded — see
      Closing note; no bake was made on this measurement.
- [ ] Twist-hold gain swept; the value (if any) that holds six of six
      600 mm legs within 1° both ways is identified. NOT MET — best
      converged result is 4 of 12 legs within 1.0 deg, worst 4.16 deg.
      Left unchecked per this ticket's own "do not report success on a
      value that doesn't meet 1° both ways."
- [x] If no twist-hold value achieves the bar, the closing note states
      the best achieved result and explicitly recommends the
      per-wheel `travel_calib` fallback for ticket 015 — do not report
      success on a value that doesn't meet 1° both ways. (The fallback
      was NOT taken — see Closing note for why: the two measurement
      methods disagree on sign, so baking either is unsafe.)
- [x] The converged twist-hold value (or the recommendation to use
      `travel_calib` instead) is written for ticket 015 to bake.
      `twist_hold_gain = 4`, already baked by ticket 015 (commit
      05de015).

## Testing

- **Existing tests to run**: N/A — hardware tuning session.
- **New tests to write**: none here; any resulting bake gets pinned in
  ticket 015.
- **Verification command**: N/A (hardware ticket).

## Closing note

### Step 1 — per-wheel measurement: attempted, INCONCLUSIVE

Single-wheel camera-truthed arcs (swept angle is proportional to that
wheel's travel): left mean |dheading| 90.93 sd 1.64, right 91.91 sd
0.85 (n=6 each), ratio 0.9893. The difference of means (0.98 deg) is
within its own combined standard error (~0.76), i.e. t~1.3 — NOT
resolvable. It also points OPPOSITE to the straight-leg decomposition,
which implied the left wheel long by 0.78%. Because the two methods
disagree and the direct one cannot arbitrate, **no per-wheel
`travel_calib` was baked** — baking the wrong sign would double the
error rather than cancel it. This is the reason the fallback named in
the ticket's own plan was not taken.

### Step 2 — twist-hold sweep: converged

Alternating +-600 mm legs at cruise 100, camera-truthed, gain applied
live via `SET twist_hold_gain`:

```
gain 2 (old default)                    mean |dh| 2.88 deg / 18 legs
                                         (g3-cruise100/, g3-cruise100-x12/)
gain 4                                   mean |dh| 2.10 deg / 12 legs
                                         (twist-4-x12/)
gain 6                                   mean |dh| 1.67 deg /  6 legs
                                         (twist-6/)
gain 4 BAKED + fresh camera calibration  mean |dh| 1.62 deg / 12 legs
                                         (baked-twist4-x12/)
```

(All paths under `captures/session-b-20260905/`.)

Two caveats travel with those numbers: (a) a 6-leg run at gain 4 gave
0.98 deg and did NOT replicate at 12 legs — six legs does not resolve
anything at this noise level, and the 0.98 must not be quoted; (b)
gain 6's 1.67 is a 6-leg figure and is therefore NOT comparable to the
12- and 18-leg ones — it is not evidence that 6 beats 4, and that arm
needs a 12-leg rerun before it can be compared.

### Step 3 — the bar

Ticket 012's criterion is six of six 600 mm legs within 1 deg both
ways. On the final baked firmware: **4 of 12 legs within 1.0 deg,
worst 4.16 deg. NOT MET.** The converged value is `twist_hold_gain = 4`
(baked by ticket 015, commit 05de015); it improves the error from 2.88
to 1.62 deg without reaching the bar.

### Trade recorded for ticket 016

On the baked build: G3 peak improved 148-154 -> 118, max accel
861-954 -> 637, max decel 1061-1092 -> 477 (now PASSING), but **G4
first-tick REGRESSED from 34-51 (passing) to 110 (failing)** —
plausibly the higher twist gain's larger differential correction on
the first tick, UNVERIFIED.
