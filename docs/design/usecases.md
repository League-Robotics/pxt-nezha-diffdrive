# DiffDrive — Use Cases

Derived from the public block API documented in `specification.md` §4.
Actor throughout is **Student/Teacher** — a person building a MakeCode
program with `DiffDrive` blocks, on hardware or in the browser
simulator. See `specification.md` for exact block signatures, units,
and parameter ranges referenced below.

---

## UC-001: Install the Extension

**Actor**: Student/Teacher

**Preconditions**: A MakeCode for micro:bit project is open in the
browser.

**Main flow**:
1. User opens the gear menu and selects **Extensions**.
2. User pastes the repository URL
   (`https://github.com/League-Robotics/pxt-nezha-diffdrive`) into the
   search box.
3. MakeCode fetches and adds the extension.
4. The `DiffDrive` block category appears in the block palette, with
   groups Drive, Move, Pose, and Setup.

**Postconditions**: The `diffDrive` namespace's blocks are available
for use in the project; `pxt.json`'s declared dependency (`core: *`)
is satisfied automatically by the MakeCode toolchain.

**Error flows**:
- Invalid/unreachable URL: MakeCode reports the extension could not be
  loaded; no blocks are added.
- Extension is already installed: no-op / already present.

---

## UC-002: Drive at a Constant Speed or Twist

**Actor**: Student/Teacher

**Preconditions**: Extension installed. Program is running (hardware
or simulator).

**Main flow**:
1. User places a `set wheel speeds left %left right %right cm/s` block
   (independent per-wheel speeds, −50..50 cm/s each) **or** a
   `drive %speed cm/s turning %yawRate deg/s` block (body speed
   −50..50 cm/s, turn rate −180..180 deg/s).
2. On first use of any `diffDrive` block, the rig is lazily
   initialized (kernel configured with default tuning, `begin()` +
   `start()` called — see `specification.md` §9, §11).
3. The command is sent to the kernel and takes effect within one
   control cycle (~24 ms on hardware).
4. The robot drives at the commanded wheel speeds / body speed and
   turn rate **until superseded by another Drive/Move command or a
   stop**.

