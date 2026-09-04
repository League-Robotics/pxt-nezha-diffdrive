---
status: pending
---

# Segment moves end early in the first minutes after a boot

Priority: **Medium** · Found 2026-09-04 during sprint 029 ticket 007 on tovez (motor-baked firmware).

## Description

Right after a boot, four `MOVE_X` segments ended early while `WHEELS_V`
holds in the same minutes were normal:
`captures/bench-acceptance-029-20260904d/confirm-direction-3.log`
(dance: `+180` pivot rotated −1.4 deg, `−40 cm` drive went 13.4 cm),
`segment-reverse-probe.log` (`MOVE_X −50` did not move; `MOVE_X +200`
stopped after 11 mm with duty cut to 0 at 0.2 s). Fifteen later moves
in the same session (`abort-hunt-raw.log`, `field-dance-motorbake.log`)
were all clean. `MotionEngine::wrongWayCount()` read 2 before the clean
run, so two of the four were wrong-way aborts on pivots -- the scaled
margin from `Segment::wrongWay()` (25 % of the yaw target, this sprint)
is still crossed by the wheels' start-up skew on the very first moves
after boot. The two straight-line stops have no wrong-way path
(`yawTarget == 0`) and no counter in the frames explains them; the
candidates are the stall latch (`updateLatch`, 500 ms window) firing
on a slow first spin-up, or a refused `kernel_.drive()`.

## Remedy

Capture `DIAG`/STATUS `reason=` at the instant of an early end on a
cold boot (poll at 8 Hz from the send); if it is the stall latch, gate
the stall detector on the shaper having commanded above the floor for
longer than the measured lag; if wrong-way, evaluate `wrongWay()` only
after the dominant axis has progressed a minimum distance. Host test
with a lagged, skewed wheel model (see `tests/host/test_profile_probe.py`).
