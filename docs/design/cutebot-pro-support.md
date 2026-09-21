# Cutebot Pro support — analysis and approach

**Owner:** Eric Busboom · **Written:** 2026-09-21 · **Status:** proposal,
pre-sprint. Nothing below has run on a Cutebot Pro yet; every hardware
claim is a SOURCE READING of ELECFREAKS' own extension unless it says
MEASURED.

## 0. The ask

Target the ELECFREAKS Cutebot Pro with this repo's drive stack. The
Cutebot Pro is a one-piece micro:bit car: two encoder motors, a
four-channel line sensor, headlights, an ultrasonic socket, an IR
receiver, four servo ports and two I2C expansion ports, all behind ONE
I2C slave at 0x10 with its own MCU that can run a closed speed/distance
loop itself. No Nezha brick, no OTOS, no RJ11 jack for the WiFi module.

The question is where in this stack the Cutebot plugs in, and what has
to move so that the two boards share everything above that point.

## 1. What the Cutebot Pro is on the wire

Source: `github.com/elecfreaks/pxt-Cutebot-Pro` (`main.ts`, `v1.ts`,
`v2.ts`, fetched from `master` 2026-09-21; copies in this session's
scratchpad, NOT vendored). Two hardware revisions exist and speak
DIFFERENT frame formats; the extension probes which one it is talking
to on first use and dispatches every call through that.

### 1.1 Revision probe (`main.ts` `readHardVersion()`)

Write the 7-byte v1-style frame `99 15 01 00 00 00 88` to 0x10, read
one byte: `1` means hardware v1, anything else means v2. The result is
cached for the session.

### 1.2 v2 frames (`v2.ts` `i2cCommandSend()`)

`FF F9 <cmd> <len> <params...>`, followed by a 1 ms busy-wait. Reads
are a bare I2C read after a `0xA0` query write — the same "a read
means whatever was last selected" statefulness the Nezha brick has.

| cmd | params | meaning |
|---|---|---|
| `0x10` | `wheel(0 L / 1 R / 2 both), abs(L) %, abs(R) %, dirbits(b0 L rev, b1 R rev)` | raw PWM, 0..100 % per wheel, ONE frame carries both |
| `0x20` | `light, r, g, b` | headlights |
| `0x30` | `abs(speed), dir` | expansion motor |
| `0x40` | `index, angle 0..180` | servo S1..S4 (the gripper) |
| `0x50` | `motor` | zero that wheel's encoder |
| `0x60` | `0` / `1` / `2, ch` | line sensor: 4-bit state / 16-bit offset (0..6000, centred 3000) / one channel's grey 0..255 |
| `0x80` | `Lh Ll Rh Rl dir` | ONBOARD SPEED LOOP, mm/s per wheel, **clamped to 200..500** when non-zero |
| `0x81` / `0x84` | `dist_h dist_l dir [speed_h speed_l]` | onboard distance move, mm |
| `0x82` / `0x85` | angle bytes + turn code | onboard steering (one-wheel 2x arc, or in-place) |
| `0x83` / `0x86` | `Lh Ll Rh Rl [sp_h sp_l] dir` | onboard per-wheel angle move, deg x10, ONE direction flag for both wheels |
| `0xA0 [0]` | — | then read 3 bytes: firmware version |
| `0xA0 [1]` / `[2]` | — | then read 1 byte: that wheel's speed, **unsigned cm/s** |
| `0xA0 [3]` / `[4]` | — | then read Int32LE: that wheel's accumulated **degrees** |
| `0xA0 [5]` | — | then read 1 byte: onboard move finished |

The extension's "wait for the move" is `pidPause()`: poll `0xA0 [5]`
every 10 ms up to a time budget, then `basic.pause(500)`.

### 1.3 v1 frames (`v1.ts`)

`99 <cmd> a b c d 88`, 7 bytes. `0x02` per-wheel cruise (cm/s, capped
50), `0x03` distance, `0x04` angle, `0x05` read speed, `0x07`/`0x08`
full ahead/astern, `0x09` stop, `0x0A` clear encoder, `0x16` **raw
pulse counters** (2 x Int32 big-endian plus two sign bytes), and
`readDistance()` converts pulses to degrees with **1428 pulses per
wheel revolution** (`v1.ts:224-235`). Whether a v2 board still answers
`0x16` is unknown and worth one bench probe: raw pulses are 4x finer
than the v2 degree read.

