# Change plan — position moves and the velocity path in pxt-nezha-diffdrive

**Written** 2026-10-27, rewritten the same day to two sprints, from
[motor-path-review.md](motor-path-review.md) and the measurements in
`nezha-esp32/docs/` (`motor-protocol.md` §7-8, `microbit-comparison.md`
§7, `fifty-cm.md`). Scope: the micro:bit firmware only. The ESP32 stays a
bench instrument; its port layer and the shared-platform work are deferred
(§4) and nothing here depends on them.

Every change names the files it touches and the measurement or test that
accepts it. Sprint 1 is host-only and ends with a hex that builds. Sprint 2
is the hardware acceptance that decides the defaults.

## 0. Decisions needed before sprint 1 is planned

| # | Decision | Recommendation |
| --- | --- | --- |
| D1 | **Watchdog semantics under a position move.** Today "the robot only moves while something ticks". A built-in move completes on its own. Keep the invariant (the watchdog hard-stops a live move 100 to 150 ms after the last tick) or let a started move complete unattended? | Keep the invariant. It is what students and the README already know, and `0x5F` makes the stop clean (§7a: 0.6 to 9 mm of travel after the command). |
| D2 | **Velocity actuator through the brick.** Keep `0x60` (integer percent plus the sigma-delta dither), or switch the kernel's speed writes to `0x77` + `0x70` mode 3 (1 °/s, two frames per change, self-stopping if not refreshed)? | Build it behind a config switch (`speed_path`), default `0x60` until the sprint 2 A/B says otherwise. |

## 1. What the measurements changed about the design

The review's §6 design stands. Three measured facts sharpen it:

- **The hard stop is only worth sending from speed.** `0x5F` and `0x60 0`
  travel the same 0.6 mm from the 8 % floor; from 30 % the hard stop
  travels 2 mm against 11, from 100 % 9 mm against 102. So the kernel's
  own ramp-to-floor stop stays as it is; `0x5F` goes on every path that
  stops a wheel that is still moving (position moves, `STOP`, `ESTOP`,
  the watchdog, fault context).
- **The kernel's integral term is a position corrector, not a speed
  regulator.** With `pid_ki 0` the kernel lands as well at 248 mm/s and
  overshoots 24 mm once in four at 792 mm/s, where feed-forward saturates
  at 100 %. A cruise ceiling below saturation (`v_max` ≤ 0.9 × full-duty)
  removes the case the integral was covering. Kernel code is untouched;
  only defaults move, and only after a two-wheel run.
- **The brick has a fine velocity command.** `0x77 <°/s>` then `0x70`
  mode 3 runs at the commanded speed within 1 % up to about 980 °/s,
  re-issuable mid-run including reversal, 1 °/s resolution against
  `0x60`'s 11.5 °/s. A `0x77` write alone does not retarget; both frames
  go out per change. This is D2.

## 2. Sprint 1 — position moves on the host (no hardware)

Goal: a hex that builds, the host suite green, the sim tour closing with
`position_mode 1`, the "no `0x60` during a move" regression pinned, and
the brick's measured behaviour written into the repo so the simulator and
the tests cite something in-tree.

