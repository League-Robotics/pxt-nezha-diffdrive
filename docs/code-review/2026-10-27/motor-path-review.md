# Code review — the motor path, micro:bit and ESP32 (2026-10-27)

**Scope.** Everything between "a move is requested" and "bytes reach the
smart motor, encoder counts come back": on the micro:bit,
`blocks/motion.ts` → `shims.cpp` (`Rig`, `tickDrive()`) →
`motion/motion_engine.*` (`Segment`, `VelocityShaper`) →
`core/diffdrive.*` (the vendored kernel) → `platform/nezha_port.*` →
`platform/i2c_bus.h` → the Nezha brick → the motor; on the ESP32,
`nezha-esp32/src/main.cpp` (`benchGoto()`, `motorTransact()`) →
`motor_protocol.h`, `pid.h`, `profile.h` → UART2 through the CD4052 mux →
the motor. Secondary: `tests/host/sim_nezha_bus.h`, `test/test.ts`'s
`RUN brick`/`brickx` handlers, `nezha-esp32/tests/`.

**Code state.** `pxt-nezha-diffdrive` master at `7cd5c8d` plus the
uncommitted `test/test.ts` brick handlers; `nezha-esp32` as of
2026-10-27 (not under version control). Nothing under `src/`, `tests/` or
`nezha-esp32/src/` was changed by this review.

**Asked for.** Review the existing micro:bit motor path in the light of
the ESP32 bench work and the finding that the motor's own position loop
lands moves on the encoder count; work out what it takes to make the
ESP32 a separate hardware platform for the whole stack, motor path
included; produce the findings that become issues and a sprint arc.

**Method.** Per [guidelines.md](../guidelines.md). Every claim marked
MEASURED names its artifact in `nezha-esp32/docs/` (`motor-protocol.md`,
`motor-characterization.md`, `microbit-comparison.md`, `fifty-cm.md`,
and the CSVs under `docs/data/`). Claims from reading the code say so.
Open items say UNVERIFIED and name the probe that settles them. Findings
were checked against `clasi/issues/**`; the one open issue this review
overlaps,
`clasi/issues/position-moves-through-the-motors-own-position-loop.md`,
is the proposal this review validates and extends, not a duplicate.

**Totals.** 2 Critical · 7 Major · 9 Minor · 6 Suggestion, plus one
platform assessment (§5) and one design proposal (§6).

---

## 0. Summary

The micro:bit stack closes its own velocity loop around the Nezha
smart motor at 24 ms with integer-percent commands. The motor already
runs its own speed loop (the brick's `0x60` "duty" is a speed setpoint
to that loop) and its own position loop (brick `0x70`, UART `03 67`).
Both were known from the vendor's block API; the brick's interface
(integer percent, two 4 ms select-and-read cycles per tick) was judged
too coarse to build on, so the kernel was built to close the loop
itself. The bench result that changes this is that the brick forwards
the motor's position loop faithfully, and that loop lands within one
encoder count at any speed, loaded or not. MEASURED, both rigs,
2026-10-27:

| 50 cm straight, worst error over 4 trials (mm) | 30 % | 60 % | 100 % | time at 100 % |
| --- | --- | --- | --- | --- |
| micro:bit kernel, stock profile | +3.0 | +3.4 | +3.0 | 1.4 s |
| micro:bit kernel, tuned (`v_floor 40`, `decel 1000`, `stop_distance 0.3`) | 0.8 | 0.6 | 0.6 | 1.4 s |
| micro:bit kernel, tuned + host-driven closing pulses | 0.22 | 0.22 | 0.22 | 3.2 s |
| micro:bit, brick built-in move (`0x70`) | 0.22 | 0.44 | 0.14 | 0.9 s |
| ESP32, UART direct, any of four strategies | 0.14 | 0.14 | 0.22 | 1.1 to 1.6 s |

(`nezha-esp32/docs/fifty-cm.md` §1 to §3.) The kernel's residual is
one 24 ms tick of travel at the floor speed plus the motor's own stop
ramp; the built-in move has neither term. The same mechanism explains
the sprint 031 pivot residual (sd 1.8°, both signs): pivots approach
at an `omegaFloor` that commands about 2 % duty against a motor that
does not move below 5 %, so the last part of every pivot is stick-slip
with the integrator winding up (§4.C, F11).

The right change is the one the open issue proposes: add a
position-move mode beside the velocity kernel, route straights and
pivots through the motor's own loop, keep the kernel for continuous
driving, arcs and as a fallback. This review confirms the proposal,
finds the two integration hazards that will break it if not designed
in (the kernel's stop-enforcement path re-writes `0x60 0` every tick
while a wheel is moving, which aborts a built-in move; and the
starvation watchdog and e-stop paths send the ramp stop, not the hard
stop), and specifies the seam so the ESP32 implements the same
interface over UART.

On the platform question: `core/` and `motion/` already compile with
libc only and are proven on the host at C++11; `board.h` is
host-portable; most of `comms/` is too. What the ESP32 needs is its
own `platform/` set (a UART motor bus with the mux, a motor port that
implements `DiffDrive::Motor` plus the new position-move port, the
internal-MCU power switch, Clock/Sleeper for Arduino) and a transport
plus main loop in place of the CODAL protocol fiber. `blocks/` has no
ESP32 equivalent and does not need one for the first milestone. The
bench firmware in `nezha-esp32/src/main.cpp` has the protocol right
and the structure wrong for reuse: one 1000-line file with the bus,
the mux, the power switch, the bench, the display and the buttons
interleaved. The host-testable parts (`motor_protocol.h`, `pid.h`,
`profile.h`) are clean and carry over.

---

## 1. The two motor paths, side by side

