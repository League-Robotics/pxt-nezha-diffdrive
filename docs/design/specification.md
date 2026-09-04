# DiffDrive — Full Specification

Status: existing, working codebase (v1.0.0) being brought under the CLASI
process. This specification is reconstructed from the stakeholder-written
`README.md` and from the shipped source (`motion.ts`, `diffdrive.h/.cpp`,
`nezha_port.h/.cpp`, `platform_ports.h`, `shims.cpp`, `test.ts`,
`pxt.json`), which is treated as ground truth for actual behavior. Every
statement in `README.md` is preserved somewhere below; source-derived
detail beyond the README is marked as such by section.

## 1. Overview

DiffDrive is a MakeCode extension for PXT/micro:bit. It drives the
ElecFreaks Nezha brick's two-wheel differential drive **closed loop**:
an encoder-servoed wheel-speed controller (the DiffDrive kernel) steps
at a 24 ms cadence on whichever fiber ticks it (the "tick model" —
sprint 002 unwired the kernel's own background fiber; see §9), and
every block talks to it.

Unlike open-loop duty control, wheel speeds are measured and corrected
continuously — straight means straight, distances land on the encoder,
and the robot's pose (x, y, heading) is always available from odometry.

## 2. Package Identity

From `pxt.json`:

| Field | Value |
|---|---|
| name | `nezha-diffdrive` |
| version | `1.0.10` |
| description | "Closed-loop differential drive for the Nezha brick: encoder-servoed wheel speeds, twist and distance moves, curved go-to, and pose from odometry. The wheel controller runs in its own fiber." |
| license | MIT |
| dependencies | `core: *`, `microphone: *` |
| files | README.md, and under `src/`: core/diffdrive.h, core/diffdrive.cpp, motion/motion_engine.h, motion/motion_engine.cpp, platform/platform_ports.h, core/heading_wrap.h, core/encoder_glitch_armor.h, platform/encoder_pose_source.h, platform/nezha_port.h, platform/nezha_port.cpp, platform/otos_port.h, platform/otos_port.cpp, comms/serial_transport.h, comms/serial_transport.cpp, comms/radio_transport.h, comms/radio_transport.cpp, comms/protocol.h, comms/protocol.cpp, comms/wire_handler.h, comms/wire_handler.cpp, comms/wire_adapter.h, comms/wire_adapter.cpp, shims.cpp, blocks/sim.ts, blocks/run.ts, blocks/pose.ts, blocks/stop.ts, blocks/world.ts, blocks/motion.ts |
| testFiles | test/test.ts, test/testrig.ts |
| supportedTargets | microbit |
| preferredEditor | tsprj |
| yotta config | `microbit_radio_max_packet_size: 250` |
| disablesVariants | `mbdal` (dropped in deploy builds — see `tools/make_deploy.py`) |

Supported targets, per README: "for PXT/microbit". (The README notes
this metadata line "is needed for package cataloging.")

**`microphone` dependency (sprint 007):** its true purpose is genuinely
unknown. Two independent code-review passes found no reference to
`microphone` anywhere in `src/` or `test/` and disagreed with each
other on what that means — one read it as dead weight to delete or
justify, the other assumed it is deliberate micro:bit V2 gating,
alongside `disablesVariants: ["mbdal"]`. It is documented here, not
deleted: removing a shipped extension's declared dependency on the
strength of a source grep, with no confirmed understanding of PXT's
editor/variant-gating behavior, risks a silent breakage a source-only
review cannot see, for a Low-priority hygiene item. Flagged in case the
stakeholder has out-of-band knowledge this review process cannot see
from source alone.

## 3. Installation

In [MakeCode for micro:bit](https://makecode.microbit.org/), open a
project, click the gear menu → **Extensions**, and paste this repo's
URL:

```
https://github.com/League-Robotics/pxt-nezha-diffdrive
```

## 4. Public API (block reference)

The public surface is the `diffDrive` namespace
(`//% color=#0f9c5a icon="" block="DiffDrive"`), split across `src/`'s
block-API modules (`sim.ts`, `run.ts`, `pose.ts`, `stop.ts`, `world.ts`,
`motion.ts` — see `src/DESIGN.md` §9 for the module split), organized
into block groups: **Drive**, **Move**, **Pose**, **World**, **Setup**.
Every exported function present at the time of writing is documented
below; the README's example listing is a representative subset, not the
full API. Sprints 002/003 added surfaces this section does not yet
detail (see `src/DESIGN.md` §9 for the current inventory):
the `drive tick` block and tick-model contract (continuous-mode
commands only move the robot while a `driveTick()` loop runs), the
**World** group (OTOS start/seed/read blocks and `go to world x y`),
the `on run` / `on run command` wire-trigger blocks, the taper/ramp
shaping shims, and the `emitLine`/`probe`/OTOS shim surface.

### 4.1 Units and coordinate conventions

- Student-facing units: **cm**, **cm/s**, **degrees**, **degrees/s**.
- Positive yaw/turn rate is **counter-clockwise** (right wheel forward
  turns the robot CCW).
- Pose is `(x, y, heading)` in **robot start coordinates**: x forward, y
  left, established at boot or at the last `resetPose()`.
- `goTo`/`startGoTo`/`whileGoingTo` take a point in the **robot's
  current frame**: x forward, y left, relative to the robot's current
  pose at the moment the call is issued (not the start-of-program
  frame).
- Internally (TS→C++ shim boundary) everything is converted to
  integers: mm, mm/s, centidegrees, centidegrees/s; kernel config
  values are scaled ×1000. The TS layer owns the cm/deg student units;
  see §9's "Boundary convention" note.

### 4.2 Drive group — velocity commands

Velocity commands do not block. Under the tick model (sprint 002) the
robot only moves **while something keeps ticking the control loop** —
run a `while (diffDrive.driveTick())` loop after issuing one. If
nothing ticks, the starvation watchdog stops the robot within about
150 ms; a fresh command or resumed tick loop resumes immediately, no
clear-emergency-stop needed. (Position-mode blocks like `move` tick
internally, so this only matters for
`setWheelSpeeds`/`driveTwist`.) `driveTick()` reports this condition
via `commandLooksActive()` (sprint 007 ticket 002, closing R-10/API-01);
`tests/host/test_continuous_drive_command_looks_active.py` pins it
against silent regression.

| Block | Function | Params | Behavior |
|---|---|---|---|
| `set wheel speeds left %left right %right cm/s` | `setWheelSpeeds(left, right)` | `left`, `right`: cm/s, block-editor range −50..50 each | Sets the two wheel speeds directly. Converted to mm/s (`×10`) and sent to the kernel as `_setWheels`. |
| `drive %speed cm/s turning %yawRate deg/s` | `driveTwist(speed, yawRate)` | `speed`: cm/s, range −50..50; `yawRate`: deg/s, range −180..180 | Drives with a body forward speed and a yaw (turn) rate simultaneously. Converted to mm/s (`×10`) and centidegrees/s (`×100`) and sent to the kernel as `_driveTwist`. |
| `stop` | `stop()` | — | Normal stop: commands the kernel to neutral (`_stopAll`). Motors ramp to zero through the kernel's normal stop path (see §6.3/§7.2); not a hardware-level emergency stop. |
| `emergency stop` | `emergencyStop()` | — | Emergency stop: latches the kernel's e-stop and calls the motor ports' `emergencyStop()` directly (`_estopAll`), bypassing normal shaping. Stays latched until `clearEmergencyStop()`. |
| `clear emergency stop` *(advanced)* | `clearEmergencyStop()` | — | Clears the e-stop latch (`_estopClear`) so driving can resume. |
| `is stalled` | `isStalled()` | — | Reports whether the kernel's stall latch has tripped (demanded duty with near-zero encoder motion sustained past `stallWindow`) — the same bit as STATUS flags bit 2 / DIAG ordinal 2 (`_isStalled`). Always `false` in the simulator (no stall model). Not advanced — this is the discoverability half of the stall-latch fix, so it stays in the default palette. |
| `clear stall latch` *(advanced)* | `clearStallLatch()` | — | Clears the stall latch so Drive/Move commands take effect again (`_clearStallLatch`). **Separate from `clearEmergencyStop()`** — the stall latch and the e-stop latch are independent fault states; clearing one never clears the other. No-op if nothing is latched. No-op in the simulator. |

### 4.3 Move group — position-mode moves (blocking)

Position-mode moves **wait until the move is done** before the block's
program flow continues.

| Block | Function | Params | Behavior |
|---|---|---|---|
| `move %distance cm turning %yaw degrees` | `move(distance, yaw)` | `distance`: cm to travel; `yaw`: degrees to turn, CCW+ | Drives a distance while turning a yaw angle, then stops. Setting both at once produces an arc. Internally: `startMove(distance, yaw)` then `while (_tickDrive())` — the blocking form ticks the control loop itself at the 24 ms cadence until the move ends. |
| `go to x %x cm y %y cm` | `goTo(x, y)` | `x`: forward distance cm; `y`: leftward distance cm (robot frame) | Reaches a point in the robot's current coordinate frame exactly, then stops. Blocks the same way as `move`. |

`goTo`'s reduction (in `startGoTo`, shared by the blocking and async
forms) calls `MotionEngine::goToR()` directly, via the `_goToR()`/
`_setGoToDeadline()` shim pair — unlike `move`, it does **not** reduce
to distance-and-yaw and go through `startMove()`/`moveX()`. Given
target `(x, y)` in the robot frame with the robot starting at heading
0 along +x, `goToR()` (`motion_engine.cpp`) owns its own split:
- turn angle `theta = 2 * atan2(y, x)` radians, signed, wrapped to the
  short arc `(-pi, pi]` before anything below uses it.
- below the same ~50 deg pivot-first threshold `move`'s own reduction
  uses (`kTurnFirstAngleRad`): one blended constant-curvature arc — if
  `|y| < 0.01`: straight line, arc length `s = x`; else signed radius
  `radius = (x² + y²) / (2y)`, arc length `s = radius * theta`.
- at or above that threshold: pivots to the line-of-sight bearing
  (`atan2(y, x)`) then drives the straight-line chord (`hypot(x, y)`)
  — reaching `(x, y)` exactly either way. This is deliberately
  different from `move`'s own >=50 deg split, which reissues an
  arc's `(s, theta)` as pivot-then-straight and lands at a different
  point than the arc it was computed for — correct for `move`, which
  never claims to reach a specific `(x, y)`, but not something `goTo`
  can inherit.
- `hypot(x, y) <= arrive` (the no-op radius passed by the caller —
  1 mm for `goTo`/`startGoTo`) issues no move at all.

### 4.4 Move group — position-mode moves (async)

Non-blocking variants for interleaving a move with other logic via
polling.

| Block | Function | Params | Behavior |
|---|---|---|---|
| `start move %distance cm turning %yaw degrees` *(advanced)* | `startMove(distance, yaw)` | same as `move` | Starts a distance/yaw move without waiting. Uses the current `defaultSpeed` (default 15 cm/s) and `defaultYawRate` (default 90 deg/s) as the move's speed/turn-rate targets. Poll `isMoving()` / call `stopMove()`. **Known tick-model gap**: polling does not itself advance the move — without a concurrent `driveTick()` loop the move never progresses and the watchdog stops it within ~150 ms (see `startMove`'s doc comment in `motion.ts`). |
| `start go to x %x cm y %y cm` *(advanced)* | `startGoTo(x, y)` | same as `goTo` | Starts a go-to without waiting; calls `goToR()` directly (see §4.3), not `startMove`. |
| `moving?` | `isMoving()` | — | Returns whether a move is currently running (`_updateMove()`; this call also advances the move state machine — see §9). |
| `move progress` *(advanced)* | `moveProgress()` | — | Fraction of the current move completed, 0 to 1 (`_progress() / 1000`). |
| `stop move` | `stopMove()` | — | Stops the robot now, including a continuous drive command in progress (`setWheelSpeeds`/`driveTwist`) — same full-stop contract as `stop` (§4.2); no-op if the robot was already idle (`_endMove`). |

