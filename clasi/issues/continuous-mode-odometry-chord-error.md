---
status: pending
sprint: '006'
---

# Continuous-mode driving never updates odometry; next pose read integrates one chord

Priority: **Medium** — code review 2026-08-23, R-09 (BLK-05; CONFIRMED with
scenario correction in `verify-blocks.md`).

In velocity mode (`driveTwist`/`setWheelSpeeds` + a tick loop) nothing calls
`odomUpdate()` — all nine call sites are move-path or pose-read
(`shims.cpp:213-233`, gates at :421-424/:466-469). The next `pose x/y`
read integrates the entire driven interval as **one chord**: drive a full
circle in an unconditional tick loop (e.g. `testrig.ts:118-120` pattern)
and pose reports approximately the whole path length instead of ~0.

Any program that drives continuously for a while and then reads pose gets
geometry that is simply wrong, with error growing with curvature × interval.

## What to do

Fold `odomUpdate()` into the continuous tick path (`tickDrive`'s velocity-
mode branch), preserving the exactly-one-ticker-per-move constraint. Add a
host test: circle at constant twist, assert pose returns near origin.