| # | Change | Where | Accepts when |
| --- | --- | --- | --- |
| C1 | `PositionMotor` port interface: `supportsPositionMove()`, `positionQuantum()` [counts], `beginMove(deltaCounts, degPerSec)`, `hardStop()`, `moveLive()`, `driven()`. | new `src/core/position_motor.h` (libc only) | C++11 syntax gate; listed in `pxt.json`. |
| C2 | `NezhaMotorPort` implements C1: `0x77 <°/s>` (written only on change, per port) then `0x70` dir mode 2 with integer degrees; `hardStop()` = `0x5F`; a move-live latch makes `setDuty()` a no-op and `driven()` true until completion, `hardStop()` or e-stop; `emergencyStop()` sends `0x5F` first when live. Quantum 10 counts. | `src/platform/nezha_port.h/.cpp` | host tests against C4: frames byte-exact per the C11 reference; zero `0x60` frames while live; e-stop sends `0x5F` then `0x60 0`. |
| C3 | Under D2: `speed_path 1` in `NezhaMotorPort`. `setDuty(pct)` becomes `0x77 round(pct × 11.5)` (only on change) plus `0x70` dir mode 3 with a run long enough to outlast the next tick (n = 1, 0.7 s); the existing deadband, dwell, slew and throttle stay in front of it; the dither is bypassed (no longer needed at 1 °/s); stop from speed is `0x5F`. `speed_path 0` is byte-identical to today. | `src/platform/nezha_port.h/.cpp` | host test: a ramp 0 → 60 → 0 % produces the expected `0x77`/`0x70` pairs and one `0x5F`; `speed_path 0` frame log unchanged against the current pin. |
| C4 | Simulated brick learns the sniffed behaviour: per-port `0x77` store; `0x70` modes 0/1 (turns), 2 (degrees, ramp to the count), 3 (timed run at the stored °/s, time (10·n − 3) × 100 ms); `0x5F` hold within 5°; `0x60 0` during a move ramps at v²/2a and drops the target; nonzero `0x60` takes over; a second `0x70` supersedes from the current position; `0x77` alone does not retarget. | `tests/host/sim_nezha_bus.h` | new `test_sim_nezha_bus_brick_opcodes.py` reproduces every row of the C11 reference that has a measured number. |
| C5 | `MotionEngine::PositionMove`: per-wheel count targets from the existing segment maths (`rotationalSlip`, `effectiveTrackWidth`), rounding to the port quantum split across the two wheels, per-wheel °/s proportional to each wheel's share of the dominant distance, two `beginMove()` calls back to back; service keeps `kernel_.step()` for encoder reads and odometry; completion = both wheels within `arriveDist`/`arriveYaw` and `atRest()`; deadline, e-stop and a stall test (no progress for `stallWindow` while a move is live) end it with `hardStop()`. Exactly one of seg_/hold_/nudge_/posMove_ live. | `src/motion/motion_engine.h/.cpp`, new `src/motion/position_move.h` | host tests: 50 cm straight, 90° pivot and a 300 mm / 45° arc on the sim bus land within one quantum; cancel, e-stop and deadline each produce `0x5F` within one tick. |
| C6 | Config ordinals `position_mode` (0 kernel, 1 built-in for straights and pivots, 2 built-in for arcs too; default 0 until sprint 2 accepts 1) and, under D2, `speed_path` (0 `0x60`, 1 `0x77`+`0x70` mode 3). Generated block enum, descriptor table, `set config` names. | `src/comms/config_fields.h`, `tools/gen_config_field_enum.py`, `src/blocks/motion.ts`, `src/shims.cpp` config table | `test_config_descriptor_table.py`, `test_config_surface_single_source.py`. |
| C7 | Routing: `WHEELS_X`, `MOVE_X`, `GO_TO_R/W`, `move`, `goTo`, `whileMoving`, pivots use `PositionMove` when the mode allows and the composed board's ports support it; `WHEELS_V`, `MOVE_V`, `setWheelSpeeds`, `driveTwist`, line following never do. `isDriving()` true during a live move. `STATUS` carries a position-move flag so `tools/mb50.py` can tell which path ran. | `src/comms/wire_handler.cpp`, `src/shims.cpp`, `src/blocks/motion.ts` | `test_wire_motion_verbs.py` extended; `test_continuous_drive_command_looks_active.py` still passes. |
| C8 | Every stop path hard-stops live moves first: `Rig::softStop()`, the watchdog (per D1), `endMove()`, `STOP`, `ESTOP`, `configureWiring()`, and `diffdrive_emergency_motor_stop()`, which also widens to M1 to M4. | `src/shims.cpp`, `src/platform/board_nezha.cpp`, `src/platform/nezha_port.cpp` | host test: a live move plus 200 ms without a tick produces `0x5F` on both ports; source pin for the fault frame's port range. |
| C9 | Jerk path applies the speed floor (ramp down to the floor, never through it). | `src/motion/velocity_shaper.cpp:104-106` | `test_velocity_shaper.py`: with `jerk > 0` the last nonzero command is ≥ floor. |
| C10 | `nudge()` and `beginNudgeWheels()` take hundredths of a millimetre. | `src/blocks/motion.ts:364`, `src/shims.cpp:740` | host test on the shim arity pin; sim parity. |
| C11 | Brick protocol reference in-tree: a knowledge doc with the opcode map (`0x60`, `0x77`, `0x70` modes 0 to 3, `0x5F`, `0x5D`, the `0x46/0x47` reads, the `FE` mode brackets), the UART frame each one becomes, and the measured tables (§7a stop travel, §7b fine velocity, §7c kernel with `pid_ki 0`, the 50 cm table), citing `nezha-esp32/docs/motor-protocol.md` as the source. The three CSVs behind the tables (`mb_probe_stops1.csv`, `mb_probe_fine1.csv`, the `mb50_ffcmp2_*` summaries) copied under `docs/code-review/2026-10-27/data/`. | new `docs/knowledge/2026-10-27-nezha-brick-opcodes.md`, `docs/code-review/2026-10-27/data/` | C4's test and `src/platform/DESIGN.md` cite it; no measured claim in the plan lacks a file in-tree. |
| C12 | `tools/make_deploy.py` and `pxt.json` carry the new files; `src/DESIGN.md` §3/§7 and `src/platform/DESIGN.md` describe the position path, the latch and (under D2) the two speed paths; README's tick contract states D1. | `pxt.json`, `tools/make_deploy.py`, docs | `test_pxt_manifest_completeness.py`; `clasi design validate`. |