**Postconditions**: Kernel is in velocity mode with the last-commanded
values; wheels continue at that command indefinitely (up to the
kernel's 1-hour internal lease backstop) until changed.

**Error flows**:
- Robot is emergency-stopped (§UC-010 latched): the kernel refuses the
  drive command internally (`kRefusedEstopped`); wheels stay at zero
  until `clear emergency stop` is called. No block-level error is
  surfaced to the student program — the command is silently ineffective
  while latched.
- Commanded speed/turn-rate combination saturates a wheel's duty rail
  under load: wheel speeds may not track the exact ratio commanded
  unless "lambda enabled" tuning is turned on (off by default; see
  `specification.md` §6.3, §11) — a known, not a fault, condition.
- Motor stall detected (demanded duty with near-zero encoder motion
  sustained past `stallWindow`, default 500 ms): kernel self-halts to
  neutral until `clearStallLatch` (not currently exposed as a block —
  see gap noted in the report to team-lead).

---

## UC-003: Drive a Straight Distance

**Actor**: Student/Teacher

**Preconditions**: Extension installed; program running.

**Main flow**:
1. User places `move %distance cm turning %yaw degrees` with `yaw = 0`
   and a nonzero `distance`.
2. Block execution starts the move at the current `defaultSpeed`
   (15 cm/s unless changed, §UC-012) and blocks the running script.
3. The move engine (shim layer) computes a duration and issues a
   velocity command with a lease; on-hardware progress is tracked
   against encoder counts with a small decel margin (~2 mm).
4. When the travelled distance reaches the target (within margin), the
   kernel is commanded to neutral and the move ends.
5. Script execution resumes after the block.

**Postconditions**: Robot has stopped; pose has advanced by
approximately the commanded distance along the heading at move start.

**Error flows**:
- Move never reaches target (e.g. robot physically blocked): the
  move's lease-aligned deadline (duration + 500 ms backstop) or a
  kernel stall-halt ends the move early regardless, so the block does
  not hang forever — but the travelled distance will be short of the
  commanded value.
- `distance = 0` and `yaw = 0`: no motion is commanded; the move
  engine's computed duration is `<= 0` and `startMove` returns
  immediately with nothing issued (see `specification.md` §9).

---

## UC-004: Pivot in Place

**Actor**: Student/Teacher

**Preconditions**: Extension installed; program running.

**Main flow**:
1. User places `move %distance cm turning %yaw degrees` with
   `distance = 0` and a nonzero `yaw` (positive = CCW).
2. Same mechanics as UC-003, but only the yaw axis has a nonzero
   target; the move duration is driven by `defaultYawRate` (90 deg/s
   unless changed).
3. Robot turns in place by approximately `yaw` degrees, then stops.

**Postconditions**: Heading has changed by approximately the commanded
angle; x/y position is approximately unchanged (a true in-place pivot
depends on wheel-speed symmetry under the closed loop).

**Error flows**: Same early-termination guards as UC-003 (lease
deadline, stall halt).

---

## UC-005: Drive an Arc (Distance + Turn Together)

**Actor**: Student/Teacher

**Preconditions**: Extension installed; program running.

**Main flow**:
1. User places `move %distance cm turning %yaw degrees` with both
   parameters nonzero.
2. The move engine computes one duration covering both axes so they
   complete simultaneously — the result is a single constant-curvature
   arc, not a straight leg followed by a turn.
3. Robot follows the arc and stops when both axes reach target (or an
   early-termination condition fires).

**Postconditions**: Pose has advanced along the arc; heading has
changed by approximately `yaw` degrees.

**Error flows**: Same as UC-003/UC-004.

---

## UC-006: Drive a Curved Path to a Point

**Actor**: Student/Teacher

**Preconditions**: Extension installed; program running.

**Main flow**:
1. User places `go to x %x cm y %y cm`, giving a target point in the
   robot's **current** coordinate frame (x forward, y left).
2. The TS layer computes a constant-curvature arc from the robot's
   current heading through that point (turn angle
   `theta = 2*atan2(y,x)`; straight line if `y` is ~0; otherwise a
   signed-radius arc — see `specification.md` §4.3) and hands the
   resulting distance+yaw to the same move engine as UC-005.
3. Block blocks until the arc completes; robot ends at (approximately)
   the requested point, facing along the arc's end tangent.

**Postconditions**: Same as UC-005, with the pose displacement matching
the requested `(x, y)` point (subject to closed-loop tracking error).

**Error flows**:
- `x = 0 and y = 0`: no-op, returns immediately with nothing issued.
- Same early-termination guards as UC-003 (lease deadline, stall
  halt) apply to the underlying move.

---

## UC-007: Start a Move Without Blocking and Poll It

**Actor**: Student/Teacher

**Preconditions**: Extension installed; program running.

**Main flow**:
1. User places `start move %distance cm turning %yaw degrees`
   (or `start go to x %x cm y %y cm`) — the advanced, non-blocking
   forms of UC-003–006.
2. Script continues immediately without waiting.
3. Elsewhere in the program, user polls `moving?` to check whether the
   move is still active, and/or reads `move progress` (0–1) for a
   completion fraction.
4. User calls `stop move` when done, or lets the move complete/expire
   on its own.

**Postconditions**: Move either completes on its own (as in UC-003–006)
or is ended early by an explicit `stop move`.

**Error flows**:
- Calling `stop move` when no move is active: no-op.
- Starting a new move (or Drive command) while one is already active:
  the new command supersedes the prior move state per the kernel's
  command-sequencing (last command wins).

---

## UC-008: Run Code While Moving

**Actor**: Student/Teacher

**Preconditions**: Extension installed; program running.

**Main flow**:
1. User places `while moving %distance cm turning %yaw degrees` (or
   `while going to x %x cm y %y cm`) with a handler body that receives
   the live `(x, y, heading)` reporter parameters each iteration.
2. The move starts (same mechanics as UC-003–006); the loop body runs
   once per ~24 ms tick with the current pose while the move remains
   active.
3. Loop exits when the move completes on its own, **or** when the
   body itself calls `stop move` (e.g. on a button press or sensor
   condition).
4. On loop exit, the move is explicitly ended if it wasn't already.

**Postconditions**: Same physical end-state as UC-003–006/UC-006, plus
whatever side effects the student's loop body performed (e.g. LED
display updates, as in the shipped `test.ts` example).

