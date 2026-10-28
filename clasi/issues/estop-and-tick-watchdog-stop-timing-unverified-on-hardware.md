---
status: pending
---

# ESTOP time-to-rest and the tick-starvation watchdog are UNVERIFIED on hardware

Sprint 043 ticket 002 (zuvat, 2026-10-27, `captures/zuvat-position-2026-10-27/`)
could not measure two of the stop cases from the acceptance list:

- **ESTOP**: the latch freezes telemetry (stale `vl`/`vr`, `cyc` stops),
  so time-to-rest is not observable over the wire. Travel after the
  command, inferred from the first fresh `x` after `SET estop_clear 1`,
  was 3.0 mm at 75 mm/s and 7.8 mm at 250 mm/s, consistent with the hard
  stop rows. Confirming the 200 ms bound needs an observed run (eyes,
  stopwatch or video) or telemetry that keeps streaming through the latch.
- **Tick-starvation watchdog**: the firmware's own fiber ticks the loop,
  so a silent host does not starve it; the README's "hard stop 100 to
  150 ms after the last tick" cannot be provoked from the wire. The
  `MOVE_X` deadline and `WHEELS_V` lease expiry were measured instead
  (both within 200 ms). A test hook that pauses the tick fiber, or a
  `RUN` program that does, would make it measurable.

STOP at both speeds met the bar (travel 2.9 / 8.7 mm against the 2.2 /
8.6 mm hold rows).