### 1.4 What the documentation does NOT give

The ELECFREAKS wiki spec table (fetched 2026-09-21) lists: 18650 cell,
3.7 V nominal; motor output **3.3 V, 0.2 A max**; 4 servo ports at
battery voltage; 4 GPIO; **2 IIC ports**; 4 line sensors. It does not
give wheel diameter, track width, gear ratio, or v2 encoder
resolution. All four are caliper/bench measurements for the bring-up
ticket, and `travelCalib`/`trackWidth`/`fullDutyVelocity` are per-robot
bakes exactly as they are for the Nezha fleet.

### 1.5 The two numbers that decide the architecture

1. **The onboard speed loop floors at 200 mm/s** (`v2.ts`
   `pidSpeedControl()`: `Math.max(lspeed, 200)` when non-zero). This
   repo's whole precision regime lives BELOW that: the fleet speed floor
   is 70 mm/s (`MotionLimits::vFloor`), every `VelocityShaper` ramp
   passes through 0..200 on the way in and out of a leg, and nudge mode
   pulses far under it. Handing the onboard loop a shaped velocity
   would have it clip every ramp to a 200 mm/s step.
2. **The onboard speed readback is one unsigned byte in cm/s.** Not a
   velocity a servo loop can close on; not even signed.

So the Cutebot's PID is real but it is a *student-block* controller
(20-50 cm/s, blocking distance/angle moves with a done flag). It is
not a replacement for `DifferentialDrive`. What the Cutebot DOES give
us cleanly is exactly what the Nezha brick gives us: a raw PWM per
wheel and an accumulating encoder per wheel. The clamp is in the
extension's TypeScript; whether the MCU itself enforces it is a §8
measurement, and the only thing that could reopen §3.B.

## 2. Where this stack already splits hardware from the rest

`src/DESIGN.md` §1's layer map is the whole story. Below the line is
CODAL-bound and board-specific; above it nothing knows what a brick is:

| layer | hardware-specific? |
|---|---|
| `platform/nezha_port.*` — `NezhaMotorPort : DiffDrive::Motor` | yes, Nezha |
| `platform/otos_port.*` — `OtosPort : PoseSource` | yes, OTOS (already optional: `engineGoToW()` falls back to `Odometry` when `connected()` is false; `make_deploy.py --no-otos` exists) |
| `platform/i2c_bus.h` + `microbit_i2c_bus.cpp` | the bus seam; board-agnostic |
| `platform/platform_ports.h` — Clock/Sleeper/FiberLauncher | CODAL, board-agnostic |
| `core/diffdrive.*` (kernel) | **no geometry, no I2C**: 14 `Motor` virtuals, counts = 0.1 deg |
| `motion/*`, `comms/*`, `blocks/*`, `tools/*` | no (the line-follow tools are Trackbit-specific, see §6) |

The `DiffDrive::Motor` port (`core/diffdrive.h:27-43`: `begin`,
`requestSample`, `setDuty`, `emergencyStop`, `tick`, `position`,
`velocity`, `appliedDuty`, `connected`, `sampleTime`, `rebaseline`,
`wedged`, `wedgeSuspect`) is the seam. The kernel drives it
split-phase: `requestSample()` on each wheel, `sleepMillis(kSettle)`,
then `tick()` executes the staged duty and collects
(`core/diffdrive.cpp:528-533`). The freshness contract is
load-bearing: a port whose read FAILS must hold `sampleTime()`, not
report velocity zero (`src/DESIGN.md` §7). A Cutebot port implements
the same 14 calls against §1.2's `0x10` and `0xA0 [3]/[4]`.

### 2.1 Where Nezha leaks above the port — the actual refactor list

Everything that has to move for a second board is on this list, and
nothing else does:

| site | what leaks | fix |
|---|---|---|
| `src/shims.cpp:114-115` | `Rig` holds `NezhaMotorPort left{1,-1}; right{2,+1}` concretely | `Rig` composes a board-provided `Motor&` pair |
| `src/shims.cpp:1176-1236` | `diagValue()` ordinals 21-24, 27, 35-40 read Nezha-only public fields (`maxDrivenStreak_`, `glitchCount_`, `rebaselineCount_`, `wiredPort/Sign`, `rawCount`) | a small board-diagnostics hook; ordinals answer 0 on a board without the field |
| `src/shims.cpp:1299-1333` + `core/motor_wiring.h` | `configureMotor` (the `configure motor` block) swaps Nezha ports M1..M4 | Cutebot wheels are fixed: sign-only flip there, or a refusal — stakeholder call |
| `src/platform/nezha_port.cpp:52-65` | `diffdrive_emergency_motor_stop()` — the FAULT-HANDLER stop writes a Nezha frame to 0x10 | per-board definition; on a Cutebot the same bytes at the same address land on the wrong MCU |
| `src/comms/protocol.cpp:100` | `kRole = "NEZHA2"` in the HELLO banner (`kDrivetrain = "diffdrive"` stays) | per-board role string (sprint 037 made role/common_name runtime-settable) |
| `src/comms/wire_handler.cpp:911`, `.h:120-123` | STATUS `otos=`, `i2cf=`, `connl/connr`, `wedge` wording | leave; `otos=0` is already the no-OTOS answer, and connected/wedge are `Motor` virtuals |
| `src/motion/motion_engine.h:236-241` | `pulseWheels()` comment hard-codes the Nezha 25 %/tick slew as a caller constraint | comment only; the value lives in the port |
| `tools/make_deploy.py:1238-1286` | `_MOTOR_BAKE_RES` regexes match the two `NezhaMotorPort` literals; `_inject_motors()` validates "Nezha port 1-4" | bake keys move to the board composition file |
| `tools/make_deploy.py:286-300`, `:754-757` | `EXPECTED_CPP_FILES` is a literal list of the 13 `.cpp` files a real build must compile; `_FAULT_SPIN_SOURCES` names `nezha_port.cpp` | add the new translation units |
| `test/test.ts` | `otosBegin()` at boot; `RUN:` vocabulary assumes OTOS verbs exist | already guarded by `--no-otos`; keep |
| `test/linefollow.ts` | Trackbit at 0x1A, raw `pins.i2c*` from TypeScript, outside `BusGuard` | the Cutebot line sensor is `0x60` on 0x10 — a second sensor backend, later (§6) |
| `tests/host/sim_nezha_bus.h`, `sim_robot_shim.cpp`, `sim_tour.py`, `tests/DESIGN.md:76-87` | the sim parses Nezha frames and compiles `nezha_port.cpp` by name; the pxt-bound TU list is pinned by `test_pxt_bound_exclusion_is_current.py` | a `sim_cutebot_bus.h` beside it; `sim_tour.py` gains a board switch; the TU list gains the new files |
| `pxt.json` | `files` list; name `nezha-diffdrive` | add the new files (`test_pxt_manifest_completeness.py` enforces it); name stays |
| `src/comms/wifi_uart.cpp:18` | UARTE1 on **P8 (TX) / P1 (RX)** = Nezha RJ11 J1 | see §5 |

Everything else — the six motion verbs, `MotionEngine`, `Odometry`,
the v6 grammar, telemetry, the config descriptor table, `robotlink.py`,
`wifilink.py`, `field.py`, `wire_acceptance.py`, the tour suite — is
untouched. That is the payoff of the sprint 013/030/033 layering and it
is why option A below is small.

The published student extension (`tools/publish_extension.py` →
`League-Microbit/pxt-diff-drive`) is one `pxt.json` with one `files`
list, so both ports ship to every student project. That is fine: the
board switch (§4) is compile-time and the unused port costs flash,
not behaviour. A second published extension is NOT proposed.

## 3. Options

### A. Cutebot as a `DiffDrive::Motor` port — RECOMMENDED

`platform/cutebot_port.{h,cpp}`: `CutebotMotorPort : DiffDrive::Motor`,
one per wheel, both bound to a shared `CutebotDevice` (the 0x10 slave)
because the Cutebot takes BOTH duties in one `0x10` frame. `tick()` on
the second wheel of the pair is what actually ships the frame; the
first wheel's `tick()` only stages. Encoder: `0xA0 [3|4]` then a 4-byte
read, degrees x 10 = kernel counts. Revision probe at `begin()`, v1
frames behind the same class if the assigned board turns out to be v1.

What stays: the kernel PID, `fullDutyVelocity`/`ki`/twist-hold as
per-robot bakes, all of `motion/` and `comms/`, every host test, the
tour suite, the calibration tooling. What is new: two source files,
one sim bus, one board composition, a fleet JSON.

What to watch:

- **Encoder resolution.** 1 deg per LSB is 10 kernel counts. At the
  24 ms cycle that is ~42 deg/s of velocity quantisation, i.e. roughly
  15-20 mm/s on a ~50 mm wheel — the same order as the 70 mm/s floor.
  Mitigations, in preference order: (1) the v1 `0x16` raw-pulse read if
  v2 firmware honours it (4x finer, bench probe); (2) the port
  estimates velocity over a longer window than one tick (the kernel
  takes `velocity()` from the port, so this is the port's business, not
  the kernel's); (3) accept it and let `ki` do the averaging.
- **3.3 V / 0.2 A motors.** `fullDutyVelocity` and stall thresholds are
  going to be very different from the Nezha bake. Measured, not guessed.
- **Nezha shaping does not carry over.** The reversal dwell, sigma-delta
  quantiser and write throttle each guard a MEASURED Nezha failure
  (`nezha_port.h` header). None is known to apply to the Cutebot; the
  new port starts with none of them and earns each one on the bench.
- **Two bus writes plus two reads per cycle**, against the Nezha's two
  selects, two reads and up to two duty writes. Comparable; the 1 ms
  post-write wait the extension uses should be a `Sleeper` sleep, not
  a spin, per the fiber-yield rule.

### B. Onboard speed loop as the kernel — NOT NOW

Replace `DifferentialDrive` with a `CutebotKernel` that forwards
velocities to `0x80` and builds `Output` from `0xA0` reads. Blocked by
§1.5: the 200 mm/s floor clips every profile and the cm/s byte cannot
close a loop. It would also need a new seam — `MotionEngine` takes
`DifferentialDrive&` concretely, not an interface — which is a larger
refactor than A for a worse controller. Revisit only if §8.7 shows the
MCU itself accepts speeds below 200 mm/s.

### C. Onboard distance/angle moves as a student fast path — LATER

`0x81`/`0x83` + `0xA0 [5]` polling. Blocking, no arcs, no ratio-locked
wheel moves, no telemetry mid-move. Fine as an extra block for
students; never the core. Out of scope for this arc.

## 4. Board selection

Compile-time, baked by `make_deploy.py` from the fleet JSON, exactly
like `kChannel`/`kProfile`/`firmware_bake.motors` today:

- `platform/board.h` carries one literal, `DIFFDRIVE_BOARD`, defaulting
  to Nezha. `make_deploy.py` rewrites it in the scratch copy from a new
  `geometry.firmware_bake.board` key (`"nezha"` | `"cutebot-pro"`),
  falling back to Nezha when absent so the existing fleet builds are
  byte-identical (the same opt-in rule `_inject_geometry()` follows).
- `platform/board_nezha.cpp` and `platform/board_cutebot.cpp` each
  define the board's `Motor` pair, `diffdrive_emergency_motor_stop()`,
  role string, and the diag/wiring hooks in §2.1, under `#if` on that
  literal. PXT compiles every file in `files`, so both are always in
  the build and the `#if` is the only switch.
- Runtime autodetection (probe 0x10 at boot) is deliberately NOT the
  mechanism: this repo has two open issues on first-I2C-command
  wedges, and the fleet's own rule is that identity comes from
  something baked and reported, not sniffed. HELLO reports the board
  via the role string; `ID` keeps reporting `kProfile`.

## 5. Carriers on a Cutebot

- **USB serial** works as-is (the farm's `mbdeploy` daemon on the node
  the board is plugged into).
- **Radio** works as-is (`--radio-link`; the pair derives from the
  board's name).
- **WiFi** is the open question. `WifiUartCodal` puts UARTE1 on P8/P1
  because that is the Nezha's J1 jack. The Cutebot Pro exposes P0/P1/P2
  on its GPIO ports and has two IIC ports; whether P8 is on a header,
  and which pins its IR receiver and ultrasonic socket consume, is
  UNVERIFIED — a look at the board and one probe. If P8 is not
  exposed, the pin pair becomes a per-board constant in the same
  board file (P1/P2 are the obvious candidates). Nothing in
  `wifi_link.*` above the UART cares.

## 6. Peripherals the Cutebot adds (follow-on, not the core)

- **Servo `0x40`** — the gripper on the assigned robot. One wire verb
  and one block; trivial once the device object exists.
- **Line sensor `0x60`** — `RUN line` needs a second sensor backend
  beside the Trackbit; the follower logic in `linefollow.ts` is already
  sensor-agnostic past `lineBits()`, and `tools/linefollow/` drives it
  by `RUN` name, not by sensor.
- **Headlights `0x20`**, ultrasonic, IR — student blocks; whenever.
- **OTOS** could still ride on an IIC port (0x17 does not collide with
  0x10). Not needed for bring-up.

## 7. Host testing

Same pattern as the Nezha sim (`tests/host/sim_nezha_bus.h`, which
exists precisely so a port's real bytes are tested rather than a
`FakeMotor` above them):

- `tests/host/sim_cutebot_bus.h` — parses `FF F9 cmd len ...`, answers
  the revision probe, `0xA0 [3|4]` in degrees from the shared `SimWheel`
  physics, `0x50` clears; rejects anything else.
- `cutebot_port_shim.cpp` + `test_cutebot_port.py` — frame bytes and
  direction bits for every sign combination, the two-wheel coalesced
  write (exactly one `0x10` frame per kernel cycle), degrees-to-counts,
  velocity over the quantised read, `rebaseline()`, `emergencyStop()`
  bytes, `connected()` and held `sampleTime()` on a NACK.
- Source pins: both boards' emergency-stop frames match their port
  constants; the pxt-bound TU list, `pxt.json` manifest completeness,
  `EXPECTED_CPP_FILES` and the C++11 syntax gate already cover new
  files once they are listed.
- `sim_tour.py --board cutebot-pro` for a whole-tour smoke on the host
  before a board is touched.

## 8. Bench bring-up (the part that needs the robot)

The assigned board for this session is on the mbdeploy farm. NOTE:
the stakeholder named **zeguz on mangi**; `mbdeploy list --remote`
(2026-09-21 22:29) advertises **zetuv on magni** and no zeguz; zetuv
refused a connect as `busy` (another session holds its serial daemon).
Resolve which board it is by `HELLO` before anything else.

Order of operations, each one a MEASURED line in the capture notes:

1. `HELLO` — identity from silicon. Confirm the micro:bit is seated in
   a Cutebot Pro and the Cutebot is powered (`i2cf` will say).
2. Revision probe (`99 15 01 00 00 00 88`) and version (`0xA0 [0]`) —
   a scratch MakeCode program using ELECFREAKS' own extension is the
   fastest way to do 2-4 without writing any C++ first.
3. Does v2 answer `0x16` raw pulses? Read both encoders at rest, spin a
   wheel by hand, read again: sign convention, resolution, wrap.
4. Caliper: wheel diameter, track width. Count: pulses per wheel rev
   against the 1428 figure.
5. First firmware build with the Cutebot port: `PING`, `STATUS
   connL=1 connR=1`, `WHEELS_V` at a low duty — direction of each wheel
   vs the commanded sign (the sign bake), then `fullDutyVelocity`.
6. `MOVE_X` 200 mm vs tape: `travelCalib`. In-place pivots vs the
   camera if it is on the field, else a protractor: `rotationalSlip`.
7. The onboard loop, once, for the record: `0x80` at 100 mm/s — does
   the MCU clamp to 200 or is that only the extension? Decides whether
   §3.B is ever worth reopening.

## 9. Proposed arc

Two sprints; the second cannot be planned in detail until §8.2-8.4
have answered what the board is.

**Sprint 040 — Board seam and the Cutebot Pro motor port.**
Refactor the §2.1 list behind a board composition with zero behaviour
change on Nezha (host suite green, one tovez/gopiv smoke over USB);
`CutebotMotorPort` + device object + sim bus + host tests; `board`
bake key in `make_deploy.py`; fleet JSON for the assigned board;
docs. Ends with a hex that builds and a host tour that closes.

**Sprint 041 — Bring-up and calibration on the Cutebot.**
§8 on the real board; kernel bake for the Cutebot motors; encoder
resolution decision (§3.A); WiFi pin answer (§5); the servo verb for
the gripper; a square tour that closes within the fleet's numbers.

Everything in §6 beyond the servo, and §3.B/C, stay as issues.

## 10. Open decisions for the stakeholder

1. Option A (our kernel over their PWM) vs B (their loop) — §1.5 says A;
   confirm.
2. `configure motor` on a Cutebot: sign-only, or refuse?
3. Which board, really: zeguz or zetuv, and is it a v1 or v2 Cutebot?