| | micro:bit (`pxt-nezha-diffdrive`) | ESP32 bench (`nezha-esp32`) |
| --- | --- | --- |
| Transport to the motor | I2C 0x10 to the brick MCU, which speaks UART to the motor | UART2 115200 8N1 directly, one bus for four ports through a CD4052 mux |
| Speed command | brick `0x60 <dir> <pct>`, integer percent (1 step = 11.5 °/s) | `03 6E <int16 tenths of %>` (0.1 % steps = 1.15 °/s) |
| Position read | select `0x46`, 4 ms settle, read 4 bytes | `02 46`, 2.3 ms round trip |
| Built-in move | brick `0x70` (integer degrees, mode byte) with speed via `0x77` (pct × 9) | `03 67 11 00 <tenths int32> <pct×9 int32>` in servo mode |
| Hard stop | brick `0x5F` (MEASURED: 5° more travel at 50 %, at rest in 144 ms) | UNVERIFIED which UART frame the brick's `0x5F` maps to |
| Control loop | 24 ms kernel tick, two 4 ms settle sleeps per tick | 5 to 7 ms loop in `benchGoto()` |
| Who closes the loop today | the kernel's velocity PID around the motor's own speed loop | the motor (builtin), or a position PID / profile on the ESP32 |
| Motor port power | the brick handles it | the ESP32 must enable it via the internal MCU (register 4 on fw 1.0.x, register 2 on 1.1.x); a freshly powered motor needs about 2 s |
| Abstraction above the wire | `DiffDrive::Motor` (14 virtuals), `I2CBus` seam, `sim_nezha_bus.h` on the host | none; `main.cpp` calls `motorTransact()` directly |

The brick's `0x77` speed register uses the same `pct × 9` scaling as
the motor's own `03 67` frame, and `0x70` lands on the count exactly as
`03 67` does, so the brick is forwarding the motor's native moves.
Both platforms are driving the same loop; only the resolution of the
target (integer degrees through the brick, tenths on the UART) differs.

---

## 2. What the bench established

Facts this review rests on. All MEASURED on the two rigs on
2026-10-27 unless marked otherwise; artifact in parentheses.

1. **Speed is linear in the command**, 11.5 °/s per percent, same both
   directions within 3 %, unloaded and under the turntable's inertia
   (`motor-characterization.md` §1, §5; `docs/data/velocity_M*_*.csv`).
2. **Below about 5 % the motor does not reliably start** (3 % and 5 %
   moved in one direction only; 8 % always). A controller needs a 5 %
   floor (`motor-characterization.md` §1).
3. **Speed 0 is a ramp, not a brake**: velocity falls at about
   3400 °/s² unloaded, 2500 to 2900 °/s² loaded, so travel after a stop
   command goes as v²/2a (20° from 30 %, 152° from 100 % unloaded;
   24° and 204° loaded) (`motor-characterization.md` §1, chart
   `stop_ramps.png`).
4. **The speed loop has a 50 to 100 ms first-order lag** and ±5 °/s
   ripple at cruise (`motor-characterization.md` §1a).
5. **The built-in move lands within 0.3° at 20, 50 and 100 %**, loaded
   and unloaded; a position PID with a 5 % floor and 0.2° to 0.3° band
   lands on the exact count (`motor-characterization.md` §2, §2a).
6. **Through the brick, `0x70` degrees mode gave 6900 / 6900 / 6905
   counts for a 690° request at 30 / 60 / 100 %** (`fifty-cm.md` §3,
   `microbit-comparison.md` §6).
7. **During a `0x70` move**: `0x46` reads work every 20 to 40 ms with
   no effect on the move; `0x5F` hard-stops (5° more at 50 %, target
   dropped); `0x60` speed 0 stops on the normal ramp (46° more at 50 %,
   target dropped); `0x60` with a nonzero speed takes over the move; a
   second `0x70` supersedes, measured from the position at the moment
   it arrives (`microbit-comparison.md` §6, `test/test.ts` `RUN brickx`).
8. **`0x77` is per port**: the most recent write to a port's speed
   governs, whether it arrived with motor byte 0 (all) or 1 to 4, and
   it persists across moves (`microbit-comparison.md` §6). This is what
   makes an arc expressible as two moves with proportional speeds.
9. **On the UART, two motors given the same move 7 to 9 ms apart stayed
   within 2 to 3° of shaft of each other** (one unloaded, one with the
   turntable) and both finished on the count; 93 ms of start skew put
   them 100° apart mid-move with the same finish
   (`microbit-comparison.md` §5.5). Start-time skew is the thing to
   keep small.
10. **On the UART a bare speed-0 frame in servo mode is refused**
    (ack status `0xC0`) and the move completes; mode-select to speed
    then speed 0 ramps down and drops the target
    (`microbit-comparison.md` §5.1).
11. **The vendor "reset" opcode `03 1D 01` disabled motion on the motor
    it was sent to until the cable was replugged**
    (`motor-protocol.md` §3). Never send it.
12. **The kernel's jerk path overshoots 13 mm at 100 %** because
    `vFloor` is applied only when `jerk == 0` (`fifty-cm.md` §2;
    `velocity_shaper.cpp:106`).
13. **The kernel's stock +2.5 mm long stop is the floor-speed tick plus
    the ramp**, the same at every cruise speed because every move ends
    at the floor (`fifty-cm.md` §2).

14. **What the brick sends for each opcode** (sniffed 2026-10-27 with
    the ESP32 in the motor's place on a crossed M3-to-M3 cable,
    `nezha-esp32/docs/motor-protocol.md` §7, logs
    `docs/data/sniff_walk1.log` and `sniff_detail1.log`): `0x60` becomes
    `03 6E <pct×10>`, so the 0.1 % resolution is discarded in the brick;
    `0x70` degrees mode becomes `03 67 11 00 <tenths> <0x77 value>`;
    `0x5F` is `03 67` with a zero relative angle at 100 %, a position
    hold; `0x77` is stored in the brick and only ever appears as the
    speed field of `03 67` / `03 70`; every mode change is bracketed by
    broadcast writes of register 0x64 (0 before, 2 after); most frames
    carry a constant `CC` where the checksum belongs and the motor
    accepts them; the brick forwards register reads for 0x46 and 0x47
    only.

Two things the ESP32 bench did NOT verify and which a design cannot
assume: two wheels through the brick at once (the micro:bit rig has one
motor), and any camera-truthed heading result for built-in moves on a
chassis.

---

## 3. Severity scale

- **Critical** — the position-move design cannot work, or a robot is
  left running, if this is not addressed.
- **Major** — a measured accuracy loss, a safety path that does the
  wrong thing, or a structural gap that blocks the platform work.
- **Minor** — a correctness or clarity defect with bounded effect.
- **Suggestion** — cleanup or an improvement with no defect behind it.

---

## 4. Findings

### A. Architecture: the model of the motor is wrong

