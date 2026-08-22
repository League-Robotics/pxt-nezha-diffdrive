# DiffDrive — Full Specification

Status: existing, working codebase (v1.0.0) being brought under the CLASI
process. This specification is reconstructed from the stakeholder-written
`README.md` and from the shipped source (`main.ts`, `diffdrive.h/.cpp`,
`nezha_port.h/.cpp`, `platform_ports.h`, `shims.cpp`, `test.ts`,
`pxt.json`), which is treated as ground truth for actual behavior. Every
statement in `README.md` is preserved somewhere below; source-derived
detail beyond the README is marked as such by section.

## 1. Overview

DiffDrive is a MakeCode extension for PXT/micro:bit. It drives the
ElecFreaks Nezha brick's two-wheel differential drive **closed loop**:
an encoder-servoed wheel-speed controller (the DiffDrive kernel) runs in
its own fiber on the micro:bit at a 24 ms cadence, and every block talks
to it.

Unlike open-loop duty control, wheel speeds are measured and corrected
continuously — straight means straight, distances land on the encoder,
and the robot's pose (x, y, heading) is always available from odometry.

## 2. Package Identity

From `pxt.json`:

| Field | Value |
|---|---|
| name | `nezha-diffdrive` |
| version | `1.0.0` |
| description | "Closed-loop differential drive for the Nezha brick: encoder-servoed wheel speeds, twist and distance moves, curved go-to, and pose from odometry. The wheel controller runs in its own fiber." |
| license | MIT |
| dependencies | `core: *` |
| files | README.md, and under `src/`: diffdrive.h, diffdrive.cpp, platform_ports.h, nezha_port.h, nezha_port.cpp, otos_port.h, otos_port.cpp, serial_transport.h, serial_transport.cpp, radio_transport.h, radio_transport.cpp, protocol.h, protocol.cpp, shims.cpp, main.ts |
| testFiles | test/test.ts, test/testrig.ts |
| supportedTargets | microbit |
| preferredEditor | tsprj |

Supported targets, per README: "for PXT/microbit". (The README notes
this metadata line "is needed for package cataloging.")

## 3. Installation

In [MakeCode for micro:bit](https://makecode.microbit.org/), open a
project, click the gear menu → **Extensions**, and paste this repo's
URL:

```
https://github.com/League-Robotics/pxt-nezha-diffdrive
```

## 4. Public API (block reference)

The public surface is the `diffDrive` namespace in `main.ts`
(`//% color=#0f9c5a icon="" block="DiffDrive"`), organized into block
groups: **Drive**, **Move**, **Pose**, **Setup**. Every exported
function in `main.ts` is documented below; the README's example listing
is a representative subset, not the full API — every block that exists
in code is included here.

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

Velocity commands **run until superseded by another command or a
stop**. They do not block.

| Block | Function | Params | Behavior |
|---|---|---|---|
| `set wheel speeds left %left right %right cm/s` | `setWheelSpeeds(left, right)` | `left`, `right`: cm/s, block-editor range −50..50 each | Sets the two wheel speeds directly. Converted to mm/s (`×10`) and sent to the kernel as `_setWheels`. |
| `drive %speed cm/s turning %yawRate deg/s` | `driveTwist(speed, yawRate)` | `speed`: cm/s, range −50..50; `yawRate`: deg/s, range −180..180 | Drives with a body forward speed and a yaw (turn) rate simultaneously. Converted to mm/s (`×10`) and centidegrees/s (`×100`) and sent to the kernel as `_driveTwist`. |
| `stop` | `stop()` | — | Normal stop: commands the kernel to neutral (`_stopAll`). Motors ramp to zero through the kernel's normal stop path (see §6.3/§7.2); not a hardware-level emergency stop. |
| `emergency stop` | `emergencyStop()` | — | Emergency stop: latches the kernel's e-stop and calls the motor ports' `emergencyStop()` directly (`_estopAll`), bypassing normal shaping. Stays latched until `clearEmergencyStop()`. |
| `clear emergency stop` *(advanced)* | `clearEmergencyStop()` | — | Clears the e-stop latch (`_estopClear`) so driving can resume. |

### 4.3 Move group — position-mode moves (blocking)

Position-mode moves **wait until the move is done** before the block's
program flow continues.

| Block | Function | Params | Behavior |
|---|---|---|---|
| `move %distance cm turning %yaw degrees` | `move(distance, yaw)` | `distance`: cm to travel; `yaw`: degrees to turn, CCW+ | Drives a distance while turning a yaw angle, then stops. Setting both at once produces an arc. Internally: `startMove(distance, yaw)` then polls `_updateMove()` every 10 ms until it returns false. |
| `go to x %x cm y %y cm` | `goTo(x, y)` | `x`: forward distance cm; `y`: leftward distance cm (robot frame) | Drives a curved (constant-curvature) path to a point in the robot's current coordinate frame, then stops. Blocks the same way as `move`. |

`goTo`'s arc math (in `startGoTo`, shared by the blocking and async
forms): given target `(x, y)` in the robot frame with the robot
starting at heading 0 along +x —
- turn angle `theta = 2 * atan2(y, x)` radians, signed
- if `|y| < 0.01`: straight line, arc length `s = x`
- else: signed radius `radius = (x² + y²) / (2y)`, arc length
  `s = radius * theta`
