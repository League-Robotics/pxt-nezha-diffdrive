---
status: pending
---

# `position_mode 2` arcs run both wheels at nearly the same speed on the real brick

Sprint 043 ticket 005 (zuvat, 2026-10-27, `captures/zuvat-position-2026-10-27/circle/`):
a 20 cm-radius circle as eight 45° arcs at `position_mode 2` closed within
1.4 to 2.2 mm on four of five laps (one 48 mm outlier) and 0.5° heading,
but did not follow the circle: the median left/right wheel-speed ratio was
1.07 where the geometry needs 0.56, so each arc ran as a near-straight plus
a one-wheel finish and the track was an offset octagon (radial deviation
32 mm mean, 68 mm worst). The kernel path (modes 0 and 1) followed the
circle at 10 mm radial but closed 40 to 69 mm off. Decision recorded in
the ticket: arcs stay on the kernel, default `position_mode 1`.

The engine's `PositionMove` computes proportional per-wheel °/s and the host
simulator shows both wheels finishing together
(`tests/host/test_motion_engine_position_move.py`). On hardware they do
not. Candidate causes:

- the brick keeps ONE speed store, not one per port: the sniff that mapped
  `0x77` ("per port when the port byte is 1..4") was done with one motor,
  and the position-move issue said two wheels through the brick were
  unverified. If the last `0x77` written governs both ports, the second
  wheel's speed overwrites the first's.
- the port's `0x77` dedupe (write only on change for that port) interacting
  with a shared store: after the first arc both ports hold "changed"
  values but the brick applies the last.
- the engine's per-wheel speeds being clamped to the same ceiling.

To settle: sniff two motors through the brick with the ESP32 harness
(`nezha-esp32`, `sniff` with a fake motor on one port while a real motor
sits on the other), then either write `0x77` immediately before each
port's `0x70` (no dedupe) or, if the store is global, implement arcs as
timed runs (`0x70` mode 3 at per-wheel °/s) or keep them on the kernel.
Mode 2 also costs about 57 failed I2C transactions per lap against 4
(`zuvat-i2c-fault-count-grows-during-position-moves.md`).