**F1 · Critical · The velocity kernel is a loop wrapped around a loop,
and its port-level shaping is built for a different actuator.**
`core/diffdrive.cpp` `controlStep()` computes a duty from a velocity
PID with accel feed-forward, twist hold, lambda, crawl pulses and
stall/deficit latches, then `NezhaMotorPort::writeShapedDuty()` applies
a deadband boost, a 100 ms reversal dwell, a sigma-delta quantizer to
integer percent, a 19 ms write throttle and a 25 %/tick slew before
writing `0x60`. The thing on the other end is a speed setpoint to a
motor whose own loop already holds speed within ±5 °/s under load
(§2 facts 1, 4). The outer PID can only add its 24 ms sampling and
integer quantization to that. The measured consequence is §0's table:
nothing the kernel does gets under 0.6 mm worst case without a
terminal correction, and the built-in move does 0.14 to 0.44 mm with
no micro:bit control loop at all.

This is not a reason to delete the kernel, but it is a reason to
shrink it. What the motor cannot know is that there are two wheels on
one chassis: the twist hold that keeps a straight leg straight and an
arc on its radius, the mm/s-to-percent calibration, and the
supervision (stall, lease, watchdog, e-stop, odometry) all stay ours.
The inner per-wheel velocity PID is the part that duplicates the
motor's own loop. The honest velocity path is feed-forward to the
motor's speed loop plus the twist-hold correction, with the inner PID
as an option and probably off, the same shape the Cutebot Pro hybrid
already landed. Several port shaping stages still guard measured brick
failures (the encoder wedge on an instant sign flip, the latched speed
across MCU resets, see `nezha_port.h`'s header) and stay.

MEASURED 2026-10-27 (`microbit-comparison.md` §7c, one wheel, no load):
with `pid_ki 0` and `accel_kaff 0` (`pid_kp` is already 0 in the
bake) the kernel is pure feed-forward through the motor's speed loop.
At 248 mm/s it is as good or better than stock (+1.96 / 0.33 against
+2.94 / 0.53 mm). At 792 mm/s the feed-forward saturates (10 900
counts/s against a `full_duty_velocity` of 10 795) and one trial in
four ran 24 mm long, where stock held +2.1 / 0.76. So the integral term
is not regulating speed, it is correcting position during the brake
when the command is pinned at the rail. Two consequences: a cruise
ceiling below saturation (about 0.9 × full-duty) makes the term
unnecessary on the velocity path, and the position correction it was
providing is exactly what the motor's own position loop does better.
Position moves stop going through the kernel at all: §6's design.

The better velocity actuator through the brick is also measured now
(`microbit-comparison.md` §7b): `0x77 <°/s>` then `0x70` mode 3 is a
velocity command with 1 °/s resolution up to about 980 °/s, re-issuable
mid-run including reversals. Against `0x60`'s 11.5 °/s steps that
removes the need for the sigma-delta dither; the cost is two I2C frames
per speed change instead of one. Owner of the decision: stakeholder;
the open issue already proposes the position half.

**F2 · Major · `DiffDrive::Motor` has no seam for a position move, so
neither platform can express one through the stack.** The 14 virtuals
(`core/diffdrive.h:25-44`) are staged duty, split-phase encoder, e-stop
and diagnostics. There is no "move N counts at speed S", no "is the
move done", no "hard stop". `test/test.ts`'s `RUN brick` reaches the
brick by raw `pins.i2cWriteBuffer` from TypeScript, bypassing the
`I2CBus` seam, the `BusGuard`, the port, the kernel and the engine,
which is fine for an experiment and wrong for a product. The ESP32
bench has the same shape: `benchGoto("builtin")` calls
`sendMoveRelative()` directly from `main.cpp`. Recommendation: a second
port interface (§6.1) implemented by `NezhaMotorPort` (brick frames)
and by the new ESP32 UART port (motor frames). The Cutebot Pro has a
per-wheel angle move too (`0x83`/`0x86`, `docs/design/cutebot-pro-support.md`
§1.2), so the interface is three-board general.

### B. Integration hazards for position moves

**F3 · Critical · The kernel's stop-enforcement path will abort any
built-in move within one tick.** Code reading, both sides, confirmed
against measurement. With the kernel in `kModeNeutral` (which is where
it sits between moves and where it would sit during a position move),
`controlStep()` calls `stageStop()` → `stageDuty(0, 0)`
(`diffdrive.cpp:826-844`). `stageDuty()` skips the write only when
`alreadyQuiet && !enforceStop`, and `enforceStop` is true whenever
either wheel reads above `kRestVelocity` (100 counts/s = 10 °/s). So
on every tick during which a wheel is moving, the kernel calls
`setDuty(0)` on both ports. `NezhaMotorPort::tick()` then runs
`writeShapedDuty(0)` → `writeRawDuty(0, stopping=true)`, where
`stopNotTaken = pct == 0 && |velocity_| > 102` defeats the dedupe cache
and the stop bypasses the throttle (`nezha_port.cpp:663-715`). Result:
a `0x60 <port> 0` frame on every tick while the wheel moves. MEASURED
(§2 fact 7): `0x60` speed 0 during a `0x70` move stops it on the ramp
and drops the target. A position move started through the stack as it
stands would run for about one tick. The `test.ts` experiment only
worked because nothing was ticking the kernel while it ran.

This is also the reason the vendored kernel's "stop is stop, re-write
it until the wheel is still" invariant exists: the brick latches its
last speed. The two requirements conflict exactly during a built-in
move and nowhere else. Recommendation (§6.3): a "position move live"
latch in the port that drops staged `setDuty()` writes for the
duration, cleared on completion, hard stop or e-stop. The kernel stays
byte-identical (no paired-PR); the latch is host-testable against the
sim bus. The alternative, a new kernel mode that samples but never
stages, is cleaner but touches the vendored file.

**F4 · Major · Every stop path sends the ramp stop, not the hard stop.**
`NezhaMotorPort::emergencyStop()` writes `0x60 0`
(`nezha_port.cpp:609-614`); `Rig::softStop()`, the starvation watchdog
(`shims.cpp:1039-1066` via `softStop()`), `endMove()`, `STOP`,
`ESTOP`, and the fault-context `diffdrive_emergency_motor_stop()`
(`board_nezha.cpp:1083-1096`) all end in that write. MEASURED (§2
fact 7): during a built-in move at 50 % that is 46° more travel
(36 mm of wheel) against 5° for `0x5F`. MEASURED on the real motor
through the brick (`microbit-comparison.md` §7a): travel after the stop
command, ramp against hold, 0.6 / 0.6 mm from the 8 % floor, 2.8 / 1.4
from 15 %, 11.1 / 2.2 from 30 %, 41.7 / 4.9 from 60 %, 101.9 / 8.6 mm
from 100 %. At the kernel's floor the two are identical, so the hard
stop does not improve a kernel move that ends at the floor; it is for
every stop from speed: e-stop, `STOP` mid-move, the watchdog, and any
live position move. The UART equivalent is known (F17).
Recommendation: the position-move port interface carries `hardStop()`;
`emergencyStop()` and the watchdog use it; the kernel's end-of-move
neutral stays as it is.

**F5 · Major · The starvation watchdog's meaning flips under position
moves, and the design must choose.** Today "the robot only moves while
something ticks" (`docs/design/design.md`, execution model): if the
tick loop stops, the brick keeps the last speed forever, so the
watchdog stops the motors 100 to 150 ms after the last tick. A
built-in move is the opposite hazard: the motor finishes on its own
whether or not anyone ticks, so a student's loop body that blocks on
`showIcon()` no longer stalls the move, but a program that abandons a
move (returns from the handler, hits a breakpoint) leaves a wheel
travelling to a target nobody is watching, for up to the move's
length. `commandLooksActive()` (`shims.cpp:1024-1036`) reads
`engine.isDriving()` and `appliedDuty`, both of which would be
false/zero during a position move, so the watchdog would not fire at
all unless taught about the new mode. Recommendation: keep the
invariant (the watchdog stops position moves too, with `0x5F`), make
`isDriving()` true during one, and say so in the README's tick
contract. Stakeholder call, since the alternative (position moves run
to completion unattended) is also defensible for a classroom.

**F6 · Major · `appliedDuty()` and `Output` lie during a position
move.** `appliedDuty()` reports the last `0x60` percent the port wrote
(`nezha_port.cpp:858-861`), which is 0 while the motor runs a
built-in move. Four consumers read it as "is this wheel driven":
`commandLooksActive()` (F5); `MotionEngine::service()`'s settle test
(`appliedDutyLeft == 0.0f && ...`, `motion_engine.cpp`, the `stopped`
expression); `NezhaMotorPort::collect()`'s frozen-read hold and wedge
detector (`|appliedDuty()| > kMotionThreshold`, `nezha_port.cpp:808-813,
837`); and the kernel's own `kaff`/bias paths, which are inert in
neutral. The wedge detector's "driven" streak will never count during
a position move, so an encoder wedge mid-move is invisible; the
frozen-read hold will treat a genuinely frozen counter as a real stop
and let `velocity_` read zero. Recommendation: the port reports a
`driven()` (or a nonzero synthetic `appliedDuty()`) while a move is
live, so the existing consumers keep their meaning; document which
`Output` fields are meaningful in each mode.

**F7 · Minor · The fault-context stop covers ports 1 and 2 only.**
`diffdrive_emergency_motor_stop()` loops `port = 1..2`
(`board_nezha.cpp:1086`). `configure motor` can move a wheel to M3 or
M4 at run time (`motor_wiring.h`, `NezhaMotorPort::configureWiring()`),
after which a hard fault leaves that wheel running. Pre-existing, not
caused by this work, in scope because it is the last line of the
motor path. Fix: loop 1..4 (two extra 8-byte writes in a fault
handler).

### C. The velocity kernel: measured defects and tuning

**F8 · Major · The jerk-limited profile skips the speed floor and
overshoots at speed.** `velocity_shaper.cpp:104-106`: "Retain the
legacy floor only without jerk limiting", `if (lim.jerk <= 0.0f &&
remain >= 0.0f && vNext < floor) vNext = floor;`. With `jerk > 0` the
reference ramps to zero, the motor's lag turns the last part into
coast, and MEASURED (§2 fact 12) the 50 cm move overshoots 13 mm at
100 %. Any student or bench config that sets `jerk` gets this. Fix:
apply the floor under jerk limiting as well (ramp down to the floor,
not through it), or refuse `jerk > 0` until it is fixed.

**F9 · Major · `omegaFloor` commands the pivot approach below the
motor's stiction.** Default `omegaFloor = 20 °/s` of body yaw
(`motion_limits.h:706`). On the effective 120 mm track
(114.2 / 0.952) that is 21 mm/s per wheel, 27 °/s of shaft at
0.7878 mm/deg, about 2.3 % duty. MEASURED
(§2 fact 2) the motor does not start below about 5 % (55 to 62 °/s),
and the loaded turntable motor needed 5 % to turn at 27 °/s. So the
last part of every pivot is commanded in the stick-slip regime; the
kernel's integral term (`ki` 6, `iMax` 766 counts/s ≈ 7 % duty) winds
up until the wheel breaks away, then the wheel lurches. A 100 ms lurch
at 55 °/s is 5.5° of shaft = 4.3 mm = about 2° of heading from one
wheel. That is the size and the sign-randomness of the sprint 031
pivot residual (`docs/sprint-031-postmortem.md` §2.3, sd 1.8°, both
signs). The straight-leg floor, `vFloor = 70 mm/s` (89 °/s, 7.7 %), is
above stiction and does not have this problem, which is why straights
are mm-accurate and pivots are not. Fix (if pivots stay on the
kernel at all): `omegaFloor` ≈ 45 °/s of body yaw (55 °/s of shaft)
as the floor, per-robot. With position moves for pivots this knob
only matters for the fallback.

**F10 · Minor · `stopDistance` and `lag` model the wrong stop.** The
shaper budgets the stop as a constant `stopDistance` plus a first-order
`lag` coast (`velocity_shaper.cpp:56-66, 147-150`). MEASURED (§2
fact 3) the motor's stop is a fixed-rate ramp, travel v²/2a with
a ≈ 3400 °/s² unloaded (about 2700 mm/s² on the fleet wheel) and
2500 to 2900 °/s² loaded. `fifty-cm.md` §2 shows what this costs:
`decel 2000` runs 20 mm long because the brake budget assumes a
deceleration the motor does not deliver, and `stop_distance` can only
centre the bias at one speed. With position moves this becomes a
second-order concern for the kernel's remaining modes. Record the
measured ramp as the model to use if anyone retunes it.

**F11 · Minor · The measured tuning for the kernel's remaining modes is
not the shipped default.** `fifty-cm.md` §2 and §3: `v_floor 40`,
`decel 1000`, `stop_distance 0.3`, `accel 2500`, `jerk 0` give
±0.4 mm sd and under 1 mm worst case on the bench wheel against
+3 mm stock. These are one-motor, no-chassis numbers; a robot needs
its own (`v_floor 40 mm/s` = 51 °/s is right at stiction and may need
to be higher under load). Worth a per-robot bake pass on a real
chassis once the position mode exists, not before.

**F12 · Minor · The `nudge()` block rounds to whole millimetres.**
`blocks/motion.ts:364` `_beginNudgeWheels(Math.round(left),
Math.round(right))` and `shims.cpp:740` `beginNudgeWheels(int left,
int right)` take integer mm, while `MotionEngine::beginNudge()` takes a
float and the pulse resolution is about 0.4 mm (`fifty-cm.md` §3). A
caller closing a 0.6 mm residual cannot ask for it. Pass hundredths
like the other block entry points (`_startMove` passes ×10 and ×100).
Related: `nudge-blocks-have-no-hardware-acceptance-run.md` (open).

### D. The ESP32 bench firmware

**F13 · Major · The abort path cannot stop a built-in move.**
`benchGoto("builtin")` and the `x` command stop with
`sendSpeedTenths(port, 0)` (`main.cpp:1220`, and the `abortRequested()`
exits), and `sendSpeedTenths()` only calls `ensureMode(kMotorModeSpeed)`
when `tenths != 0` (`main.cpp:581-587`). MEASURED (§2 fact 10): a bare
speed-0 frame in servo mode is refused with status `0xC0` and the move
completes. So `x` during a `goto builtin` does nothing, and the bench's
only emergency stop for the one strategy that is going into production
is broken. Fix: a `hardStop(port)` that selects speed mode first (and,
once F17 is settled, sends whatever the real hard stop is); never a
bare speed 0 while `portMode[port] == servo`.

**F14 · Major · `main.cpp` is not reusable as a platform.** One
translation unit holds the mux select, the UART transaction, the
reply scanner call, the per-port mode cache, the internal-MCU I2C
(buttons, version, power mask), the port ping scan, the bench
strategies, the sample recorder, the serial command parser, the
display and the button state machine, all sharing file-scope globals
(`currentPort`, `portMode[4]`, `benchPort`, `pid`, `prof*`,
`samples[2000]`). The parts that belong in a port (`selectPort()`,
`motorTransact()`, `readAngle()`, `readSpeed()`, `motorSend()`,
`ensureMode()`, `sendSpeedTenths()`, `sendMoveRelative()`,
`pingPort()`) are about 150 lines and are correct; they need to become
a `MotorUartBus` (mux + transact, one per board) and a
`NezhaUartMotorPort` (one per port) behind a bus interface, the same
split `I2CBus`/`NezhaMotorPort` already has, so a host `SimMotorUart`
can answer the real frames. §5.3 lists the pieces.

**F15 · Minor · `motor_protocol.h` still builds the reset frame.**
`motorResetFrame()` (`motor_protocol.h:69-71`) and `sendReset()` /
the `reset` serial command (`main.cpp:594-597, 1195-1200`) send
`03 1D 01`. MEASURED (§2 fact 11) this disabled a motor until it was
replugged. Delete the builder and the command, or keep the opcode
constant with a comment and a static assertion that nothing references
it; a bench user typing `reset` should get a refusal, not a bricked
motor.

**F16 · Minor · Opcode `0x70` means different things on the two buses,
and the names will collide in shared code.** On the brick, `0x70` is
"move by degrees/turns/seconds" with a mode byte; on the motor UART,
`0x70` is "run for a time" (`kMotorRegMoveTimed`), and the UART's
positioning move is `0x67`. Both repos will soon hold both. Name
constants by bus (`kBrickMoveDeg`, `kMotorRegMove`), and put the brick
opcodes in one header beside the UART ones so the mapping brick → UART
is written down once.

**F17 · Minor · RESOLVED 2026-10-27: the brick's `0x5F` on the UART is
a zero relative move at 100 %.** Sniffed (§2 fact 14): `03 5A 01` if
the port is not already in servo mode, then
`03 67 11 00 00000000 84030000`. The motor's position loop brakes to
the current count, which is the measured 5° stop. The ESP32 port's
`hardStop()` sends exactly that; F13's fix follows.

**F18 · Suggestion · Smaller items in `nezha-esp32/src`.**
`sendSpeedTenths()` always returns true and discards `motorSend()`'s
result (`main.cpp:581-587`); `motorSend()` counts a non-zero ack
status as a reject but the caller never sees it. `evalProfile()` has
an empty conditional (`profile.h:333-335`). `benchPort = 1; // M2`
(`main.cpp:440`) is right only because the index is 0-based; say so.
`PositionPid::update()` applies `minimumOutput` by the sign of the
clamped output, so a tiny output of the wrong sign (possible with
`kd > 0` on a reversal) floors in the wrong direction; floor by the
sign of the error instead. The trapezoid feed-forward at 100 %
commands 1150 °/s against a 1093 °/s motor (`fifty-cm.md` §1); cap
`vmax` at the measured full speed.

