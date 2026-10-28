---
status: in-progress
sprint: '042'
tickets:
- 042-002
- 042-003
- 042-004
- 042-006
- 042-007
- 042-008
- 042-012
---

# Position moves through the motor's own position loop (brick 0x70), not the velocity kernel

## The finding

The Nezha brick is not a motor driver with an encoder. It is an I2C proxy
to a smart motor that has its own speed loop and its own position loop.
The kernel's "duty" write (0x60) is a speed setpoint to that loop, and the
kernel's velocity PID is a loop wrapped around a loop. The brick also
forwards the motor's native positioning move, opcode 0x70, which lands on
the encoder count by itself.

Measured 2026-10-27 on two bench rigs (one motor on M1, 83 mm wheel, 50 cm
moves at 30 / 60 / 100 %, four trials each, both directions). Settled
error in mm, worst case over the trials:

| Path | 30 % | 60 % | 100 % |
| --- | --- | --- | --- |
| kernel `WHEELS_X`, stock profile | +3.0 | +3.4 | +3.0 (always long) |
| kernel, tuned (`v_floor 40`, `decel 1000`, `stop_distance 0.3`) | 0.8 | 0.6 | 0.6 |
| kernel, tuned + host-driven closing pulses | 0.22 | 0.22 | 0.22 (3 to 4 s per move) |
| brick 0x70 built-in move | 0.22 | 0.44 | 0.14 (0.9 s at 100 %) |
| ESP32 kit, UART direct, any strategy | 0.14 | 0.14 | 0.22 |

The kernel is limited by its 24 ms tick and integer-percent commands
through the brick; the motor's loop is not. Full data, charts and the
protocol notes: `nezha-esp32/docs/fifty-cm.md`,
`nezha-esp32/docs/microbit-comparison.md`,
`nezha-esp32/docs/motor-protocol.md`.

## Verified on the brick (test/test.ts `RUN brick`, `RUN brickx`)

- `FF F9 <port> <dir> 70 <hi> 02 <lo>`: move by integer degrees, dir 1/2.
  690° gave 6900 / 6900 / 6905 counts at 30 / 60 / 100 %.
- `FF F9 <port> 00 77 <hi> 00 <lo>`, value = percent × 9: the move speed,
  per port when the port byte is 1..4, all ports when 0; the most recent
  write to a port governs and persists. This is what makes arcs possible
  (two moves with proportional speeds).
- `46` position reads work during a move, every 20 to 40 ms.
- `5F` during a move: hard stop, 5° more travel at 50 %, at rest within
  150 ms, pending target dropped.
- `60` speed 0 during a move: stop on the motor's normal ramp (46° more at
  50 %), target dropped. `60` with a nonzero speed takes over the move.
- A second `70` during a move supersedes it, measured from the position at
  the moment it arrives.
- On the ESP32 UART, two motors given the same move 7 ms apart stayed
  within 2 to 3° of shaft of each other and both finished on the count,
  one unloaded and one with a heavy turntable.

Not yet verified: two wheels through the brick at once (the rig has one
motor on the brick).

## Proposal

Add a position-move mode to `MotionEngine`, beside the velocity kernel,
and route the position blocks and wire verbs to it. Keep the velocity
kernel for continuous modes (`setWheelSpeeds`, `driveTwist`, line
following) and as a fallback.

- **Port layer** (`nezha_port.h/.cpp`): frames for 0x77 per-port speed,
  0x70 relative move (integer degrees, direction byte), 0x5F hard stop.
  While a built-in move is live on a port, the port must write **no** 0x60
  frames: the stop-enforcement path (`stopNotTaken`, `stopEnforceCountdown`)
  re-writes zero while the wheel reads motion and would abort the move.
- **Engine**: a `PositionMove` segment with per-wheel targets in counts.
  Planning = today's segment maths (distance and yaw to per-wheel counts,
  `rotationalSlip`, track width), then integer degrees per wheel with the
  rounding split across the two wheels so the heading error is under one
  degree-step. Speeds per wheel proportional to their distances so both
  finish together (arcs). Issue the two 0x70 frames back to back. Service:
  keep reading 0x46 on both wheels every tick for odometry and progress;
  completion = both at rest within the arrival window; stall, wrong-way,
  deadline and e-stop keep their meaning. Stop = 0x5F on both; e-stop and
  the starvation watchdog must send 0x5F, because the motor keeps running
  its move if the micro:bit stops ticking (the opposite of today's
  "latched speed" hazard: the motor now finishes on its own).
- **Kernel interaction**: the kernel must not stage writes during a
  position move. Either hold it in a read-only neutral or give the port a
  "position move live" latch that drops kernel writes. Its glitch armor
  must accept the counter advancing while it was not commanding.
- **Blocks and wire**: `move`, `goTo`, pivots, `MOVE_X`, `WHEELS_X`,
  `GO_TO_*` use position mode; continuous verbs unchanged. Config: the
  brick move speed is a percent, so `cruise` in mm/s maps through
  `full_duty_velocity` and `travelCalib`.
- **Host simulator** (`sim_nezha_bus.h`): model 0x70/0x77/0x5F so the host
  tests cover the new path.
- **Profile tuning for the kernel's remaining modes**, independent of the
  above: `v_floor 40`, `decel` capped near 1000 mm/s², and the jerk path
  either applies the floor or is disabled (today it overshoots 13 mm at
  full speed because `vFloor` is skipped whenever `jerk > 0`).

## Acceptance

- 50 cm straight on the bench rig: every trial within 0.5 mm per wheel at
  30, 60 and 100 %, move time at 100 % under 1.2 s.
- 90° and 180° pivots, camera-truthed as in sprint 031: encoder-side error
  within 0.5°, no stick-slip lurch at the end.
- A 60 cm square closes better than the 11 mm recorded in sprint 031.
- Stop and e-stop during a move: wheels at rest within 200 ms.
- Two-wheel start skew through the brick measured and under 10 ms.

## Risks and open questions

- The kernel's write pipeline fighting a live move (see above) is the main
  integration hazard; the measurement that a 0x60 write takes over a move
  makes it easy to detect in a host test.
- Integer degrees: 0.72 mm per wheel on an 83 mm wheel. Split the rounding
  across wheels; accept the residual rather than chase it with pulses.
- The brick may queue or drop a 0x70 that arrives too soon after another
  frame; the vendor code pauses 4 ms after 0x5D. Measure the minimum gap.
- Slip calibration (`rotational_slip`) stays as it is; it is mechanical.

## Plan and decisions (2026-10-27)

The concrete change list is `docs/code-review/2026-10-27/change-plan.md`
(sprint 1 rows C1, C2, C4, C5, C6, C7, C12 are this issue; the review is
`motor-path-review.md` beside it). Stakeholder decisions taken 2026-10-27:

- **D1**: the starvation watchdog keeps its invariant. A live built-in
  move is hard-stopped (`0x5F`) 100 to 150 ms after the last tick, same
  as a kernel move today.
- **D2**: the fine velocity actuator is built behind a `speed_path`
  config switch, default `0` (today's `0x60`). Separate issue:
  `fine-velocity-actuator-behind-a-speed-path-switch.md`.

Scope for this issue: `PositionMotor` interface, `NezhaMotorPort`
implementation with the move-live latch, the simulated brick model,
`MotionEngine::PositionMove`, the `position_mode` ordinal (default 0
until hardware accepts it), wire/block routing with a `STATUS` flag,
manifests and DESIGN docs. Stop paths are
`every-stop-path-hard-stops-a-live-move.md`; the in-tree protocol
reference the tests cite is `nezha-brick-opcode-reference-in-tree.md`.