**Error flows**: Same early-termination guards as UC-003 (lease
deadline, stall halt) still apply to the underlying move even if the
loop body never calls `stop move` itself.

---

## UC-009: Read Robot Pose

**Actor**: Student/Teacher

**Preconditions**: Extension installed; program running (rig lazily
initializes on first pose read, same as any other block).

**Main flow**:
1. User reads `pose x (cm)`, `pose y (cm)`, and/or `heading (deg)` at
   any point in the program, whether or not a move is currently
   active.
2. Each read triggers an odometry update from the kernel's latest
   encoder output, then returns the corresponding pose component.

**Postconditions**: Returns the current best estimate of position/
heading relative to the last `reset pose` (or boot, if never reset).

**Error flows**:
- Reading pose before any motion has occurred: returns `(0,0,0)`
  (or the state since the last reset) — not an error.
- Reading pose during a Drive-mode (non-Move) command: valid — pose is
  always live-updated from odometry regardless of command mode.

---

## UC-010: Reset Pose

**Actor**: Student/Teacher

**Preconditions**: Extension installed; program running.

**Main flow**:
1. User places `reset pose`.
2. Kernel-measured deltas up to that moment are consumed into the
   current pose first, then x/y/heading are reset to `(0, 0, 0)`.
3. Subsequent `pose x`/`pose y`/`heading` reads, and subsequent
   `go to`/`while going to` target points, are relative to this new
   origin.

**Postconditions**: Pose is `(0, 0, 0)`.

**Error flows**: None — always succeeds.

---

## UC-011: Stop and Emergency-Stop

**Actor**: Student/Teacher

**Preconditions**: Extension installed; robot is driving or moving.

**Main flow (normal stop)**:
1. User places `stop`.
2. Kernel is commanded to neutral through its normal stop path
   (write-shaped, anti-latch-safe — see `specification.md` §7.2); any
   active move's `moveActive` flag is cleared.
3. Robot decelerates/stops through the normal control path.

**Main flow (emergency stop)**:
1. User places `emergency stop`.
2. Kernel's e-stop latch is set **and** each motor port's
   `emergencyStop()` is called directly, bypassing the normal
   write-shaping pipeline — the fastest available stop.
3. Robot stops immediately; any active move ends.
4. All subsequent Drive/Move commands are refused (silently, at the
   kernel level) until cleared.

**Postconditions (normal stop)**: Kernel in neutral mode; further
Drive/Move commands work normally.

**Postconditions (emergency stop)**: Kernel is latched e-stopped;
Drive/Move commands are ineffective until `clear emergency stop`.

**Error flows**:
- Issuing `stop`/`emergency stop` when the robot is already stopped:
  no-op, safe.
- Forgetting to call `clear emergency stop` after an emergency stop:
  robot will not respond to any further Drive/Move blocks for the
  remainder of the program — a common "why isn't my robot moving"
  pitfall worth calling out in student-facing docs (not currently
  called out in the README).

---

## UC-012: Clear an Emergency Stop

**Actor**: Student/Teacher

**Preconditions**: Robot is in the emergency-stopped state (UC-011).

**Main flow**:
1. User places `clear emergency stop` (advanced block).
2. Kernel's e-stop latch is released.
3. Subsequent Drive/Move commands take effect normally again.

**Postconditions**: Kernel no longer refuses commands for e-stop
reasons. (Note: this clears only the e-stop latch, not an independent
stall latch — see the gap noted for `clearStallLatch` in UC-002's
error flows.)

**Error flows**: Calling when not e-stopped: no-op.

---

## UC-013: Calibrate the Chassis for a Non-Reference Kit

**Actor**: Student/Teacher (typically a teacher/builder doing initial
setup for a chassis that differs from the reference kit)

**Preconditions**: Extension installed; robot is a Nezha-brick,
two-motor differential-drive chassis with left=M2 (mirrored),
right=M1 wiring (§ Wiring assumptions).

**Main flow**:
1. User measures the actual track width (distance between wheel
   contact points) and places `set track width %width cm` with that
   value.