### E. Tests and simulators

**F19 · Major · `sim_nezha_bus.h` models `0x60` and `0x46` only.** The
whole-stack tour shim (`sim_robot_shim.cpp`) is the only place the
real `NezhaMotorPort` runs on the host, and it cannot see `0x70`,
`0x77` or `0x5F` at all; a position-move path would be "proven" by
tests that never exercise the frames. The model needed is small and
now fully measured (§2 facts 3, 7, 8): per-port move speed register
(pct × 9, persists); `0x70` degrees mode runs the wheel at that speed
to the target with the motor's ramp at the end (±1 count is enough);
`0x5F` stops within 5°; `0x60 0` during a move ramps at v²/2a and
drops the target (the test for F3); a nonzero `0x60` takes over; a
second `0x70` supersedes from the current position. The ESP32 needs
the same thing for UART frames, which `motor_protocol.h`'s
`findMotorReply()` already half provides (parse the request, answer
with a reply frame).

**F20 · Minor · The ESP32 has no bus-level test.**
`tests/test_motor_protocol.cpp` covers frame bytes, the reply scanner,
the PID and the profile, and nothing above them; `motorTransact()`,
the mux, the mode cache and the power switch are proven only by
running the board. Once F14's split exists, the same `SimMotorUart`
that F19 wants gives these a host test.

