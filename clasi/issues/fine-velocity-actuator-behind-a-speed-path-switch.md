---
status: pending
---

# Fine velocity actuator through the brick, behind a `speed_path` switch

The brick forwards the motor's own velocity command: `0x77 <°/s>` then
`0x70` mode 3 (timed run) runs the wheel at the commanded speed within
1 % up to about 980 °/s, with 1 °/s resolution, re-issuable mid-run
including reversal. Today's actuator `0x60` is integer percent, which is
11.5 °/s per step, and the port dithers between steps (sigma-delta) to
fake resolution. A `0x77` write alone does not retarget; both frames go
out per change, so each change costs two I2C frames.

MEASURED 2026-10-27, micro:bit rig (one motor on M1, 83 mm wheel):
`nezha-esp32/docs/microbit-comparison.md` §7b and
`nezha-esp32/docs/data/mb_probe_fine1.csv` (copied in-tree by
`nezha-brick-opcode-reference-in-tree.md`): `0x77` 60 → 60.5 °/s,
300 → 302, 905 → 909.5, saturating near 980.

## Change

Stakeholder decision D2 (2026-10-27): build it behind a config switch,
default off. `change-plan.md` rows C3 (host) and C17 (hardware A/B).

- Config ordinal `speed_path`: 0 = `0x60` (byte-identical to today),
  1 = `0x77` + `0x70` mode 3.
- In `NezhaMotorPort::setDuty(pct)` with `speed_path 1`: `0x77
  round(pct × 11.5)` only on change, then `0x70` dir mode 3 with a run
  long enough to outlast the next tick (n = 1, 0.7 s, so a starved
  firmware self-stops). The existing deadband, reversal dwell, slew and
  write throttle stay in front of it; the sigma-delta dither is bypassed.
  Stop from speed is `0x5F`.
- Simulated brick (`tests/host/sim_nezha_bus.h`) models mode 3 at the
  stored °/s so a host test can pin the frame sequence.

## Acceptance

- Host: a ramp 0 → 60 → 0 % at `speed_path 1` produces the expected
  `0x77`/`0x70` pairs and one `0x5F`; at `speed_path 0` the frame log is
  unchanged against the current pin.
- Hardware (sprint 2): `speed_path 0` against `1` on `WHEELS_V` and a
  600 mm kernel leg, speed hold and heading, decides the default.