Independent of the rest and shippable out of process today: C9, C10, C11,
and the M1-to-M4 half of C8.

Order inside the sprint: C11 first (it is the spec the tests cite), then
C1 → C4 → C2 (→ C3) → C5 → C6 → C7 → C8, with C9, C10, C12 anywhere.

## 3. Sprint 2 — position moves on the bench and a robot (hardware)

Goal: the acceptance bars in
`clasi/issues/position-moves-through-the-motors-own-position-loop.md` met,
defaults set from the evidence, scaffolding removed. Needs the one-wheel
bench rig and one two-wheel robot under the camera.

| # | Change | Accepts when |
| --- | --- | --- |
| C13 | Bench rig (one wheel, 83 mm): `tools/mb50.py --mode position` repeats `fifty-cm.md` at 30/60/100 %, four trials each direction, the `STATUS` flag from C7 confirming the path. | every trial within 0.5 mm, time at 100 % under 1.2 s. |
| C14 | Robot (two wheels, camera): 90° and 180° pivots, 600 mm legs, a 60 cm square, at `position_mode 1`; two-wheel start skew from telemetry. | encoder-side pivot error within 0.5°, no lurch; square closes better than 11 mm; skew under 10 ms; mid-leg twist recorded against the kernel's twist hold (decides whether straights need a correction). |
| C15 | Stop timing: `STOP`, `ESTOP`, watchdog during a live move, on bench and robot. | wheels at rest within 200 ms, travel after the command within the §7a table. |
| C16 | Arcs: `position_mode 2` on the robot against the kernel's arcs, camera-truthed. | decides the default for arcs. |
| C17 | Under D2: `speed_path 0` against `1` on `WHEELS_V` and a 600 mm kernel leg, speed hold and heading, bench then robot. | decides the default for `speed_path`. |
| C18 | Kernel defaults for the modes that stay on the kernel, per robot: `v_floor`, `decel` ≤ 1000, `stop_distance`, `omega_floor` above stiction (≈45 °/s body), `v_max` ≤ 0.9 × full-duty so the feed-forward never saturates; `pid_ki` kept or dropped on the §7c evidence with two wheels. | baked per robot with the captures cited. |
| C19 | Remove `RUN brick`, `brickx`, `brickraw`, `brickread`, `brickstop` from `test/test.ts`; `tools/mb50.py`'s brick mode moves onto the real `RUN` verbs. | test build has no raw `pins.i2c*` outside the `BusGuard`. |
| C20 | Defaults flipped on the evidence (`position_mode 1` or 2, `speed_path` per C17); student-facing block docs and README describe the new move; captures from C13 to C17 land in-tree beside the knowledge doc; a sprint postmortem records what the camera said. | `position_mode` default matches the accepted mode; every number in the postmortem has a capture. |

## 4. Deferred: the ESP32

Not in these two sprints. The ESP32 stays the bench instrument and the
sniffer it is today (`nezha-esp32/`). When it comes back, the review's
§5 still applies and the work splits as before: a port layer
(`MotorUartBus` + `SimMotorUart`, `NezhaUartMotorPort` implementing
`Motor` + `PositionMotor`, the internal-MCU power client, the bench
firmware rebuilt on them with the servo-mode abort fixed and the reset
frame deleted), then the platform (a PlatformIO library pointing at this
checkout, Arduino `Clock`/`Sleeper`, a board file, a PXT-free `Rig`, a USB
CDC transport, one script for both rigs). C1's interface is written so
that port layer can implement it without change.

## 5. What is deliberately not in this plan

- Changing the vendored kernel (`core/diffdrive.*`). Every change above
  keeps it byte-identical; the paired-PR regime is untouched.
- The remaining ESP32 bench probes (register 0x64 after a mode select,
  `03 70` above 1000 °/s, the `0x5D` arithmetic). Nothing above needs them.
- Decoding the brick's `0x5D` absolute move beyond what the C11 reference
  records. The stack uses relative moves.