2. User measures (or empirically tunes) wheel travel per encoder
   degree and places `set wheel calibration %calib mm/deg` with that
   value.
3. Subsequent odometry, distance-based moves, and twist↔wheel-speed
   conversions use the updated geometry.

**Postconditions**: Rig's `trackWidth`/`travelCalib` reflect the new
chassis; distances and turns land accurately for that chassis instead
of the reference-kit defaults (115 mm track, 0.7837 mm/deg).

**Error flows**:
- Value of `0` or negative for either parameter: the shim's
  `setGeometry` only applies a value `if (value > 0)` — a zero/negative
  calibration call is silently ignored, leaving the prior value in
  place (not reset to some default).
- Called in the simulator: no effect — `setGeometry` is a no-op in the
  browser fallback (`specification.md` §5).

---

## UC-014: Tune Default Move Speed and Turn Rate

**Actor**: Student/Teacher

**Preconditions**: Extension installed; program running.

**Main flow**:
1. User places `set default speed %speed cm/s` and/or
   `set default turn rate %yawRate deg/s` (advanced blocks), typically
   near program start.
2. Value is clamped to a minimum of 1 (both fields).
3. Subsequent `move`/`goTo`/`start move`/`start go to` calls use the
   new default(s) as their target speed/turn rate.

**Postconditions**: Defaults updated for the remainder of the program
(or until changed again); does not affect any move already in
progress.

**Error flows**: Value `<= 0`: clamped up to 1, not rejected — no
error surfaced.

---

## UC-015: Advanced Kernel Tuning via the Config Escape Hatch

**Actor**: Teacher/advanced student (explicitly an "advanced" block)

**Preconditions**: Extension installed; program running; user
understands the target `ConfigField` (see `specification.md` §4.8).

**Main flow**:
1. User places `set config %field to %value`, selecting one of the 15
   `ConfigField` enum values (e.g. `PID kp`, `stall speed`, `lambda
   enabled`).
2. Value is scaled ×1000 and sent to the shim's `setKernelValue`,
   which routes to the matching kernel setter.
3. Kernel applies the new value on its next config snapshot (within
   one control cycle).

**Postconditions**: The targeted kernel `Config` field is updated;
behavior described in `specification.md` §6.3/§6.5 for that field
changes accordingly.

**Error flows**:
- Selecting a field not in the `ConfigField` enum: not possible from
  the block UI (enum-constrained); the shim's `switch` has a
  `default: break` no-op for any out-of-range integer, reachable only
  by other, non-block callers.
- Setting a nonsensical value (e.g. negative `stallWindow`): kernel
  setters reject non-finite values (`kRefusedNonFinite`) but do
  **not** range-check plausibility beyond that — an ill-chosen value
  can produce degraded or unsafe-feeling driving behavior without any
  block-level error.
- This escape hatch **cannot** reach several kernel tuning surfaces at
  all (per-wheel gain/intercept correction, adaptive-bias tuning, the
  deficit detector) — see the gap noted in `specification.md` §4.8 and
  in the report to team-lead.

---

## UC-016: Develop and Test in the Browser Simulator

**Actor**: Student/Teacher

**Preconditions**: MakeCode project open in the browser (no physical
robot required).

**Main flow**:
1. User writes a program using any `DiffDrive` blocks and runs it in
   the simulator pane instead of downloading to hardware.
2. Every block resolves to its TypeScript simulator body (a kinematic
   stand-in, `specification.md` §5) instead of the C++ shim.
3. Pose, move completion, and timing behave approximately like
   hardware (same block contracts) but do not reproduce the real
   closed-loop control law, wedge/stall detection, or I2C behavior.

**Postconditions**: Program logic (sequencing, pose reads, loop
conditions) can be validated without hardware; exact motion fidelity
(wheel correction, adaptive bias, stall/wedge behavior) is not
represented.

**Error flows**:
- Program relies on kernel tuning changes (`set config`, `set
  geometry`) having an observable effect: none in the simulator — see
  `specification.md` §5. This is a known simulator/hardware behavior
  gap, not a bug, but worth surfacing to students who tune in
  simulator and expect it to carry to hardware.
