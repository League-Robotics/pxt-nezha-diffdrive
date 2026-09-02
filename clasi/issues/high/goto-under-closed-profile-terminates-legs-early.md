---
status: pending
sprint:
---

# `RUN:goto` under the closed profile terminates legs 5–11 cm in, with a clean `GOTO:end` and no latched state

## Summary

During sprint 020's goToWorld arrival campaign (vevov, playfield,
2026-08-26/27, firmware 67455bf), **5 of 15 `RUN:goto` calls ended the
leg 5–11 cm after it started** — `GOTO:end` emitted normally, believed
pose honest (camera agreed within ~1 cm), target still 40–80 cm away.
Retrying the same target always advanced another ~10 cm or completed.
Three full 4-leg `RUN:tour:world` runs in the same session — same
`goToWorld()` code path, but the **open** profile (speed 20) instead of
`closedLoopProfile()` (speed 40, ramp 180 ms) — had **zero** aborts.

Evidence: `captures/gotoworld-arrival-20260826.csv` (abort log with
seeds, targets, stop points, and the in-session STATUS lines).

## What it is not

- **Not the move deadline.** One abort was timestamped: the leg died at
  t = 0.50 s against a computed budget of ~4.3 s
  (`startGoTo()`: `180/120 + 42.6/40 + 1.5`).
- **Not a latched stall or e-stop.** `STATUS` immediately after two of
  the aborts (same program lifetime — the gauti serial path does not
  reset the target on port open): `ready=1 active=1 connL=1 connR=1
  otos=1 wedge=0 flags=31 i2cf=1` — flags 0x31 is ready|connL|connR
  only; kFlagStallHalted (bit 2), kFlagEstopped (bit 1) and
  kFlagLeaseExpired (bit 3) all clear.
- **Not location-bound.** Stop points were spread across the field
  (x ≈ −40 … −15 on different legs); a later completed call drove
  clean through every earlier stop point.
- **Not pivot-specific.** It happened both after `goToWorld()`'s
  internal turn-first pivot and after a separate `RUN:face` had already
  aligned the bearing to ~1°.

## Remaining suspects

`MotionEngine::serviceMove()` ends a move on
`(distDone && yawDone) || expired || out.stallHalted || wrongWay ||
out.estopped`. With `expired` ruled out by timing and the latched flags
clear afterwards, the candidates are:

- **`wrongWay`** — `wrongWayCount_` exists on the engine
  (`motion_engine.h:318`) but is not surfaced by any wire verb, so it
  could not be read from the bench. Surfacing it (STATUS or a DIAG
  field) turns the next occurrence into a one-line diagnosis.
- **A stall that trips and auto-clears** (`stall_clear`, sprint 007)
  before STATUS is read.

The closed profile's higher accel (`setRampMs(180)`, speed 40) is the
discriminating variable — a wheel-slip transient at ramp-up would look
like either of the above.

## Suggested first step

Surface `wrongWayCount_` (and the stall-halt event count, if one
exists) in `STATUS`, reflash, and re-run five `RUN:goto` hops under the
closed profile. One counter incrementing at the moment of an early
`GOTO:end` settles the attribution without any camera work.

## Impact

`RUN:goto` is the repositioning verb between campaigns and the path
students' `goToWorld` blocks exercise at speed. A one-in-three chance
of silently stopping a third of the way into a leg makes closed-profile
gotos unusable unattended (sprint 020 worked around it by retrying
until completion; the retries converge because each call re-plans from
the OTOS).