**F21 · Suggestion · The `RUN brick`/`brickx` handlers in `test/test.ts`
are measurement scaffolding and should not ship in the student
program.** They talk to 0x10 from TypeScript outside the `BusGuard`,
which the repo's own bus discipline forbids (`core/bus_guard.h`,
`docs/design/design.md` sprint 030 correction), and they hard-code
motor 1. Keep them until the port-level path exists (they are the
bench harness `tools/mb50.py` drives), then delete them in the same
ticket that lands `RUN` verbs for the real path.

**F22 · Suggestion · `tools/mb50.py` and `tools/bench.py` should
converge on one trial protocol.** Both already run the same 50 cm /
three-speed / four-trial / alternating experiment and write CSVs;
`chart50.py` reads both. Once the ESP32 speaks the wire grammar
(§5.4), one script drives both rigs and the comparison is apples to
apples by construction.

---

## 5. The ESP32 as an alternate platform

### 5.1 What "platform" means in this stack

`src/DESIGN.md` §1 draws the line: below it is CODAL-bound and
board-specific; above it nothing knows what a brick is. Sprint 040 put
a second board (Cutebot Pro) under that line with a compile-time seam
(`platform/board.h`, `DIFFDRIVE_BOARD`) inside one PXT build. The ESP32
is a different thing: a different build system (PlatformIO), a
different runtime (Arduino on FreeRTOS, no CODAL fibers), a different
transport (USB CDC, no `uBit.serial`), no MakeCode and no blocks. The
board seam helps (the `boardMotors()` / `boardWiring()` / diag hooks
are host-portable declarations the ESP32 can implement) but it is not
the whole answer.