- the resulting `(s, theta)` is handed to `startMove` as
  distance-and-yaw.
- `x == 0 && y == 0` is a no-op (returns immediately, no move issued).

### 4.4 Move group — position-mode moves (async)

Non-blocking variants for interleaving a move with other logic via
polling.

| Block | Function | Params | Behavior |
|---|---|---|---|
| `start move %distance cm turning %yaw degrees` *(advanced)* | `startMove(distance, yaw)` | same as `move` | Starts a distance/yaw move without waiting. Uses the current `defaultSpeed` (default 15 cm/s) and `defaultYawRate` (default 90 deg/s) as the move's speed/turn-rate targets. Poll `isMoving()` / call `stopMove()`. |
| `start go to x %x cm y %y cm` *(advanced)* | `startGoTo(x, y)` | same as `goTo` | Starts a go-to without waiting; computes the arc (see §4.3) and calls `startMove` internally. |
| `moving?` | `isMoving()` | — | Returns whether a move is currently running (`_updateMove()`; this call also advances the move state machine — see §9). |
| `move progress` *(advanced)* | `moveProgress()` | — | Fraction of the current move completed, 0 to 1 (`_progress() / 1000`). |
| `stop move` | `stopMove()` | — | Ends the current move now; no-op if none is active (`_endMove`). |

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
| 8 | `SpeedFloor` | "speed floor" | `vMin` |
| 9 | `PosErrMax` | "position error limit" | `posErrMax` |
| 10 | `StallSpeed` | "stall speed" | `stallSpeed` |
| 11 | `StallDemand` | "stall demand" | `stallDemand` |
| 12 | `StallWindow` | "stall window ms" | `stallWindow` |
| 13 | `LambdaEnabled` | "lambda enabled" | `lambdaEnabled` |
| 14 | `CrawlPulse` | "crawl pulse" | `crawlPulse` |

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
(hardware, §9) and a TypeScript body in `main.ts` (browser simulator,
used when a MakeCode program runs in the web simulator rather than on
device). The simulator is a minimal kinematic stand-in, not a
reproduction of the closed-loop control law:

- Maintains `simX`, `simY`, `simHeading` (mm, mm, rad) and
  `simVel`/`simYawRate` (mm/s, rad/s), integrated by `simIntegrate()`
  on every call using wall-clock delta time (`control.millis()`),
  clamped so that `dt < 0` or `dt > 0.5s` is treated as `dt = 0`
  (guards clock jumps).
- `setWheelSpeeds`: sets `simVel` to the mean and `simYawRate` to the
  half-difference over an assumed track width (`/115` mm, matching the
  hardware default track width), and cancels any active simulated move.
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
- `poseX`/`poseY`/`poseHeading`/`resetPose` read/reset the simulated
  pose.
- `setGeometry`/`setKernelValue` are no-ops in the simulator — track
  width, wheel calibration, and kernel tuning have no simulated effect.

## 6. Kernel: `DiffDrive::DifferentialDrive` (closed-loop wheel-speed controller)

Source: `diffdrive.h` / `diffdrive.cpp`. This is the vendored control
kernel — see §12 for its provenance and maintenance boundary. It is
platform-agnostic: the only include is `<cstdint>`, and it depends on
four small ports it defines itself (`Motor`, `Clock`, `Sleeper`,
`FiberLauncher`) rather than any firmware HAL.

### 6.1 Execution model

