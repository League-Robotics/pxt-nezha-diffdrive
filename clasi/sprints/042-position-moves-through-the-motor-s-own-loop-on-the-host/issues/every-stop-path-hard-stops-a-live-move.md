---
status: in-progress
sprint: '042'
tickets:
- 042-009
---

# Every stop path hard-stops a live move; the fault stop covers M1 to M4

Every stop in the firmware today sends `0x60 0`, which the motor treats
as a speed setpoint of zero and obeys on its own ramp. With a built-in
position move live (brick `0x70`) that is also the wrong frame: it drops
the target and ramps. The brick's `0x5F` is a hard stop (servo-mode hold
at the current count) and the right frame whenever a wheel that is
moving must stop now.

MEASURED 2026-10-27, micro:bit rig, `nezha-esp32/docs/microbit-comparison.md`
§7a, `mb_probe_stops1.csv`: travel after the stop command, ramp vs hard,
0.6 / 0.6 mm at 8 %, 2.8 / 1.4 at 15 %, 11.1 / 2.2 at 30 %, 41.7 / 4.9 at
60 %, 101.9 / 8.6 at 100 %. Identical at the kernel's floor, 5 to 12×
shorter above it. So the kernel's own ramp-to-floor stop is untouched;
`0x5F` goes on every path that stops a wheel still moving.

Also: `diffdrive_emergency_motor_stop()` in `board_nezha.cpp` stops
ports M1 and M2 only. A robot wired on M3/M4 (the wiring hooks allow it)
is not stopped by the fault-context stop. Review finding F7.

## Change (`change-plan.md` C8)

- `Rig::softStop()`, the starvation watchdog (decision D1: it keeps its
  invariant and hard-stops a live move), `endMove()`, `STOP`, `ESTOP`,
  `configureWiring()` and `diffdrive_emergency_motor_stop()` call the
  port's `hardStop()` first when a move is live or the wheel is moving
  above the floor, then the existing `0x60 0`.
- The fault stop widens to M1 to M4.

## Acceptance

- Host test: a live position move plus 200 ms without a tick produces
  `0x5F` on both ports; `STOP`/`ESTOP`/`endMove()` during a move produce
  `0x5F` within one tick.
- Source pin on the fault frame's port range (M1 to M4).
- Hardware (sprint 2): wheels at rest within 200 ms of `STOP`/`ESTOP`
  during a move; travel after the command within the §7a table.
