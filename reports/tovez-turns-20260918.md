# tovez turns, 2026-09-18 — the board is running uncalibrated

**Board:** tovez, main playfield, over nada's serial daemon.
**Firmware:** `1.20260914.1`, `ID` profile `calibration`.
**Data:** `reports/tovez-turn-cal-20260918/` (16 pivots, as found),
`reports/tovez-turn-cal-20260918-fixed/` (9 pivots, fitted values SET
live). Convention gate in `captures/tovez-turns-20260918/center.log`.

## Why a commanded turn is missed

16 camera-scored in-place pivots at the square tour's own pivot speed
(188 mm/s), from rest, signs alternating:

| commanded | n | mean error | min | max |
|---|---|---|---|---|
| +90 | 4 | **+3.41°** | +1.7 | +6.5 |
| −90 | 4 | **−2.36°** | −2.9 | −1.7 |
| +180 | 4 | +0.18° | −1.5 | +1.3 |
| −180 | 4 | −0.55° | −1.6 | +0.8 |

Two things to read here.

**Every 90 overshoots in its own direction.** +90 is always positive,
−90 always negative, across all four repeats each. A signed constant
like that is not noise and it does not cancel over a lap — it is
**overrun**, the robot continuing to turn after the command is
satisfied.

**The 180s are not "fine" — they are two errors cancelling.** The fit
over all 16 is:

```
camera = 0.972 x commanded + 5.41 deg
```

A gain of 0.972 under-turns by 2.8% (−2.5° at 90, −5.0° at 180); the
+5.41° offset is constant regardless of angle. At 180 they cancel
(−5.0 + 5.4 ≈ +0.4). At 90 they do not (−2.5 + 5.4 ≈ +2.9). **A tour
built from 90s gets the worst possible combination of the two.**

## The cause: neither correction is on the board

`GET` on the running firmware:

```
get rotational_slip 0.998        <- the fit wants 0.970
get stop_distance  0.000000      <- the fit wants 5.4 mm
get lag            0.000000
get pid_kp         0.000000
```

`rotational_slip` and `stop_distance` are precisely the two knobs that
cancel the two terms above, and both sit at their uncalibrated
defaults. The fitted values are in family with the rest of the fleet —
tigez measured slip 0.9617 / overrun 5.5 mm (2026-09-03), and tovez's
own baked value is 0.962 (2026-09-05). **The calibration is real and
correct; it is simply not on this board.** `ID` reports build profile
`calibration`, not `tovez`, consistent with a hex built from a generic
profile.

## Confirmed by applying it live

Same sweep, same cruise, with `SET rotational_slip 0.9701` and
`SET stop_distance 5.4`:

| | as found (n=16) | fitted values SET (n=9) |
|---|---|---|
| fit gain | 0.972 | **0.986** |
| fit offset | **+5.41°** | **+1.79°** |
| mean abs error | 1.92° | **1.01°** |
| +90 mean error | **+3.41°** | **+1.17°** |
| −90 mean error | **−2.36°** | **+0.44°** |

The signed 90° overshoot — the thing that accumulates around a square —
is essentially gone, and mean error halves. That is the diagnosis
confirmed on hardware, not a model.

**Caveat:** the confirming run was cut short at 9 of 16 turns when the
serial carrier dropped (`Errno 32` broken pipe at the end), so it is 2-3
repeats per angle, not 4. The direction of the result is unambiguous;
the exact residual is not, and its own re-fit (slip 0.9564 /
stop_distance 7.24) should **not** be chased — that is 9-turn noise.

These SETs are live-only and do not survive a reboot.

## The encoders cannot see it

Per-turn, the encoder-believed error is far smaller than the camera's
(e.g. turn 1: camera +6.5° vs encoder +1.4°). The robot believes it is
turning accurately while physically over-turning two to four times
more, so it cannot correct itself and closed-loop odometry will not
save a tour.

## The wiggle

Commanded pivot cruise is 188 mm/s. Measured peak wheel speeds run
**193–245 mm/s**, up to +30% over, with left and right peaks differing
by as much as 45 mm/s on the same pivot (turn 1: left 200, right 245).
The 90° pivots never reach a cruise plateau at all — the traces in
`wheel-speeds.png` are pure accel→decel triangles, so the whole turn
happens inside the ramp where the speed loop is least settled.

`pid_kp` is **0.000000** with `pid_ki 6` — an integral-only speed loop,
which overshoots and hunts by construction. That is a credible source
of the wiggle seen while driving, and it is UNVERIFIED: the test is a
`WHEELS_V` step-response capture at fixed speed, which needs no field
and cannot crash anything.

## Next

1. Reflash tovez with its own profile so slip and stop_distance are
   baked, rather than SET live. One flash.
2. Re-run this sweep to confirm, then one square tour.
3. Separately, characterise the speed loop (`pid_kp 0`) against the
   wiggle.