### 4.5 Move group — loop ("while") forms

Run user code **during** the move; leaving the loop (or calling
`stopMove()` from inside it) ends the move.

| Block | Function | Params | Behavior |
|---|---|---|---|
| `while moving %distance cm turning %yaw degrees` | `whileMoving(distance, yaw, body)` | `body(x, y, heading)`: reporter-parameter handler | Starts a distance/yaw move, then loops calling `body(poseX(), poseY(), heading())` once per ~24 ms tick while the move is active. When the loop exits (move complete, or the body called `stopMove()`), the move is explicitly ended (`_endMove()`). |
| `while going to x %x cm y %y cm` | `whileGoingTo(x, y, body)` | same contract as `whileMoving` | Same as `whileMoving`, but for a `goTo` arc. |

### 4.6 Pose group

| Block | Function | Behavior |
|---|---|---|
| `pose x (cm)` | `poseX()` | Robot x position (forward from start/reset), in cm (`_poseX() / 10`). |
| `pose y (cm)` | `poseY()` | Robot y position (left from start/reset), in cm (`_poseY() / 10`). |
| `heading (deg)` | `heading()` | Robot heading in degrees, CCW positive (`_poseHeading() / 100`). |
| `reset pose` | `resetPose()` | Resets pose to `(0, 0, 0)` — establishes a new start frame for subsequent pose reads and `goTo` calls. |

### 4.7 Setup group — calibration and configuration