- Runs its own cooperative fiber, started by `start()` via the injected
  `FiberLauncher`; the fiber body (`run()`) calls `step()` once per
  cycle and sleeps to an **absolute** deadline (`cycleStartUs +
  cyclePeriod*1000`), tracking `cycleOverrunCount_` when a cycle
  overruns instead of sleeping.
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
  chassis geometry; track width and travel calibration live here
  (`Rig::trackWidth`, `Rig::travelCalib`). `odomUpdate()` converts each
  wheel's position delta to mm via `countsPerMm() = 10 /
  travelCalib`, then applies the standard differential-drive
  dead-reckoning update: `dCenter = (dLeft+dRight)/2`, `dHeading =
  (dRight-dLeft)/trackWidth`, integrated at the mid-step heading
  (midpoint method) into `(x, y, heading)`.
- **Move engine**: a start/update/end state machine layered over the
  kernel's velocity interface, implementing position-mode moves
  (distance+yaw; `goTo`'s arc math lives in the TS layer, §4.3).
  `startMove` computes a single duration covering both the distance
  and yaw axes (so they complete simultaneously — an arc finishes as
  one motion, not two sequential ones), derives a constant
  velocity/twist from that duration, and issues a `kernel.drive()`
  with a lease of `duration*1000 + 500` ms as a backstop.
  `updateMove()` (called by the TS layer's `_updateMove()` shim, which
  every blocking/loop/polling form is built on) compares progress
  against the target with a 25-count (~2 mm) decel margin on each
  axis, and ends the move (commands `kernel.neutral()`, clears
  `moveActive`) when both axes are done, the lease-aligned deadline
  has expired, or the kernel reports `stallHalted`. `progress()`
  reports the more-limiting of the two axes' fractional completion,
  0..1000. `endMove()` ends a move early if one is active.
- **Boundary convention**: integers only across the TS↔C++ boundary —
  mm, mm/s, centidegrees, centidegrees/s; kernel config values scaled
  ×1000. The TS layer owns the cm/deg student-facing units (§4.1) and
  performs all the scaling.
- **Lazy singleton**: the whole rig (`Rig` struct: two motor ports,
  platform ports, the kernel, odometry state, move-engine state) is
  constructed once on first use (`ensure()`), which also applies the
  default tuned `Config` (§11), calls `kernel.begin()` (primes
  encoders, arms the boot zero-write) and `kernel.start()` (the kernel
  fiber free-runs from here on). There is no explicit
  "initialize"/"connect" block — first use of any `diffDrive` block
  triggers setup.

## 10. Wiring assumptions

Left wheel on **M2** (mirrored, `fwdSign = -1`), right wheel on **M1**
(`fwdSign = +1`) — the standard two-motor chassis. These are compile-time
defaults in `shims.cpp`'s `Rig` struct
(`NezhaMotorPort left{2, -1}; NezhaMotorPort right{1, +1};`), not
runtime-configurable from blocks.

## 11. Default tuning values (the "tovez" bake)

Set once, in `shims.cpp`'s `ensure()`, before `begin()`/`start()`.
Comment in source: "tovez-measured defaults; generic kits adjust via
`setGeometry()`" (i.e. via the `set track width` / `set wheel
calibration` blocks, §4.7) — these are defaults for the reference kit,
not universal constants.

| Field | Default | Units |
|---|---|---|
| `travelCalib` (Rig, not Config) | 0.7837 | mm/deg |
| `trackWidth` (Rig, not Config) | 115.0 | mm |
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
| `cyclePeriod` | 24 | ms |

Fields **not** set by the default config (left at the `Config` struct's
own zero/identity defaults): `kaff` (0 → no accel feedforward),
`twistHoldGain` (0 → twist-hold trim off), `wheelGain`/`wheelIntercept`
(identity: gain 1.0, intercept 0.0 → no per-wheel correction),
`deficitThreshold`/`deficitWindow` (0 → deficit detector off),
`lambdaEnabled` (false → authority scaling off), `crawlPulse` (0 → off).

Nezha port shaping defaults (`nezha_port.h`, used as-is —
`configureShaping()` exists but is never called in `shims.cpp`):
`outputDeadband` 0.03, `reversalDwell` 100 ms, `slewRate` 25 pct/tick,
`writeThrottle` 19,000 µs.

## 12. Provenance and maintenance boundary

- The wheel kernel (`diffdrive.h`/`diffdrive.cpp`) is vendored from the
  [radio-robot](https://github.com/League-Robotics/radio-robot)
  firmware and is **maintained there**; this repo carries the MakeCode
  packaging. Per README: vendored from `src/firm/diffdrive/`, comments
  stripped for size.
  **Note** — the source files' own header comments describe a more
  specific origin: `diffdrive.h` says the kernel is "unchanged from
  the firmware tree (`src/firm/control/`) it is extracted from," and
  `diffdrive.cpp`'s header says it was "EXTRACTED from
  `src/firm/control/differential_drive.cpp` with only the namespace
  (`Control` → `DiffDrive`) and include changed... fix bugs THERE
  first or HERE first, but always in both — until the firmware is cut
  over to consume this package directly." This is a discrepancy
  between the README's stated path (`src/firm/diffdrive/`) and the
  code's own stated path (`src/firm/control/`); flagged here rather
  than silently resolved (see report to team-lead).
- The firmware's fidelity test suite (`src/tests/diffdrive/`, in the
  radio-robot repo) holds the two copies to the same, byte-for-byte
  control law.
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
  `platform_ports.h`, `shims.cpp`, `main.ts`) are this repo's own and
  are edited here directly.

## 13. Versioning

Current version: **1.0.0**. Per stakeholder constraint: this
extension's semver must outrank the firmware's own tag scheme
(`0.YYYYMMDD.n`) for this package — hence starting at `1.0.0` rather
than `0.x`.

## 14. Test coverage

`test.ts` (declared in `pxt.json`'s `testFiles`) is a smoke program,
not a unit-test suite with assertions: the square tour in four moves,
plus a loop-form leg with a live pose readout. Runs both in the
simulator (against the kinematic stand-in, §5) and on hardware (against
the real kernel):

- Button A: `resetPose()`, then four iterations of `move(50, 0)`
  (50 cm straight) followed by `move(0, 90)` (pivot 90° CCW) — a
  50 cm-sided square — then shows the rounded `poseX()` on the LED
  matrix.
- Button B: `whileMoving(50, 0, ...)` driving 50 cm straight while
  plotting a live bar graph of `x` progress on the LED matrix each
  iteration, then an explicit `stop()` after the loop exits.

## 15. License

MIT.