### 5.2 Portability by layer, as the code stands

| layer | files | reaches `pxt.h`? | ESP32 status |
| --- | --- | --- | --- |
| kernel | `core/diffdrive.*`, `encoder_glitch_armor.h`, `heading_wrap.h`, `bus_guard.h`, `motor_wiring.h`, `fiber_identity.h`, `motion_owner.h` | no (libc only; C++11 syntax gate) | compiles as is |
| motion | `motion/*` | no | compiles as is |
| board seam | `platform/board.h` | no | compiles as is; the ESP32 supplies a `board_nezha_esp32.cpp` |
| Nezha port | `platform/nezha_port.*`, `i2c_bus.h` | `.cpp` only inside `#ifndef DIFFDRIVE_HOST_BUILD` for the fault handlers | not needed on the ESP32 (no brick); the shaping pipeline's measured reasons are brick-specific |
| platform ports | `platform/platform_ports.h` (Clock/Sleeper/FiberLauncher) | yes | replace: `micros()`, `delay()`/`vTaskDelay()`, `xTaskCreate` or none |
| vfp guard | `platform/vfp_guard.*` | yes | not needed (the hazard is CODAL's context switch) |
| OTOS, WiFi flash | `platform/otos_port.*`, `wifi_flash_port.*` | yes | out of scope for milestone 1 |
| wire grammar / adapter / run queue / config fields / emit queue | `comms/wire_handler.*`, `wire_adapter.*`, `run_*`, `config_fields.h`, `emit_queue.h`, `reply_backpressure.h`, `transport_sink.h` | no | compiles as is (host-tested) |
| transports and protocol loop | `comms/serial_transport.*`, `radio_transport.*`, `wifi_*`, `protocol.*` | yes | replace: an Arduino `SerialTransport` over USB CDC and a `loop()`-driven protocol; `fiber_identity.h` is pure and the "one fiber" invariant becomes "one task" |
| composition root | `shims.cpp` (`Rig`, `tickDrive()`, watchdog, config table) | yes | the hard part: `Rig`, `tickDrive()`, `softStop()`, the config descriptor table and the diag ordinals are all in the 2343-line PXT shim; the ESP32 needs the same objects without the PXT glue |
| blocks | `blocks/*.ts` | n/a | no equivalent; the ESP32's "student surface" is the wire protocol first, an Arduino C++ class second |

UNVERIFIED and worth one compile: that `comms/wire_handler.cpp` and
`wire_adapter.cpp` really have no transitive CODAL reach (the host
tests say so at C++20 on clang; the ESP32 build is GCC on Xtensa).

### 5.3 What the ESP32 platform needs

1. **`platform/motor_uart_bus.h`** — the bus seam, the `I2CBus`
   analogue: `bool transact(uint8_t port, const uint8_t* frame, size_t
   len, MotorReply& reply, uint32_t timeoutMs)` and `bool ping(port)`.
   Two implementations: the ESP32 one (mux select on GPIO 2/1, flush,
   write, scan for `F9 F5 01`, from `main.cpp:452-495, 549-570`) and a
   host `SimMotorUart` that answers the real frames (F19, F20).
2. **`platform/nezha_uart_motor_port.*`** — `DiffDrive::Motor` plus the
   position-move port (§6.1), one per motor port. `requestSample()` is
   a no-op (the UART read is synchronous, 2.3 ms); `tick()` reads
   `02 46` and writes the staged speed as `03 6E` tenths (no sigma-delta
   needed: 0.1 % resolution); keeps the per-port mode cache
   (`03 5A`) and skips repeated speeds exactly as the vendor library
   does. Encoder plausibility armor is reusable as is.
3. **`platform/nezha_esp32_power.*`** — the internal-MCU client: version
   read, power-mask write by firmware version, the ping-and-power scan
   (`main.cpp:627-737`). `begin()` on a port must wait out the
   measured 2 s after power-up before the first speed command, or
   report not ready.
4. **`platform/board_nezha_esp32.cpp`** — the board half of `board.h`:
   the two ports, wiring hooks, diag ordinals, a fault-context stop
   (for the ESP32: the hard stop of F17, `03 5A 01` then a zero
   relative move at 100 %, to every powered port).
5. **`platform/esp32_ports.h`** — Clock/Sleeper/FiberLauncher.
6. **A transport and a loop** — USB CDC `SerialTransport`; `Protocol`'s
   body driven from `loop()` or one FreeRTOS task; the wire grammar
   unchanged so `tools/mb50.py`, `robotlink.py` and the bench scripts
   drive both platforms.
7. **A composition root** — a `Rig` without PXT: the kernel, engine,
   odometry, bus guard (trivially satisfied on one task), watchdog
   (a timer), config descriptor table. The cleanest route is to pull
   the board-agnostic part of `shims.cpp`'s `Rig`/`tickDrive()` into a
   host-portable `core/rig.*` that both the PXT shim and the ESP32
   main compose; that is also a cleanup the micro:bit side has wanted
   (the shim is 2343 lines).

The kernel's split-phase sampling costs the ESP32 8 ms of sleeps per
24 ms tick for nothing (the UART read is one round trip), and the
cadence is fixed at `cyclePeriod ≥ 2 × kSettle + margin`. For
milestone 1 accept the 24 ms tick on the ESP32 for the velocity path;
position moves do not care, and a faster kernel cadence is a later
kernel change (paired-PR regime).

### 5.4 How to share the code

Options, with a recommendation:

- **A. Vendor a copy into `nezha-esp32`.** Fast, and exactly the
  "fix bugs in both trees" regime the kernel already suffers from
  (`core/diffdrive.h`'s header comment). Rejected.
- **B. PlatformIO library pointing at the `pxt-nezha-diffdrive`
  checkout** (`lib_extra_dirs` or a `library.json` inside
  `pxt-nezha-diffdrive/src/` with `srcFilter` selecting `core/`,
  `motion/`, `platform/board.h` and the portable half of `comms/`).
  One source of truth, the host suite still runs where it lives, the
  PXT manifest (`pxt.json` `files`) untouched. Recommended for the
  first milestone; the ESP32 repo gains a submodule or a documented
  sibling-checkout path.
- **C. Split the portable layers into their own repo** (the direction
  `radio-robot-lib`/`radio-robot` already point in). Right eventually,
  premature until B has shown which files are really shared.

Whichever is chosen, `tests/host/test_pxt_manifest_completeness.py`
and `test_cxx11_syntax_gate.py` are the gates that keep the shared set
honest; add a third that compiles the shared set with the Xtensa
toolchain (`pio run` in the ESP32 repo, in CI or in the sprint-close
checklist).

---

## 6. Proposed design: position moves on both platforms

This elaborates the open issue with what the review found.

### 6.1 The port seam

A second interface beside `DiffDrive::Motor`, in `core/` so it stays
libc-only:

```
class PositionMotor {
  virtual bool supportsPositionMove() const = 0;
  virtual float positionQuantum() const = 0;   // [counts] 10 on the brick, 1 on the UART
  virtual bool beginMove(float deltaCounts, float speedFraction) = 0;  // relative
  virtual bool hardStop() = 0;                 // brick 0x5F / UART per F17
  virtual bool moveLive() const = 0;
};
```

`NezhaMotorPort` implements it with `0x77` (per port, pct × 9, written
only when it changes) then `0x70` degrees mode with the direction byte;
`NezhaUartMotorPort` with `03 5A 01` then `03 67 11 00`. Both round
`deltaCounts` to their quantum and report what they rounded to, so the
engine can split the rounding across the two wheels (§6.4). The
`moveLive()` latch is what F3 and F6 need.

### 6.2 The engine

A `PositionMove` beside `Segment`/`Hold`/`Nudge` (exactly one live).
Planning reuses `beginSegment()`'s maths (distance and yaw to per-wheel
counts, `rotationalSlip`, `effectiveTrackWidth`), then per-wheel speed
fractions proportional to each wheel's share of the dominant distance
(this is what makes an arc two moves that finish together; §2 fact 8)
and the two `beginMove()` calls back to back. Service: keep stepping
the kernel (encoder reads continue through `requestSample()`/`tick()`,
so `Output` positions and `Odometry` stay continuous); completion =
both wheels within `arriveDist`/`arriveYaw` of target and at rest
(`atRest()`), with the deadline, e-stop and the stall latch keeping
their meaning (stall = demanded and still for `stallWindow`, which the
engine can compute from the move's own expectation since the kernel
will not). Stop = `hardStop()` on both. The settle-and-rest test the
ESP32 bench used ("no change for 400 ms") adds 0.4 s per move and is
the wrong test; target-plus-rest is 100 to 150 ms.

### 6.3 Keeping the kernel out of the way

For the duration of a position move the port drops staged `setDuty()`
writes (`moveLive()`), reports `driven()` true, and still answers
encoder reads. `emergencyStop()` on a live move sends `hardStop()` then
the zero. The kernel is never told; it sits in neutral exactly as it
does between moves today, and the paired-PR regime is untouched. A
host test against the extended sim bus pins that no `0x60` frame is
written during a move (the F3 regression).

### 6.4 Units, rounding and config

- Cruise in mm/s maps to a speed fraction through `countsPerMm()` and
  `fullDutyVelocity` (10795 counts/s in the fleet bake, 108 counts/s
  per percent, against 115 measured on the bare motor; the loaded
  number is the one to use).
- Brick quantum: 10 counts = 1° = 0.79 mm on the fleet wheel. Round
  the two wheels in opposite directions so the heading error of a
  pivot stays under half a step, and accept the residual rather than
  chase it with pulses.
- A config ordinal `position_mode` in `config_fields.h`, same shape as
  the Cutebot's `onboard_pid` (43): 0 = kernel for everything (today),
  1 = built-in moves for straights and pivots, 2 = built-in for arcs
  too. Default 1 after bench acceptance; 0 is the escape hatch.
- Wire: `WHEELS_X`, `MOVE_X`, `GO_TO_*` honour the mode; `WHEELS_V`,
  `MOVE_V` never use it. Blocks: `move`, `goTo`, `whileMoving`,
  `nudge` likewise; `setWheelSpeeds`/`driveTwist` unchanged.

### 6.5 Safety rules, stated once

1. No `0x60`/`03 6E` write to a port with a live move except as part
   of `hardStop()` or e-stop.
2. Every stop path (`STOP`, `ESTOP`, `stop move`, watchdog, fault
   handler, `configureWiring()`) hard-stops live moves first.
3. The watchdog treats a live move as "driving" (F5, pending the
   stakeholder's call).
4. Never send `03 1D` (F15).

---

## 7. Bench probes still needed (UNVERIFIED)

1. Two wheels through the brick at once: start skew between the two
   `0x70` frames and mid-move divergence (needs a second motor on the
   micro:bit rig, or a robot). The sniff shows the brick emits a
   four-frame preamble plus command in about 3 ms without waiting for
   replies, so the skew between two ports should be a few ms.
2. ~~A finer `0x70` unit~~ SETTLED by the sniff: modes 0 and 1 are
   turns, mode 2 is degrees (×10 on the wire), mode 3 is seconds. No
   finer unit; the rounding split stays.
3. ~~Minimum gaps~~ SETTLED for the brick side: no inter-frame wait.
   The 4 ms the vendor code pauses after `0x5D` is the brick's own
   read-then-move sequence.
4. ~~`0x5F` on the UART~~ SETTLED (F17).
5. A camera-truthed straight leg and pivot on a chassis with built-in
   moves: end heading, mid-leg twist without the kernel's twist hold,
   and whether `rotational_slip` 0.952/0.962 still holds (it should; it
   is mechanical).
6. E-stop and watchdog timing during a built-in move: wheels at rest
   within 200 ms (the issue's acceptance bar).
7. ~~Fine velocity through the brick~~ SETTLED (`motor-protocol.md` §8,
   `microbit-comparison.md` §7b): `03 70`'s speed field is degrees per
   second, 1 °/s resolution, unsigned 16-bit, direction in flag bit 0,
   time in 100 ms units; a second frame supersedes at once; through the
   brick, `0x77` + `0x70` mode 3 measures within 1 % of the value up to
   about 980 °/s, and a `0x77` write alone does not retarget. Still
   open: the same through the brick with two wheels, and on a chassis.
8. ~~The feed-forward-only kernel run~~ SETTLED on one wheel
   (`microbit-comparison.md` §7c, F1): as good at 248 mm/s, 24 mm
   overshoot at 792 mm/s where the feed-forward saturates. Open: the
   same with two wheels and the twist hold on a chassis.
9. The register 0x64 bracket: `64 00` is a stop (acked, the motor
   decelerated); `64 02` was refused in speed mode. Whether `64 02`
   after a mode select does anything, and whether a mode select needs
   the bracket at all, is open. The vendor ESP32 library never sends
   it and its moves work. The motor also treats a checksum byte of
   `CC` as a wildcard and rejects any other wrong checksum
   (`motor-protocol.md` §8).
10. The `0x5D` absolute-move arithmetic, if anyone ever wants it: a
    fake-motor position command on the ESP32 and a clean matrix
    (`motor-protocol.md` §7).

---

## 8. Proposed issues and sprint arc

Each row is one CLASI issue; the finding column is the evidence.

| # | issue | findings | size |
| --- | --- | --- | --- |
| I1 | `PositionMotor` port interface in `core/`; `NezhaMotorPort` implements it with `0x77`/`0x70`/`0x5F`; move-live latch drops kernel writes; `driven()` for the wedge/frozen-read consumers | F2, F3, F6 | substantial |
| I2 | Extend `sim_nezha_bus.h` with the measured `0x70`/`0x77`/`0x5F`/takeover/supersede behaviour and the v²/2a ramp; pin "no `0x60` during a move" | F19, F3 | compact |
| I3 | `MotionEngine::PositionMove`: planning, rounding split, per-wheel speeds, completion, stall/deadline/e-stop; `position_mode` config ordinal; wire verbs and blocks routed | F1, §6.2, §6.4 | substantial |
| I4 | Every stop path hard-stops live moves; watchdog and `isDriving()` semantics decided and documented | F4, F5 | compact |
| I5 | Fault-context stop covers M1 to M4 | F7 | trivial |
| I6 | Jerk path applies the speed floor | F8 | compact |
| I7 | `omegaFloor` default above stiction; stop-ramp model recorded; measured kernel tuning baked per robot after a chassis run | F9, F10, F11 | compact (after I3's bench) |
| I8 | `nudge()` block and `beginNudgeWheels()` take hundredths of a mm | F12 | trivial |
| I9 | Bench acceptance on a robot: 50 cm, 90°/180° pivots camera-truthed, 60 cm square, stop/e-stop timing, two-wheel skew (probes 1, 3, 5, 6) | §7 | substantial, hardware |
| I10 | *Deferred.* ESP32: split `main.cpp` into `MotorUartBus`, `NezhaUartMotorPort` (Motor + PositionMotor), MCU power client, board file; fix the servo-mode abort; delete the reset frame; name opcodes by bus | F13, F14, F15, F16, F18 | substantial |
| I11 | *Deferred.* ESP32: `SimMotorUart` and host tests for the port and bus; the sniffer's fake motor is its first draft | F20 | compact |
| I15 | Bench: the feed-forward-only kernel run and the fine-velocity path through the brick (probes 7, 8); decides how much of the kernel's velocity PID survives | F1 | compact, hardware |
| I12 | *Deferred.* ESP32: shared-source build (option B), Arduino Clock/Sleeper, USB CDC transport, `loop()`-driven protocol, a PXT-free `Rig`; `pio run` compiles `core/` + `motion/` + portable `comms/` | §5.2, §5.3, §5.4 | substantial |
| I13 | *Deferred.* ESP32: drive the wire grammar from `tools/mb50.py`/`bench.py` and repeat `fifty-cm.md` on both rigs with one script | F22 | compact |
| I14 | Remove the `RUN brick`/`brickx` scaffolding once I3's `RUN` verbs exist | F21 | trivial |

**Arc.** Two sprints, both on the micro:bit firmware; the ESP32 issues
(I10 to I13) are deferred and the ESP32 stays the bench instrument.
The concrete change list is [change-plan.md](change-plan.md).

- **Sprint 1 — position moves on the host (I1, I2, I3, I4, I5, I6,
  I8, plus the in-tree brick protocol reference).** Ends with a hex
  that builds, the host suite green, the sim tour closing with
  `position_mode 1`, and the F3 regression pinned.
- **Sprint 2 — position moves on the bench and a robot (I9, I7, I15's
  two-wheel half, I14).** The acceptance bars in the open issue: 0.5 mm
  per wheel at 30/60/100 %, under 1.2 s at 100 %, pivots within 0.5°
  encoder-side with no lurch, a 60 cm square better than 11 mm, stops
  within 200 ms. Decide arcs (mode 2) and the velocity actuator on
  camera and bench evidence; bake the defaults.

I6 and I8 are independent of everything else and could ship out of
process today; I5 likewise.