| Block | Function | Params | Behavior |
|---|---|---|---|
| `set default speed %speed cm/s` *(advanced)* | `setDefaultSpeed(speed)` | `speed` cm/s, eg 15 | Sets the default speed used by `move`/`goTo`/`startMove`/`startGoTo`. Clamped to a minimum of 1 (`Math.max(1, speed)`). |
| `set default turn rate %yawRate deg/s` *(advanced)* | `setDefaultYawRate(yawRate)` | `yawRate` deg/s, eg 90 | Sets the default turn rate for the same set of blocks. Clamped to a minimum of 1. |
| `set track width %width cm` *(advanced)* | `setTrackWidth(width)` | `width` cm, eg 11.5 | Distance between the wheels, used by odometry and by twist↔wheel-speed conversion. Sent to the shim as `round(width * 100)` (units of 0.1 mm). |
| `set wheel calibration %calib mm/deg` *(advanced)* | `setWheelCalibration(calib)` | `calib` mm/deg, eg 0.7837 | Wheel travel per shaft-encoder degree, used to convert between physical distance and encoder counts. Sent to the shim as `round(calib * 10000)` (units of 1e-4 mm/deg). |
| `set config %field to %value` *(advanced)* | `setConfigValue(field, value)` | `field`: `ConfigField` enum; `value`: number | Escape hatch: sets one kernel `Config` field directly. Value sent as `round(value * 1000)` (kernel-side config values are ×1000-scaled integers; see §6.5 and §9). |

### 4.8 `ConfigField` enum (advanced tuning targets)

