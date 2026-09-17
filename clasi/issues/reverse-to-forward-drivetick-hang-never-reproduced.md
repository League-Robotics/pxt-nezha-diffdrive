---
status: pending
---

# The reverse-to-forward `driveTick()` hang was never reproduced, and its cause is unknown

Carried out of sprint 039 ticket 002, which closed on its other defect
(the stale `STATUS active`, fixed and confirmed on hardware). This is
the part that did not resolve.

## What was seen, once, and never since

MEASURED vevov 2026-09-15 by the nezha-robot-template session,
`captures/calibratel-vevov-20260915/bench-log.md` runs 7-8: a
`driveTick()` loop immediately following a direction reversal ran only
16-17 of its 40 commanded ticks AND never printed the RUN job's own
post-loop line. Twice, on the build
`calibrate-l-bench 1.20260912.8`.

## What the repro run established

MEASURED vevov 2026-09-16 by team-lead,
`captures/039-002-repro-20260915/repro-results.md`, on the sprint build
(`vevov-nudgehang0915`): **22 reversal transitions, 0 failures** — 14
wheels-up, 8 on the floor under load, at both the -4/+4 and -10/+10
cm/s speeds the original used. Every run completed 40 of 40 ticks, and
every completion line arrived, with `runDrops=0`/`emitDrops=0`.

So: it does not reproduce on this build. That is NOT the same as fixed.

## Why it cannot be called fixed

The sprint build differs from the original by more than the bench verb:
it carries ticket 002's Defect 1 fix, which added
`engine.settleToRest()` to `Rig::softStop()` — a change to the very
stop path each of those loops ran through. So the hang may have been
cured incidentally, or it may simply not have been triggered. Eight
loaded transitions is a thin sample against a fault that appeared twice
in one session and never again.

The leading hypothesis (a load-dependent I2C stall inside
`kernel.step()`, holding `busGuard` on the loop's own fiber) is in
`docs/knowledge/2026-09-15-reverse-to-forward-drivetick-hang-diagnosis.md`.
It is UNVERIFIED — neither confirmed nor refuted.

## The test that would settle it

Flash the ORIGINAL firmware back onto vevov and try to reproduce it
there, using the same held-open-socket harness (see
`repro-results.md` — `mbdeploy connect` closes after the ack and drops
later lines, which imitates this exact bug).

- Reproduces on the old build, not the new one -> the Defect 1 fix
  explains it, and this closes.
- Reproduces on neither -> the trigger is something neither session
  isolated, and the honest record is an intermittent fault seen twice
  on 2026-09-15.

## Related, and possibly the reason it was never caught in the act

`watchdog-freshness-is-armed-before-the-bus-guard-is-acquired.md`: the
starvation watchdog is re-armed by a fiber that then blocks, so the one
mechanism meant to stop the wheels during a hang can be starved by the
hang itself. Worth testing in the same session.