Exposed for `setConfigValue`, in block-declaration order (also the
integer values used by the shim's `setKernelValue` switch, §9):

| Value | Enum member | Block label | Kernel `Config` field |
|---|---|---|---|
| 0 | `MaxDuty` | "max duty %" | `maxDuty` |
| 1 | `FullDutyVelocity` | "full-duty wheel speed" | `fullDutyVelocity` |
| 2 | `Kp` | "PID kp" | `kp` |
| 3 | `Ki` | "PID ki" | `ki` |
| 4 | `IMax` | "PID integral limit" | `iMax` |
| 5 | `Kaff` | "accel feedforward" | `kaff` |
| 6 | `PidMax` | "PID output limit" | `pidMax` |
| 7 | `TwistHoldGain` | "twist hold gain" | `twistHoldGain` |
| 8 | `VFloor` | "speed floor mm/s" | *(none — see below)* |
| 9 | `PosErrMax` | "position error limit" | `posErrMax` |
| 10 | `StallSpeed` | "stall speed" | `stallSpeed` |
| 11 | `StallDemand` | "stall demand" | `stallDemand` |
| 12 | `StallWindow` | "stall window ms" | `stallWindow` |
| 13 | `LambdaEnabled` | "lambda enabled" | `lambdaEnabled` |
| 14 | `CrawlPulse` | "crawl pulse" | `crawlPulse` |
| 15 | `DefaultCruise` | "default cruise speed" | *(none — see below)* |
| 16 | `RotationalSlip` | "rotational slip" | *(none — see below)* |
| 17 | `StallClear` | "clear stall latch" | *(none — see below)* |
| 18 | `StopDistance` | "stop distance mm" | *(none — see below)* |
| 19 | `Accel` | "acceleration mm/s2" | *(none — see below)* |
| 20 | `Decel` | "deceleration mm/s2" | *(none — see below)* |
| 21 | `VMax` | "max speed mm/s" | *(none — see below)* |
| 28 | `Jerk` | "jerk" | *(none — see below)* |
| 30 | `OmegaMax` | "max turn rate deg/s" | *(none — see below)* |
| 34 | `OmegaFloor` | "turn rate floor deg/s" | *(none — see below)* |
| 35 | `ArriveDist` | "arrive distance mm" | *(none — see below)* |
| 36 | `ArriveYaw` | "arrive yaw deg" | *(none — see below)* |

Ordinals 22, 23, 24, 25, 26, 27, 29, 31 (`BrakeFrac`, `DistTaper`,
`YawTaper`, `DistFloor`, `TurnFloor`, `RampMs`, `PlateauMinS`,
`ProfileExit`) are **removed** (sprint 029 ticket 004, design
`motion-profile-unification.md` §4.7/§8) — no `ConfigField` enum
member exists for them, and their wire names answer `err 1` on both
GET and SET for one release, the same reply an unrecognized name
always gets.

Ordinal 8's "Kernel `Config` field" column is also non-standard, as of
sprint 029 ticket 004 (design `motion-profile-unification.md` §4.7,
K5): `VFloor` used to be a real `DifferentialDrive::Config` field
(`vMin`, the kernel's own speed floor) but now writes
`MotionLimits::vFloor` (`motion_limits.h`) instead — the ordinal is
unchanged, but the kernel's own `vMin` stays pinned at 0 forever
(`shims.cpp`'s `ensure()`, its own `Config` seed comment). The speed
floor moved from being a *servo* concept to a *profile* concept: the
shaper (§4.2 of that design) is what commands the floored speed now,
not the kernel's own `applySpeedFloor()`.

Ordinal 15's "Kernel `Config` field" column is also non-standard:
`DefaultCruise` is not a `DifferentialDrive::Config` field at all — it
is the wire/shim layer's own `Rig::defaultCruiseMmS_` (`shims.cpp`),
seeded to 150 mm/s (matching the block layer's own `defaultSpeed`).
This is the sprint 007 ticket 003 fix for a code-review finding
(R-11/BLK-03/API-03): the wire's "cruise/speed == 0 means the
configured default" sentinel used to resolve through
`fullDutyVelocity` — the kernel's own 100%-duty ceiling, ~875 mm/s,
*and* the field whose `0` means "uncalibrated, refuse VELOCITY
commands" at the kernel layer. Those were two unrelated meanings of
zero collapsed onto one field; `DefaultCruise` gives the wire layer's
convenience sentinel its own, independent field, leaving
`fullDutyVelocity`'s calibration-refusal meaning untouched.

Ordinal 16's "Kernel `Config` field" column is also non-standard:
`RotationalSlip` is not a `DifferentialDrive::Config` field either — it
is `MotionEngine`'s own `rotationalSlip_` (`motion_engine.h`), the
camera-measured wheel-contact-scrub ratio that `effectiveTrackWidth`
(`= trackWidth / rotationalSlip`) is built from. This is the sprint 007
ticket 005 fix for a code-review finding (R-14/API-06): `rotationalSlip`
was getter-only, so the only palette knob that changed turn geometry at
all was `set track width` — which this file's own geometry doctrine
(§2.1 in the canonical motion-api spec this project conforms to)
forbids using for that purpose, since `trackWidth` is the
caliper-measured physical dimension and is never "corrected" to make a
turn land. `setConfigValue`'s new setter applies the same
"`>0`, else silently keep the prior value" validation
`setTrackWidth`/`setTravelCalib` already use (via `setGeometry`,
§9) — invalid values are silently ignored, not clamped or rejected.
No dedicated block was added for this ordinal (unlike `trackWidth`/
`travelCalib`, which each have one): `RotationalSlip` is a one-time
chassis-calibration constant, reachable through the existing generic
`set config` block at the same tier as the other kernel fields above
it.

Ordinal 17's "Kernel `Config` field" column is deliberately non-standard: `Set
config` with `StallClear` does not write a stored `Config` field at
all — it is a write-triggered **action** wearing a config-field's
clothes, reaching `DifferentialDrive::clearStallLatch()` directly
(nonzero `value` clears the latch; magnitude is ignored). Its GET side
is a convenience readback of `Output.stallHalted`, not a stored value —
reading it back never returns whatever was last "set." This mirrors
the dedicated `clear stall latch`/`is stalled` blocks (§4.2) exactly;
both routes reach the same kernel call.

Ordinal 18's "Kernel `Config` field" column is likewise non-standard,
as of sprint 029 ticket 004 (design `motion-profile-unification.md`
§4.7): `StopDistance` (renamed from `PivotOverrun`, ordinal unchanged)
is not a `DifferentialDrive::Config` field — it is `MotionLimits`' own
`stopDistance` (`motion_limits.h`), the per-wheel coast (mm) after the
last nonzero command, consumed by the shaper's own predictive-arrival
math every tick (§6.3 of that design) rather than subtracted from the
segment's target at start time the way the old `pivotOverrunMm_` was.
`setConfigValue` applies the same "`>= 0`, else silently keep the
prior value" validation `MotionLimits::setStopDistance()` already
uses.

Ordinals 19-21, 28, 30, 34-37's "Kernel `Config` field" column is
non-standard for the same reason as 8/15/16/17/18 above: none of these
nine is a `DifferentialDrive::Config` field. All nine live on
`MotionLimits` (`motion_limits.h`) — the one value object every
shaping/floor/arrival number in the system now reads from (design
`motion-profile-unification.md` §4.1) — reached via one small
descriptor table in `shims.cpp` (`kLimitsFields`) that
`setKernelValue()`/`getConfigValue()` both consult before falling into
either function's own kernel-field switch, rather than as
individually-forwarded `MotionEngine` setters the way this table used
to describe. `Accel`/`Decel`/`VMax` (19-21) also resolve the
wire-level `MOVE_X`/`GO_TO_R`/`GO_TO_W` verbs' own `cruise == 0` "use
the default" sentinel by leg distance — a wire-layer behavior this
document's block-API reference does not otherwise cover, since the TS
blocks above (§4.3-4.5) always resolve `defaultSpeed` themselves
before reaching the shim. `WHEELS_X`/`WHEELS_V` keep ordinal 15's flat
`Rig::defaultCruiseMmS_` sentinel unchanged. Each ordinal is a thin
forward to the named `MotionLimits` setter/member:

| Ordinal | Enum member | `MotionLimits` setter/member | Unit |
|---|---|---|---|
| 19 | `Accel` | `setAccel()`/`accel` | mm/s² |
| 20 | `Decel` | `setDecel()`/`decel` | mm/s² |
| 21 | `VMax` | `setVMax()`/`vMax` | mm/s |
| 28 | `Jerk` | `setJerk()`/`jerk` | mm/s³ |
| 30 | `OmegaMax` | `setOmegaMax()`/`omegaMax` | deg/s |
| 34 | `OmegaFloor` | `setOmegaFloor()`/`omegaFloor` | deg/s |
| 35 | `ArriveDist` | `setArriveDist()`/`arriveDist` | mm |
| 36 | `ArriveYaw` | `setArriveYaw()`/`arriveYaw` | deg |
| 37 | `Lag` | `setLag()`/`lag` | s |

`Accel`/`Decel`/`VMax`/`ArriveDist` (19-21, 35) validate `> 0`, else
silently keep the prior value — these are always-active ceilings/
windows with no "off" state (design §8: "now always active, no legacy
mode" for `Accel`/`Decel`). `Jerk`/`OmegaMax`/`OmegaFloor`/`ArriveYaw`/
`Lag` (28, 30, 34, 36, 37) validate `>= 0`, since `0` is each field's
own documented "off"/"none"/"unmeasured" value (`Jerk` 0 = no jerk
rounding, `OmegaMax` 0 = no pure-turn rate ceiling, `Lag` 0 = no
drivetrain response lag measured yet — the shaper's braking plan and
arrival test fall back to their pre-`Lag` formula exactly, byte for
byte, whenever it is 0).

**Not exposed anywhere in the block API or the `ConfigField` enum** (a
source-derived observation, not in the README): the kernel's per-wheel
accel/decel gain-and-intercept correction (`setWheelCorrection`, 8
floats), the adaptive-bias tuning (`setAdaptation`: `biasMax`,
`tauAdapt`, `aSteady`), and the deficit detector's threshold/window
(`setDeficit`). These can only be changed by editing the default
`Config` in `shims.cpp`'s `ensure()` (§11) — there is no block or
`ConfigField` value that reaches them at runtime.

## 5. Simulator behavior (browser fallback)

Every exported block function has two implementations: a C++ shim
(hardware, §9) and a TypeScript body in `sim.ts` (browser simulator,
used when a MakeCode program runs in the web simulator rather than on
device). The simulator is a minimal kinematic stand-in, not a
reproduction of the closed-loop control law:

- Maintains `simX`, `simY`, `simHeading` (mm, mm, rad) and
  `simVel`/`simYawRate` (mm/s, rad/s), integrated by `simIntegrate()`
  on every call using wall-clock delta time (`control.millis()`),
  clamped so that `dt < 0` or `dt > 0.5s` is treated as `dt = 0`
  (guards clock jumps).
- `setWheelSpeeds`: sets `simVel` to the mean and `simYawRate` to the
  half-difference over an assumed track width (`/115` mm — near, no
  longer exactly equal to, the hardware default of 114.2 mm), and
  cancels any active simulated move.
- `driveTwist`: sets `simVel`/`simYawRate` directly from the twist
  command.
- `startMove`: computes a constant velocity/yaw-rate for the move's
  full duration (`max(distance/speed, yaw/yawRate)`) and marks a
  simulated move active; remaining distance/angle count down each
  integration step; the move self-clears when both remainders reach
  zero.
- `updateMove`/`progress`/`endMove`/`stopAll` mirror the hardware
  shim's move-engine contract (§9) against the simulated state instead
  of the kernel's real output.
- `emergencyStop`/`clearEmergencyStop`: `emergencyStop` performs the
  same reset as `stopAll` and additionally sets a `simEstopped` latch;
  `clearEmergencyStop` clears it. While latched, `setWheelSpeeds`/
  `driveTwist`/`startMove` are refused at intake — mirroring
  hardware's `estopLatch_` (§6.4), checked by `checkCommandable()` —
  and leave `simVel`/`simYawRate`/`simMoveActive` untouched; there is
  no per-tick equivalent of the kernel's own `effective = kModeNeutral`
  override (§6.3) because nothing else in the simulator can introduce
  velocity between calls, so an intake-time refusal is sufficient.
  `stopAll` never sets or clears this latch, matching hardware's
  stop-vs-latch distinction (§9's `deliverStopNow()`).
- `poseX`/`poseY`/`poseHeading`/`resetPose` read/reset the simulated
  pose.
- `setGeometry`/`setKernelValue` are no-ops in the simulator — track
  width, wheel calibration, and kernel tuning have no simulated effect.
- `_tickDrive` (sprint 002) mirrors the hardware tick engine's
  absolute-deadline 24 ms pacing with `basic.pause()`, so
  `while (driveTick())` loops are timing-observable in the browser the
  same way they are on hardware.

## 6. Kernel: `DiffDrive::DifferentialDrive` (closed-loop wheel-speed controller)

Source: `diffdrive.h` / `diffdrive.cpp`. This is the vendored control
kernel — see §12 for its provenance and maintenance boundary. It is
platform-agnostic: the only include is `<cstdint>`, and it depends on
four small ports it defines itself (`Motor`, `Clock`, `Sleeper`,
`FiberLauncher`) rather than any firmware HAL.

### 6.1 Execution model

- Can run its own cooperative fiber, started by `start()` via the
  injected `FiberLauncher`; the fiber body (`run()`) calls `step()`
  once per cycle and sleeps to an **absolute** deadline
  (`cycleStartUs + cyclePeriod*1000`), tracking `cycleOverrunCount_`
  when a cycle overruns instead of sleeping. **In this package that
  fiber is deliberately never started** (sprint 002's tick model):
  `shims.cpp` drives `step()` from `tickDrive()` on the caller's
  fiber, with the same absolute-deadline pacing lifted into the shim
  layer — see §9.
- Default cadence: **24 ms** (`Config::cyclePeriod`, set once before
  `begin()` — changing it after `begin()` is refused with
  `kCadencePreserved` and the prior value is kept; see `setConfig`'s
  cadence-freeze logic).
- Each `step()`: snapshots config/commands (lock-free sequence
  counters), applies pending stall-clear / rebase requests, runs
  `controlStep()`, then samples both wheels: `requestSample()` →
  sleep `kSettle` (4 ms) → `tick()`, for left then right in sequence.
  A failed collect on either wheel increments the sticky
  `i2cFaultCount_`.
- Output (`Output` struct) is published via a lock-free
  even/odd sequence counter (`outSeq_`) so `output()` can be read
  concurrently from the caller's context without blocking the fiber.
- `begin()` calls `Motor::begin()` on both wheels, primes the
  stop-enforcement countdown, and refuses (`kRefusedUnconfigured`) if
  `maxDuty <= 0`. `start()` is idempotent and refuses
  (`kRefusedNotBegun`) if called before `begin()`.

### 6.2 Command modes and lease

- Three modes: `kModeNeutral` (commanded stop), `kModeVelocity`
  (body velocity + twist), `kModeRawDuty` (direct per-wheel duty,
  bypasses the PID entirely).
- `drive(velocity, twist, lease)` and `driveDuty(dutyLeft, dutyRight,
  lease)` both take a **lease** in ms (capped at `kLeaseMax` = 3,600,000
  ms / 1 hour) after which the command auto-expires back to neutral if
  not refreshed — a safety backstop against a hung caller leaving the
  robot driving. `neutral()` commands an immediate stop with no lease.
- Commands are refused (returned `Status`, and the first refusal is
  latched in `lastError()` until `clearLastError()`) when: the kernel
  hasn't `begin()`'d yet; it's e-stopped; it's unconfigured
  (`maxDuty <= 0`, or velocity mode with `fullDutyVelocity <= 0`); or
  any parameter is non-finite (NaN/Inf).
- `Output.leaseExpired` and the sticky `leaseExpiryCount` report lease
  timeouts for diagnostics.

### 6.3 Control law (per cycle, velocity mode)

Applies only when the effective mode is `kModeVelocity` (i.e., not
neutralized by lease expiry, stall halt, or e-stop, and
`fullDutyVelocity > 0`):

1. **Raw per-wheel targets**: `rawLeft = velocity - twist`,
   `rawRight = velocity + twist` (counts/s).
2. **Lambda authority scaling** (optional, `lambdaEnabled`): if either
   wheel's *previous cycle's* duty demand exceeded the duty rail
   (`maxDuty%`), `lambda` sheds authority — instantly on the attack
   side, released with a `kLambdaReleaseTau` = 0.3 s time constant —
   scaling both `rawLeft`/`rawRight` (and the twist term used for
   twist-hold) so the two wheels stay in the commanded velocity/twist
   ratio instead of one wheel independently clipping.
3. **Twist-hold trim** (optional, `twistHoldGain > 0`, needs both
   wheels connected): maintains an integral reference of commanded vs.
   measured half-differential wheel position, and applies a
   proportional trim (clamped to remaining duty headroom) to correct
   drift in the turn rate — e.g. compensating a robot that doesn't
   turn at exactly the commanded rate under load.
4. **Speed floor** (`vMin`, optional): if the larger-magnitude of the
   two wheel targets is nonzero but below `vMin`, both targets are
   scaled up together (preserving their ratio) to the floor — avoids
   commanding speeds too low for the motor to reliably turn.
5. **Per-wheel accel/decel correction** (`correctedCommand`): maps
   desired speed through a per-wheel, per-direction (accelerating vs.
   decelerating, determined by comparing magnitude to the previous
   cycle's target), linear `gain`/`intercept` model plus the wheel's
   adaptive `bias` (below). A desired speed at/below that wheel's
   intercept is unreachable and yields zero; the correction never
   flips the commanded sign. Exact zero always passes through
   unmodified ("stop is stop").
6. **PID + feedforward** (`fastPid`): `kp * velocityError +
   kaff * smoothedCommandedAccel + clamp(ki * clampedPositionError,
   ±iMax)`, clamped to `±pidMax`; non-finite results are floored to
   zero ("fail closed, never inject NaN"). The position error
   (`positionError`) is the divergence between an integrated
   reference of commanded speed and actual encoder position since the
   last (re)arm, clamped to `±posErrMax`; it is disarmed and
   re-anchored whenever speed is momentarily zero, `dt<=0`, the wheel
   disconnects, or a rebase occurred.
7. **Duty conversion**: `(correctedSpeed + pid) / fullDutyVelocity`,
   clamped to the duty rail, then passed through a **crawl-pulse**
   Bresenham-style pulse generator (`crawlPulse`, optional) that turns
   a duty magnitude too small to reliably move the motor into
   intermittent full-`crawlPulse` pulses whose average matches the
   demanded magnitude, rather than commanding a sub-breakaway
   continuous duty.
8. **Adaptive bias** (`adaptBias`, needs `tauAdapt > 0`): while the
   wheel's sample is fresh, the commanded acceleration is below
   `aSteady` (i.e. "steady state, not ramping"), and the commanded
   speed is at/above `vMin`, the per-wheel `bias` integrates the
   velocity error over time (`bias += err*dt/tauAdapt`), clamped to
   `±biasMax` (or forced to 0 if `biasMax` is 0). This is the slow
   long-run trim layered under the fast per-cycle PID.
9. **Saturation/deficit/stall detection**: a wheel is "saturated" when
   its instantaneous duty demand exceeds the rail. The **deficit
   latch** (per wheel) sets when velocity error exceeds
   `deficitThreshold` while both bias and PID are saturated, held for
   `deficitWindow` ms — signals the wheel structurally cannot reach
   its target even with full correction authority. The **stall latch**
   (shared, whole-kernel) sets when a meaningful duty is demanded
   (`|rawLeft|` or `|rawRight| > stallDemand`) while both encoders read
   near-zero (`<= stallSpeed`) and connected, held for `stallWindow`
   ms; once latched, the kernel self-halts to neutral
   (`stallHalted_`) until `clearStallLatch()` is called.

In `kModeRawDuty`, all of the above (PID, corrections, floors, lambda,
twist-hold) is bypassed — the commanded duty is clamped to the rail and
written directly.

In `kModeNeutral` (commanded stop, lease expiry, stall halt, or
e-stop), all adaptive/reference state is reset to a clean idle
baseline and a stop is staged (§6.6/§7.2).

A halted→not-halted or not-halted→halted edge on `(estopped ||
stallHalted)` triggers a full adaptive-state reset (`resetAdaptiveState`
— clears position/twist references, bias, deficit/stall latches, crawl
carries, last-PID values, and re-arms the stop-enforcement countdown).

### 6.4 Fault handling and safety surfaces

- **E-stop**: `estop()` sets a latch consulted every cycle (forces
  neutral); `estopClear()` releases it. `emergencyStopMotors()` sets
  the latch **and** calls each `Motor::emergencyStop()` directly — the
  one path that does not depend on a healthy `tick()` (see §7.2).
- **Stall latch**: see §6.3 point 9; cleared via `clearStallLatch()`
  (increments a request counter the next `step()` observes).
- **Wedge detection**: delegated to each `Motor` port; the kernel
  surfaces `wedged()`/`wedgeSuspect()` per wheel in `Output` and uses
  `wedgeSuspect()` as part of the PID's per-wheel "sample fresh" gate
  (a wedge-suspect wheel's sample is treated as stale).
  See §7.4 for the concrete Nezha implementation.
- **Rebase**: `rebasePosition()` requests a software re-anchor (bumps
  an epoch, re-arms position/twist references, clears cached wheel
  samples, calls `Motor::rebaseline()` on both wheels) with no bus
  traffic.
- **Status/refusal codes** (`Status` enum): `kOk`,
  `kRefusedUnconfigured`, `kRefusedNotBegun`, `kRefusedEstopped`,
  `kRefusedNonFinite`, `kCadencePreserved`. The first non-`kOk`
  refusal is latched in `lastError()` until explicitly cleared.
- **Diagnostics in `Output`**: cycle timing (`cyclePeriodMeasured`,
  `cycleBusy`, `cycleOverrunCount`), per-wheel position/velocity/
  connected/sample-time/wedge/wedge-suspect/deficit/saturation flags,
  measured mean `velocity` and half-differential `twist`, applied
  duty, `lambda`, per-wheel `bias`, `ready` (begun + calibrated),
  `estopped`, `leaseExpired`, `stallHalted`, sticky
  `leaseExpiryCount`/`i2cFaultCount`. None of this diagnostic detail is
  currently surfaced through the MakeCode block API (§4) — the TS
  layer only reads `positionLeft`/`positionRight` (for odometry) and
  `stallHalted` (to end a move early); see §9.

### 6.5 Config surface

Full `Config` struct (all fields settable via chained `setXxx()` calls
or a single `setConfig(Config)`; every setter and `setConfig` reject
non-finite input with `kRefusedNonFinite`):

`maxDuty` [%], `fullDutyVelocity` [counts/s], `kp` [1], `ki` [1/s],
`iMax` [counts/s], `kaff` [s], `pidMax` [counts/s], `twistHoldGain`
[1/s], `wheelGain[2][2]`/`wheelIntercept[2][2]` (per-wheel,
per-accel/decel, [1]/[counts/s]), `vMin` [counts/s] (speed floor),
`posErrMax` [counts], `biasMax` [counts/s], `tauAdapt` [s], `aSteady`
[counts/s²], `deficitThreshold` [counts/s], `deficitWindow` [ms],
`stallSpeed` [counts/s], `stallDemand` [counts/s], `stallWindow` [ms],
`lambdaEnabled` [bool], `crawlPulse` [-1,1], `cyclePeriod` [ms].

Only 15 of these fields are reachable from MakeCode blocks, via
`ConfigField`/`setConfigValue` — see §4.8 for the mapping and the list
of fields that are **not** reachable at runtime from blocks.

## 7. Nezha motor port (hardware I2C leaf)

Source: `nezha_port.h` / `nezha_port.cpp`. Implements the kernel's
`Motor` port against the ElecFreaks Nezha brick over I2C. Ported from
the firmware's Nezha motor leaf plus the wedge detector from its
`motor_armor.h` (see §12).

### 7.1 Bus protocol

- 7-bit I2C address `0x10`.
- Motor-run register `0x60`: an 8-byte frame
  `{0xFF, 0xF9, port, direction, 0x60, magnitude, 0xF5, 0x00}`,
  `direction` is `1` (CW) or `2` (CCW), `magnitude` is an unsigned
  percent (0-100).
- Encoder register `0x46`: split-phase — a select write
  (`{0xFF,0xF9,port,0x00,0x46,0x00,0xF5,0x00}`) followed, after a
  settle, by a 4-byte little-endian signed-counter read. 1 count = 0.1
  degree of shaft rotation. The device counter is **never
  device-reset**; all rebaselining is a software offset
  (`encOffset_`).
- `begin()` primes the encoder with a median-of-3 select+read+settle
  (4 ms settle each) so `position()` starts at (software) zero without
  ever touching the device's own counter; `connected_` becomes true as
  soon as at least one of the three reads succeeds.

### 7.2 Write-shaping pipeline (`writeShapedDuty` → `writeRawDuty`)

Ordered, and the order is explicitly load-bearing (per the source
comment) — each stage guards a specific measured hardware failure mode:

1. **Exact-zero short-circuit.** `duty == 0.0f` bypasses every later
   stage and goes straight to a stop write. Rationale: the brick
   physically latches its last commanded speed across MCU resets, so
   one lost zero write is permanent.
2. **Deadband boost.** A genuine nonzero command below
   `outputDeadband_` (default 0.03, i.e. 3%) is raised to the deadband
   floor rather than being zeroed (zero is reserved for stage 1's
   meaning).
3. **Reversal dwell.** On a commanded sign flip, the port writes zero
   and holds for `reversalDwell_` ms (default 100 ms) before shipping
   the new sign — an instantaneous H-bridge flip is known to latch the
   `0x46` encoder readback (the "encoder wedge"), so the flip is
   staged through zero.
4. **Sigma-delta duty quantizer.** The brick only accepts integer
   percent; a running fractional carry (`dutyCarry_`) preserves
   sub-percent resolution (~8 mm/s per count) across cycles by
   dithering the emitted integer up/down. The carry is **discarded**
   whenever a stop is written, so a stopped wheel cannot creep from
   accumulated remainder.
5. **stopNotTaken re-write.** A commanded zero re-writes even if the
   write-dedupe cache says "already written zero," whenever the wheel
   still reads motion above `kStopConfirmVelocity` (102 counts/s) —
   guards a stop write that silently failed to take mechanically.
6. **Min-write throttle + slew**, both **bypassed for a stop write**:
   - throttle: skip the write if less than `writeThrottle_` (default
     19,000 µs) has elapsed since the last successful write — paces
     writes to keep the brick's own controller stable.
   - slew: limits the per-write change to `slewRate_` (default 25) pct
     per write, except on the very first write ever (the
     `kNeverWritten` sentinel is exempted — a slew-clamped first write
     from that sentinel once produced a wrong-direction command and
     triggered a wedge).
   - a write is only "committed" (updates `lastWrittenPct_`/
     `lastWriteTimeUs_`) on I2C ACK; a NAK'd write retries on the next
     tick rather than being treated as already-applied.

`emergencyStop()` is the one call that does not depend on a healthy
`tick()`: it zeroes the staged duty and immediately calls
`writeShapedDuty(0, ...)` — which takes the exact-zero short-circuit
path (stage 1) straight to a stop write.

### 7.3 Split-phase encoder sampling

`requestSample()` issues the `0x46` select write; the kernel spends the
settle time in `Sleeper::sleepMillis(kSettle=4ms)`; `tick(nowUs)` then
executes the staged duty write (§7.2) **and** collects the encoder
(`collect()`). A successful collect updates `position()`/`velocity()`
(computed as `Δposition/Δt` between successful collects) and stamps
`sampleTimeUs_`; a failed collect leaves `sampleTimeUs_` untouched (so
the kernel's staleness gate — §6.3 point 6 — ages honestly) and clears
`connected_`.

### 7.4 Wedge detector

Ported from the firmware's `motor_armor.h`, folded into the port.
Tracks consecutive **identical** encoder position reads (raw,
unconditional of drive state):
- `identicalReads_` increments on any streak of identical connected
  reads; `wedged()` latches true once the streak reaches
  `kWedgeThreshold` = 10.
- `identicalReadsDriven_` is the same streak but additionally requires
  `|appliedDuty()| > kMotionThreshold` (0.03); `wedgeSuspect()` latches
  true at the same threshold — this is the flavor the kernel's PID
  freshness gate (§6.3) consults, since it specifically flags "we're
  commanding motion but seeing none."

## 8. Platform ports (CODAL glue)

Source: `platform_ports.h`. Thin CODAL implementations of the kernel's
`Clock`/`Sleeper`/`FiberLauncher` ports for the MakeCode (pxt-microbit)
target — each method is a single CODAL call, mirroring the firmware's
own platform layer:
- `CodalClock::nowMicros()` → `system_timer_current_time_us()`.
- `CodalSleeper::sleepMillis(ms)` → `fiber_sleep(ms)` (cooperative,
  yields to other fibers); `yield()` → `schedule()` (a bare scheduling
  point, no timed wait).
- `CodalFiberLauncher::launch(entry, ctx)` → `create_fiber(entry, ctx)`
  (the kernel's entry never returns).

## 9. Composition layer (`shims.cpp`)

This is the MakeCode-facing C++ surface — it composes the kernel with
two `NezhaMotorPort`s and the CODAL platform ports, and adds the two
pieces of application logic the kernel deliberately does not contain:

- **Odometry**: differential dead-reckoning computed from the kernel's
  `Output` wheel positions. The kernel is counts-native and has no
  chassis geometry; track width, travel calibration, and rotational
  slip moved to `MotionEngine` in sprint 003 (`motion_engine.h` —
  `odomUpdate()` reads them from `Rig::engine`). `odomUpdate()`
  converts each wheel's position delta to mm via
  `countsPerMm() = 10 / travelCalib`, then applies the standard
  differential-drive dead-reckoning update:
  `dCenter = (dLeft+dRight)/2`, `dHeading =
  (dRight-dLeft)/effectiveTrackWidth()` (track width divided by the
  measured rotational slip), integrated at the mid-step heading
  (midpoint method) into `(x, y, heading)`.
- **Move engine**: since sprint 003 this lives in
  `MotionEngine` (`motion_engine.h`/`.cpp`), shared by the blocks and
  the wire protocol; the shim's `startMove`/`updateMove`/`endMove`/
  `progress` are thin forwards onto `engine.moveX()`/`serviceMove()`/
  `endMove()`/`progress()`. `startMove` still computes a single
  duration covering both the distance and yaw axes (so an arc
  finishes as one motion), derives from it the single `cruise` that
  reproduces the legacy dual-rate math exactly, and calls
  `engine.moveX()` with a timeout backstop of
  `duration*1000 + 1500` ms (the extra covers the end-of-move taper).
  `serviceMove()` shapes each tick — acceleration ramp, end-of-move
  taper with floors, wrong-way abort — reissuing `kernel.drive()`
  every tick with a rolling 500 ms lease, and ends the move
  (commands `kernel.neutral()`) when both axes are within margin
  (10 counts distance; 4 counts yaw on a pure turn, 10 in an arc),
  the timeout deadline expires, the kernel reports `stallHalted`, or
  the robot rotates the wrong way. `progress()` reports the
  more-limiting axis's fractional completion, 0..1000.
- **Boundary convention**: integers only across the TS↔C++ boundary —
  mm, mm/s, centidegrees, centidegrees/s; kernel config values scaled
  ×1000. The TS layer owns the cm/deg student-facing units (§4.1) and
  performs all the scaling.
- **Lazy singleton**: the whole rig (`Rig` struct: two motor ports,
  platform ports, the kernel, the `MotionEngine`, odometry state) is
  constructed once on first use (`ensure()`), which also applies the
  default tuned `Config` (§11) and calls `kernel.begin()` (primes
  encoders, arms the boot zero-write). `kernel.start()` is
  **deliberately not called** (sprint 002's tick model): every
  control cycle runs on whichever fiber calls the shim's
  `tickDrive()` — one `kernel.step()` + `serviceMove()`, then
  absolute-deadline self-pacing to the 24 ms cadence. The one
  background fiber `ensure()` launches is the **starvation
  watchdog**: every ~50 ms, if something looks like it is driving and
  no tick has run for ~100 ms, it neutrals the kernel, ends the move,
  and writes a port-level zero — a resumable soft stop that never
  touches the e-stop latch. There is no explicit
  "initialize"/"connect" block — first use of any `diffDrive` block
  triggers setup.

## 10. Wiring assumptions

Left wheel on **M1** (mirrored, `fwdSign = -1`), right wheel on **M2**
(`fwdSign = +1`) — the vevov wiring, camera-verified 2026-08-20. (The
earlier tovez defaults had the side labels the other way around;
because `fwdSign` applies to both duty and encoder, odometry is
self-consistent under any sign choice, and which port is called
"left" is the free variable that sets physical rotation direction —
see the history comment on `Rig` in `shims.cpp`.) These are
compile-time defaults in `shims.cpp`'s `Rig` struct
(`NezhaMotorPort left{1, -1}; NezhaMotorPort right{2, +1};`), not
runtime-configurable from blocks.

## 11. Default tuning values (the "tovez" bake)

Kernel config set once, in `shims.cpp`'s `ensure()`, before `begin()`;
geometry defaults live on `MotionEngine`'s fields (`motion_engine.h`,
with the measurement history behind each in the field comments).
Generic kits adjust via `setGeometry()` (i.e. the `set track width` /
`set wheel calibration` blocks, §4.7) — these are measured defaults
for the reference robot, not universal constants. The geometry values
are the vevov bake (2026-08-19/20 measurements), superseding the
original tovez numbers.

| Field | Default | Units |
|---|---|---|
| `travelCalib` (MotionEngine, not Config) | 0.7878 | mm/deg |
| `trackWidth` (MotionEngine, not Config) | 114.2 | mm (caliper-measured; never adjusted to fix a turn) |
| `rotationalSlip` (MotionEngine, not Config) | 0.952 | — (camera-measured scrub; all rotational correction lives here) |
| `maxDuty` | 100.0 | % |
| `fullDutyVelocity` | 10795.0 | counts/s |
| `kp` | 0.0 | — (proportional term disabled by default) |
| `ki` | 6.0 | 1/s |
| `iMax` | 765.6 | counts/s |
| `pidMax` | 1276.0 | counts/s |
| `vMin` (speed floor) | 255.2 | counts/s |
| `posErrMax` | 127.6 | counts |
| `biasMax` | 303.7 | counts/s |
| `tauAdapt` | 30.0 | s |
| `aSteady` | 382.8 | counts/s² |
| `stallSpeed` | 191.4 | counts/s |
| `stallDemand` | 510.4 | counts/s |
| `stallWindow` | 500.0 | ms |
| `twistHoldGain` | 2.0 | 1/s (enabled 2026-08-20 — trims measured vs. commanded differential; the tovez bake shipped it off) |
| `cyclePeriod` | 24 | ms |

Fields **not** set by the default config (left at the `Config` struct's
own zero/identity defaults): `kaff` (0 → no accel feedforward),
`wheelGain`/`wheelIntercept`
(identity: gain 1.0, intercept 0.0 → no per-wheel correction),
`deficitThreshold`/`deficitWindow` (0 → deficit detector off),
`lambdaEnabled` (false → authority scaling off), `crawlPulse` (0 → off).

Nezha port shaping defaults (`nezha_port.h`, used as-is —
`configureShaping()` exists but is never called in `shims.cpp`):
`outputDeadband` 0.03, `reversalDwell` 100 ms, `slewRate` 25 pct/tick,
`writeThrottle` 19,000 µs.

## 12. Provenance and maintenance boundary

- The wheel kernel (`diffdrive.h`/`diffdrive.cpp`) is vendored from
  [`League-Robotics/radio-robot`](https://github.com/League-Robotics/radio-robot),
  where it currently lives at `src/firm/diffdrive/`, and is
  **maintained there**; this repo carries the MakeCode packaging on
  top of it. The kernel moved to that path after this package was
  first vendored — `src/firm/control/differential_drive.h` (the path
  this section, and the source files' own header comments, once
  named) is now a thin forwarding-adapter header in the upstream repo,
  not the kernel itself; the README's path was already correct. See
  `src/DESIGN.md` §2 for the one authoritative statement of the
  upstream repo, current path, and maintenance boundary — this
  section summarizes it rather than restating it independently.
- The firmware's fidelity test suite (`src/tests/diffdrive/`, in the
  radio-robot repo) holds the two copies to the same, byte-for-byte
  control law, with one documented exception — see `src/DESIGN.md` §2.
- The Nezha motor port (`nezha_port.h`/`.cpp`) is, per README, "a
  faithful reduction of that firmware's anti-latch motor leaf." Its own
  header comment is more specific: ported from
  `radio-robot src/firm/hardware/nezha/nezha_motor.cpp`, with the wedge
  detector folded in from that firmware's `motor_armor.h`, reduced to
  the 13 methods the kernel's `Motor` port interface needs.
- The kernel is deliberately **not** derived from any firmware HAL —
  it defines its own four small ports (`Motor`, `Clock`, `Sleeper`,
  `FiberLauncher`) so a MakeCode/PXT package or a MicroPython C module
  can implement the same ports against its own platform without
  inheritance coupling to the firmware's HAL. `platform_ports.h`
  (CODAL) and `nezha_port.h`/`.cpp` (Nezha over I2C) are this repo's
  own port implementations, maintained **here** (they are not vendored
  — they were "ported"/written for this target, per their own header
  comments).
- Practical implication for anyone changing this repo: the kernel
  files (`diffdrive.h`/`.cpp`) should be treated as a synced copy —
  fix a kernel bug in both this repo and the firmware repo (per the
  source comment) until the firmware itself is cut over to depend on
  this package. The port/shim files (`nezha_port.*`,
  `platform_ports.h`, `shims.cpp`, and the `src/*.ts` block-API files
  (`sim.ts`, `run.ts`, `pose.ts`, `stop.ts`, `world.ts`, `motion.ts`))
  are this repo's own and are edited here directly.

## 13. Versioning

Current version: **1.0.10** (`pxt.json`). Per stakeholder constraint:
this extension's semver must outrank the firmware's own tag scheme
(`0.YYYYMMDD.n`) for this package — hence starting at `1.0.0` rather
than `0.x`. Note `protocol.cpp`'s `kVersion` constant (reported by the
wire's ID/VER verbs) is a manually-kept mirror of this field.

## 14. Test coverage

Two test surfaces (see `tests/DESIGN.md` and `test/DESIGN.md`):

- **`tests/host/`** — the assertion-based suite (sprint 003): the
  extension's portable C++ (kernel, motion engine, v6 wire grammar,
  wire adapter) compiled for the desktop and driven from pytest via
  `ctypes` against fake ports. Run with `uv run pytest`.
- **`test/test.ts` / `test/testrig.ts`** (declared in `pxt.json`'s
  `testFiles`) — on-robot smoke/bench programs, not assertion suites.
  `test.ts` drives three playfield square tours (robot-relative,
  OTOS-guided `goToWorld`, open-loop wheels), triggered by buttons or
  wire `RUN:` commands, each as an explicit `startMove` +
  `driveTick()` loop; plus named commands for lever-arm calibration
  and probes. `testrig.ts` is the zeguz OTOS drum-rig console.
  Deployed via `tools/make_deploy.py`, which promotes them into
  `files` in a scratch build.

## 15. License

MIT.
