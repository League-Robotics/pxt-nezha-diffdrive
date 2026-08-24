---
id: '006'
title: 'Motion correctness: goTo geometry and odometry truth'
status: done
branch: sprint/006-motion-correctness-goto-geometry-and-odometry-truth
use-cases:
- SUC-001
- SUC-002
- SUC-003
- SUC-004
- SUC-005
- SUC-006
issues:
- goto-geometry-pivot-split-miss.md
- cross-fiber-stop-settle-window-race.md
- continuous-mode-odometry-chord-error.md
- otos-seed-heading-clamp.md
- brick-reset-odometry-teleport.md
- no-encoder-odometry-posesource-fallback.md
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sprint 006: Motion correctness: goTo geometry and odometry truth

> **Arc position.** This sprint is the third planned out of the
> 2026-08-23 code review (`docs/code-review/2026-08-23/review.md`), after
> sprint 004 (`004-radio-full-v6-transport-telemetry-frame-firmware`,
> ticketed — the radio/wire-grammar arc) and sprint 005
> (`005-retrofit-bench-tooling-onto-the-v6-telemetry-stream`, roadmap —
> the bench-tooling arc). The three sprints partition the same review's
> findings by theme, not by dependency: 004/005 are a transport-and-tooling
> pair that must run in that internal order (005 waits on 004's hardware
> checkpoint), while this sprint is independent of both — it touches
> `motion_engine`/`diffdrive`/`otos_port`/`shims` tick paths, not the wire
> layer or the bench scripts. It comes after 004/005 in sprint numbering
> because the review's transport-and-telemetry gaps were triaged as the
> more urgent arc first; nothing here blocks on or is blocked by 004/005
> landing, so this sprint could in principle be pulled forward or run
> interleaved without harm.

## Goals

Group the code review's motion-correctness cluster — five findings whose
common thread is "the robot goes where it is told, and the pose it
reports is the truth" — into one sprint, fixed together because they
share that theme, not because they share a code path:

- **goTo geometry** (`goto-geometry-pivot-split-miss.md`, HIGH): fix the
  pivot-split miss, the long-way-around degeneracy, and the dead `arrive`
  tolerance in the `goTo`/`moveX` path. Add host tests **above** the 50°
  pivot-split threshold and for behind-the-robot targets — the specific
  gap that let all three ship green.
- **Stop timing** (`cross-fiber-stop-settle-window-race.md`, HIGH):
  deliver a cross-fiber/watchdog-triggered stop inside the kernel's
  settle window every time, not ~1/3 of the time, without adding a second
  ticker.
- **Continuous-mode odometry** (`continuous-mode-odometry-chord-error.md`,
  MED): fold `odomUpdate()` into the velocity-mode tick path so pose stays
  correct during continuous driving instead of integrating one long chord
  at the next read.
- **Heading seed wrap** (`otos-seed-heading-clamp.md`, MED): wrap seeded
  headings to ±180° instead of clamping, so a 0–360°-convention or
  unwrapped-odometry seed doesn't silently poison the OTOS pose source.
- **Brick reset discontinuity** (`brick-reset-odometry-teleport.md`,
  MED): run the decisive bench experiment (power-cycle the brick
  mid-drive, watch DIAG ordinals 10/11 and pose) to confirm or rule out
  the ~4 m teleport, then — if confirmed — rebaseline odometry on an
  impossible-delta discontinuity instead of integrating it.
- **Encoder `PoseSource` fallback for GO_TO_W**
  (`no-encoder-odometry-posesource-fallback.md`; added after this
  roadmap was first written — see detail-planning note below): give
  `GO_TO_W` an encoder-odometry `PoseSource` so it works on the fleet's
  OTOS-less robots (tovez, gopiv, zeguz) instead of answering
  `kUnimplemented` on every one of them. Claimed here because it shares
  the heading-unwrap work item 4 already does and the same `PoseSource`
  seam item 5's rebaseline fix touches.

**Detail-planning note (sprint-planner):** this sixth issue was linked
to the sprint after the roadmap body above was written, so "five
findings"/"five defects" below describes the roadmap's original scope;
the Architecture section (below) covers all six, and the sixth issue's
fix is deliberately sequenced to depend on the fifth's (see Tickets).

## Problem

All five defects come from the 2026-08-23 code review's kernel/odometry
findings (R-02/03/04, R-08, R-09, R-05, R-07), each independently
CONFIRMED — four by static re-derivation (arithmetic in
`verify-kernel.md`/`verify-blocks.md`), one (`brick-reset-odometry-teleport`)
with the code path statically certain but the hardware premise
unverifiable without a bench run. Left as-is:

- A `goTo` call can miss its target by over 100 mm on any split above 50°,
  or spin nearly 360° for a target behind the robot, and the host test
  suite stays green because it never exercises either case.
- A stop issued from another fiber, or a watchdog-timed stop, has roughly
  a 1-in-3 chance of landing in the kernel's settle window and being held
  for another 100-150 ms — reintroducing the per-turn overshoot the
  settle logic exists to remove.
- Continuous velocity-mode driving silently decouples from odometry:
  pose is only ever right immediately after a discrete move, never during
  or after sustained twist-driven motion.
- A heading seed outside ±180° (any 0-360°-convention source, or the
  project's own unwrapped odometry heading echoed back) clamps instead of
  wrapping, disagreeing with the odometry pose source by up to ~170° —
  poisoning exactly the drift measurement the reseed exists to make.
- If a brick MCU reset actually zeroes the encoder registers mid-session,
  the two-strike glitch armor accepts the resulting counter jump as truth,
  teleporting pose by ~4 m with no rebaseline and no diagnostic signal.

## Solution

Per-issue, at a level of detail the "What to do" section of each issue
file already states in full (read `clasi/issues/<file>` at detail-planning
time for the exact approach) :

1. `goto-geometry-pivot-split-miss.md` — recompute the post-pivot leg
   toward the actual target (or split the arc geometrically rather than
   kinematically); normalize theta to ±180° and take the short arc;
   implement the arrival-tolerance check that is already parsed but
   unimplemented.
2. `cross-fiber-stop-settle-window-race.md` — deliver staged neutral
   inside `step()`'s settle path, or push duty directly through the
   anti-latch pipeline, honoring the one-ticker-per-move constraint from
   `settle-tick-loop-is-not-host-testable.md`.
3. `continuous-mode-odometry-chord-error.md` — call `odomUpdate()` from
   `tickDrive`'s velocity-mode branch, preserving the same one-ticker
   constraint.
4. `otos-seed-heading-clamp.md` — wrap the heading (one modulo) before
   the `writePoseMm` register write; while in there, resolve or
   re-document the wrapped-vs-unwrapped heading contract mismatch noted
   against `motion_engine.h:139` (KERN-08).
5. `brick-reset-odometry-teleport.md` — split honestly (per detail-
   planning direction) into a host-testable half and a bench-only half.
   Host-testable now, unconditionally: the glitch armor's own two-strike
   acceptance of an implausible jump as truth is a real defect
   independent of what causes the jump (a brick reset is the named
   hypothesis, not the only possible one) — rebaseline on the
   discontinuity instead of integrating it, with a DIAG counter
   surfacing when it fires. Bench-only, separately: run the decisive
   experiment (prove the DIAG-capture instrument is watching, per this
   project's measurement doctrine) to confirm or rule out the
   brick-MCU-reset premise specifically and record the real numbers —
   this does not gate the code fix, which ships regardless.
6. `no-encoder-odometry-posesource-fallback.md` — new `EncoderPoseSource`
   over the existing Rig odometry; one selection point in
   `engineGoToW()` (OTOS when connected, encoder otherwise). Inherits
   item 5's rebaseline guarantee rather than re-implementing it, so this
   item is sequenced after item 5 in Tickets.

## Success Criteria

- `GO_TO_R`/`goTo` hits its target within tolerance for splits above and
  below the 50° pivot threshold, and for targets behind the robot; new
  host tests cover both cases and fail on the pre-fix behavior.
- A stop issued mid-settle-window is delivered within that same tick,
  every time — not probabilistically — with no added ticker.
- A host test drives a full circle under continuous velocity-mode
  driving and reads pose back near the origin.
- A host test seeds heading at 350°/-350°/720° and reads back the
  correctly wrapped equivalent; the OTOS pose source's wrapped-vs-
  unwrapped contract is consistent with `motion_engine.h`.
- The rebaseline-on-discontinuity fix ships with a DIAG counter
  surfacing when it fires, host-tested, regardless of the bench
  outcome (the code-level defect is real independent of root cause).
  The brick-reset bench experiment is run separately and its result
  (confirmed or ruled out) is recorded in
  `brick-reset-odometry-teleport.md`; it does not gate this criterion.
- **(Added — issue 6)** `GO_TO_W` dispatches successfully on a robot
  with no connected OTOS, driving on encoder odometry instead of
  answering `kUnimplemented`; a host test exercises `goToW()` through
  the new `EncoderPoseSource` with no OTOS anywhere in the link.
- All new/changed host tests pass; no regression in existing
  `tests/host` coverage.

## Scope

### In Scope

- `src/motion_engine.*` — goTo/moveX geometry: pivot-split leg
  recomputation, theta normalization, arrival-tolerance check.
- `src/shims.cpp` — settle-window-safe stop delivery (`stopAll()`/
  `endMove()`/`updateMove()`, reusing the existing starvation-watchdog
  port-level primitive — **not** a `diffdrive.*` kernel change); tick
  paths — continuous-mode `odomUpdate()` folding; no change to the
  one-ticker-per-move constraint.
- `src/otos_port.*` — heading wrap on seed (`setPose()`), delegating
  to a new host-portable `heading_wrap.h` (`OtosPort` itself cannot be
  host-compiled — see Architecture).
- `src/nezha_port.*` — glitch-armor rebaseline-on-discontinuity, and its
  extracted host-portable decision logic (new: `encoder_glitch_armor.h`).
- **(Added — issue 6)** A new host-portable `encoder_pose_source.h`
  (`EncoderPoseSource : diffDrive::PoseSource`) plus the selection-rule
  wiring in `shims.cpp::engineGoToW()` (OTOS when connected, encoder
  otherwise) and the corresponding `wire_adapter.cpp` comment update
  (GO_TO_W no longer documents an OTOS-required refusal).
- `tests/host` — new/extended host tests for all six fixes: above-50°
  and behind-robot goTo cases, settle-window stop timing, continuous-mode
  circle-closure, heading-wrap seeding, discontinuity-rebaseline coverage
  (host-testable regardless of the bench result), and a `goToW()` test
  through the new encoder fallback with no OTOS in the link.
- The brick-reset bench experiment itself (hardware step, DIAG ordinals
  10/11 + pose capture), recorded back into
  `brick-reset-odometry-teleport.md`.

### Out of Scope

- The wire grammar / protocol (`radio-robot-lib`, `WireHandler`,
  `RadioSink`, frame formats) — sprint 004's domain.
- `tools/` bench scripts and `tools/tlm.py` — sprint 005's domain.
- Any issue not in this sprint's linked set (see the code review annex
  and `clasi/issues/` for the rest of the backlog — notably the other
  R-0x findings not claimed here).
- Detail planning, architecture, use cases, and tickets — this is a
  roadmap-phase sprint; those are produced when this sprint is
  detail-promoted.

## Test Strategy

Host-only (`tests/host`), consistent with this project's existing
practice of catching kernel/geometry defects without hardware wherever
possible:

- New geometry tests for `goTo`/`moveX` deliberately above the 50° split
  threshold and for targets behind the robot — the exact gap the code
  review found the existing suite silent on.
- A settle-window timing test that issues a stop at a point in the tick
  cycle known to fall inside the settle window and asserts the stop is
  delivered within that tick, not on the next watchdog cycle.
- A continuous-mode odometry test: drive a closed circle under constant
  twist in an unconditional tick loop, assert pose returns near origin.
- A heading-wrap test: seed 350°/-350°/720°, assert the register and the
  read-back heading match the wrapped equivalent.
- The brick-reset case's rebaseline-on-discontinuity logic is
  host-testable now (script an implausible-then-consistent raw-counts
  jump through `EncoderGlitchArmor` directly — it has no I2C/hardware
  dependency to fake) and does not wait on the bench confirming the
  premise; only the real-world trigger (an actual brick MCU reset) is
  bench-only by nature.
- **(Added — issue 6)** A `goToW()` test through `EncoderPoseSource`
  with no OTOS in the link (mirroring `test_motion_engine_gotow.py`'s
  existing `FakePoseSource` pattern), plus a test that
  `engineGoToW()`'s selection rule picks the encoder source when
  `OtosPort::connected()` is false.

## Architecture

**Substantial** — this sprint touches 5 modules (`motion_engine.cpp`,
`shims.cpp`, `otos_port.cpp`, `nezha_port.cpp`, `wire_adapter.cpp`
comment/behavior) and introduces 3 new host-portable components
(`heading_wrap.h`, `EncoderGlitchArmor`, `EncoderPoseSource`) with new
cross-module dependencies (`OtosPort` → `heading_wrap.h`;
`NezhaMotorPort` → `EncoderGlitchArmor`; `Rig`/`shims.cpp` →
`EncoderPoseSource`) — well past the compact tier's "one module, no
new dependency" bar. The full 7-step methodology applies, diagrams
included. (`heading_wrap.h` was added during ticket-writing, after the
architecture review recorded below: `otos_port.h` unconditionally
includes `pxt.h`, so `OtosPort` cannot be host-compiled at all, and the
sprint's own success criterion — a host test proving the wrap — is
otherwise unmeetable. Same extraction pattern as `EncoderGlitchArmor`,
smaller in scope; noted here for transparency rather than re-run
through a second review cycle.)

This project has opted into the persistent per-subsystem design-doc
overlay model (`design_docs: enabled`), so the full architecture
write-up — module table, the component diagram, Design Rationale, and
Migration Concerns — lives in this sprint's `design/` overlay, not
here: see
[`design/DESIGN.md`](design/DESIGN.md) (the edited copy) and
[`design/DESIGN.diff.md`](design/DESIGN.diff.md) (the reviewable diff
against the canonical `src/DESIGN.md`). `docs/design/design.md` (the
system-level doc) was evaluated and **not** seeded — none of this
sprint's changes touch its global conventions (units, sign convention,
execution/tick model, sensor doctrine all hold unchanged; the "one
ticker per move" invariant is explicitly preserved, not relaxed).

**Summary for readers of this file alone** (see the overlay for full
detail): `goToR()` gains its own pivot-split geometry so it reaches its
target exactly instead of inheriting `moveX()`'s generic split, honors
`arrive` as a no-op radius, and takes the short arc. `stopAll()`/
`endMove()`/`updateMove()`'s completion path each add an immediate
port-level stop (reusing the starvation watchdog's existing
`Motor::emergencyStop()` primitive) alongside the pre-existing staged
`kernel.neutral()`, closing the cross-fiber settle-window race without
a second ticker and without touching the vendored kernel.
`tickDrive()` folds `odomUpdate()` into every tick unconditionally
(continuous-mode odometry no longer waits for the next pose read).
`OtosPort::setPose()` wraps the heading channel (via new, host-
portable `heading_wrap.h` — `OtosPort` itself cannot be host-compiled
at all) before quantizing (fixing the seed-heading clamp). A new
`EncoderGlitchArmor` (host-
portable, extracted from `NezhaMotorPort::collect()`) turns the
glitch armor's existing two-strike acceptance of an implausible jump
into a rebaseline instead of an integrated teleport, host-testable for
the first time. A new `EncoderPoseSource` wraps the Rig's existing
(already-unwrapped) odometry as a second `PoseSource` implementation;
`engineGoToW()` now selects `OtosPort` or `EncoderPoseSource` in one
place instead of refusing outright when no OTOS is connected — this
inherits the glitch-armor's rebaseline guarantee for free (no new
epoch-tracking code needed in the pose source itself), which is why
issues 5 and 6 are sequenced back-to-back in Tickets below. The kernel
(`diffdrive.{h,cpp}`) stays byte-unchanged throughout — no cross-repo
resync with the radio-robot firmware is triggered by this sprint.

**Known risk, not newly introduced:** the stop-delivery fix's new
port-level write shares the Nezha brick's I2C bus with the encoder
settle window; this collision window already exists today in the
starvation watchdog's own port writes, and the existing fault-counting
path (`i2cFaultCount_`) already absorbs a corrupted sample as a held
value, not a silent bad read — see the overlay's Migration Concerns for
the full analysis and ticket 002's recommended test.

## Use Cases

Two of docs/design/usecases.md's UC-001..UC-016 are directly affected
(UC-006, UC-011); one is restored to match its already-written
postcondition (UC-009); two of this sprint's six fixes have no
block-facing use case at all (SEED and GO_TO_W are wire-only verbs —
`usecases.md` predates the wire protocol entirely, per `src/DESIGN.md`
§0/sprint 004's own precedent for this).

### SUC-001: Drive a Curved Path to a Point, Correctly, Past the Pivot-Split Threshold
Parent: UC-006 (Drive a Curved Path to a Point)

- **Actor**: Student/Teacher
- **Preconditions**: Extension installed; program running; a `go to`
  target whose bearing from the robot's current heading is ≥ 25°
  (equivalently, whose implied turn angle `theta = 2*atan2(y,x)` is
  ≥ 50°, `moveX`'s pivot-first split threshold), including a target
  behind the robot.
- **Main Flow**:
  1. User places `go to x %x cm y %y cm` with a target past the
     pivot-split threshold (e.g. (100, 100) cm) or behind the robot
     (e.g. (−100, 1) cm).
  2. `goToR()` computes its own pivot-then-chord decomposition toward
     the actual target (not `moveX`'s generic arc-then-split, which
     reaches a different endpoint for the same inputs), normalizing
     the turn angle to the short arc first.
  3. Block blocks until the two-phase move completes.
- **Postconditions**: Robot ends within tolerance of the requested
  `(x, y)` point (UC-006's existing postcondition, now actually true
  above the split threshold and for behind-the-robot targets — before
  this fix, (100, 100) cm missed by ~115 mm out of a 141 mm hop, and
  (−100, 1) cm pivoted ~359° and drove ~31 m before this sprint's
  normalize-to-short-arc fix).
- **Acceptance Criteria**:
  - [ ] A host test at bearing ≥ 25° (e.g. (100, 100)) asserts the
        kinematically-integrated endpoint of the issued segments is
        within tolerance of the target — this exact case misses by
        ~115 mm today.
  - [ ] A host test with a target behind the robot (e.g. (−100, 1))
        asserts a short-arc pivot (≤ ~180°), not the long way around.
  - [ ] A host test at/just below the 25°/50° threshold still passes
        (no regression to the existing plain-arc case).
  - [ ] A host test seeds the robot at (or within noise of) the target
        and asserts `goToR()` is a no-op (the `arrive` radial gate).

### SUC-002: A Stop Lands Within the Same Tick, From Any Fiber
Parent: UC-011 (Stop and Emergency-Stop)

- **Actor**: Student/Teacher
- **Preconditions**: Robot is driving or moving under a `while
  (driveTick())` loop on one fiber; `stop`/`stop move` (or the
  `isMoving()`/`move progress` poller ending a move at its deadline) is
  issued from a different fiber (e.g. a button handler) while the
  ticking fiber is inside the kernel's ~8 ms settle window.
- **Main Flow**:
  1. User's button-press handler (a separate CODAL fiber) calls `stop`
     while the drive-tick fiber is mid-`step()`.
  2. The stop path stages `kernel.neutral()` (as before) **and** pushes
     an immediate port-level zero write to both motors (new — reuses
     the starvation watchdog's own `Motor::emergencyStop()` primitive).
  3. Robot decelerates/stops within the current tick, not the next
     ~100–150 ms watchdog cycle.
- **Postconditions**: Same as UC-011's existing "normal stop"
  postcondition (kernel in neutral; further Drive/Move commands work
  normally) — delivered every time this scenario occurs, not roughly
  a third of the time as before this fix. The e-stop latch is untouched
  (this stays the resumable "soft stop" family, not e-stop).
- **Acceptance Criteria**:
  - [ ] A host test scripts a stop call landing inside the settle
        window (via the existing `FakeSleeper`/`FakeMotor` harness
        pattern) and asserts the motor's commanded duty reads zero
        within that same tick, not after an additional watchdog-scale
        delay.
  - [ ] No new fiber/ticker is introduced (`tests/host`'s existing
        one-ticker-per-move assertions, if any, still pass unchanged).
  - [ ] The fix does not set `estopLatch_`; a fresh `driveTick()` call
        after the stop resumes motion with no `clearEmergencyStop()`
        needed.

### SUC-003: Pose Stays Live During Continuous-Mode Driving
Parent: UC-009 (Read Robot Pose)

- **Actor**: Student/Teacher
- **Preconditions**: A `while (driveTick())` loop drives continuous
  velocity-mode commands (`setWheelSpeeds`/`driveTwist`), not a
  move-engine move.
- **Main Flow**:
  1. User drives a closed circle at constant twist under an
     unconditional `while (driveTick())` loop for several seconds.
  2. Each tick now folds `odomUpdate()` unconditionally, not only while
     a move-engine move is active.
  3. User reads `pose x`/`pose y`/`heading` at any point during or
     after the drive.
- **Postconditions**: Pose reflects the actual curved path driven so
  far (near the origin after a closed circle), matching UC-009's
  existing postcondition text ("pose is always live-updated from
  odometry regardless of command mode") — which, before this fix, was
  contradicted by continuous-mode driving integrating the whole
  interval as one straight chord at the next read.
- **Acceptance Criteria**:
  - [ ] A host test drives a full circle under constant twist in an
        unconditional tick loop and asserts pose reads back near the
        origin (not approximately the full path length, the pre-fix
        behavior).
  - [ ] `updateMove()`'s existing (correct) odometry gating for
        move-engine polling is unchanged — no regression there.

### SUC-004: Seeding World Pose Agrees Across Both Pose Sources for Any Heading Convention
Parent: N/A (wire-only `SEED` verb; no student-facing block equivalent
— `seedPose()` is reached from `main.ts`'s World-group blocks and the
wire's `SEED` verb, not from a use case `usecases.md` documents)

- **Actor**: A bench host or AprilCam-driven reseed routine supplying a
  world-frame fix, potentially in a 0–360° heading convention, or the
  robot's own deliberately-unwrapped odometry heading echoed back.
- **Preconditions**: OTOS present and begun.
- **Main Flow**:
  1. Caller calls `seedPose(x, y, heading)` with `heading` outside
     ±180° (e.g. 350°, or 720°).
  2. `OtosPort::setPose()` wraps the heading into (−π, π] before
     quantizing into the chip's register (x/y keep their existing
     clamp — only heading, a wrap-mandatory quantity, changes).
  3. Both pose sources (OTOS register, Rig odometry) read back the
     same heading modulo 360°.
- **Postconditions**: The OTOS and encoder-odometry pose sources start
  agreed at seed time for any input heading — restoring the invariant
  `seedPose()`'s own contract comment already claims ("their later
  divergence IS the drift being measured"), which a >180° seed
  silently broke before this fix (up to ~170° of disagreement).
- **Acceptance Criteria**:
  - [ ] A host test proves the 350°/−350°/720° → correctly-wrapped
        (e.g. 350° → −10°) round trip via the new `heading_wrap.h`
        (see ticket 004) — `OtosPort` itself cannot be host-compiled
        (`otos_port.h` includes `pxt.h` unconditionally), so this is
        the only host-testable proxy for the real register write.
  - [ ] `PoseSource::heading()`'s contract comment
        (`motion_engine.h`) is updated to state the wrap convention is
        implementation-defined and consumed only via cos/sin — not a
        universal "(unwrapped)" claim that `OtosPort` (wrapped) and the
        new `EncoderPoseSource` (unwrapped) cannot both satisfy.

### SUC-005: An Implausible Encoder Jump Rebaselines Instead of Teleporting Pose
Parent: UC-009 (Read Robot Pose)

- **Actor**: Student/Teacher (indirectly — this defends pose truth
  against a hardware fault, not a student action).
- **Preconditions**: The Nezha brick's encoder counter for one wheel
  jumps implausibly (≥ 5000 counts) between two samples and the next
  sample is self-consistent with the jumped value (the existing
  two-strike glitch armor's own trigger condition — today accepted as
  a real ~4 m position change).
- **Main Flow**:
  1. `NezhaMotorPort::collect()` observes the implausible-then-
     consistent pattern and asks `EncoderGlitchArmor` (new,
     host-portable) for a decision.
  2. `EncoderGlitchArmor` returns "accept as rebaseline," not "accept
     as motion."
  3. `collect()` re-anchors its position offset (same technique the
     existing manual `rebaseline()` already uses) instead of
     integrating the jump; a DIAG counter increments so the event is
     visible.
- **Postconditions**: Position stays continuous across the event
  instead of teleporting by the full jump magnitude; velocity reflects
  real motion during the sample gap, not a multi-m/s spike. The
  real-world premise this defends against (does a brick MCU reset
  actually restart the counter near zero?) is separately confirmed or
  ruled out by this sprint's bench experiment, recorded in
  `brick-reset-odometry-teleport.md` — that confirmation does not gate
  this use case, which defends against the code-level defect
  (accepting *any* implausible-then-consistent jump as truth)
  regardless of what causes it.
- **Acceptance Criteria**:
  - [ ] A host test drives `EncoderGlitchArmor` directly (no I2C fake
        needed) with a scripted implausible-then-consistent raw-counts
        sequence and asserts a rebaseline decision, not an
        accept-as-motion decision.
  - [ ] A DIAG counter surfaces when a rebaseline fires (0 across a
        normal session).
  - [ ] The existing two-strike behavior for a *plausible* second
        reading (e.g. a genuine hand-rotation re-sync) is unchanged —
        this is a new third outcome, not a replacement of the existing
        accept-as-motion path for ordinary cases.

### SUC-006: GO_TO_W Drives on Encoder Odometry When No OTOS Is Present
Parent: N/A (wire-only `GO_TO_W` verb; `main.ts`'s own `goToWorld()`
block is a separate TS-level heuristic that never calls
`MotionEngine::goToW()` and is unaffected by this fix)

- **Actor**: A bench host issuing `GO_TO_W` to a robot with no OTOS
  fitted (tovez, gopiv, zeguz — most of the fleet).
- **Preconditions**: No OTOS connected (`otosRef().connected()` is
  false — never begun, or begun against a chip that never answered).
- **Main Flow**:
  1. Host sends `GO_TO_W <x> <y> ... #<id>`.
  2. `engineGoToW()` selects `EncoderPoseSource` (wrapping the Rig's
     existing dead-reckoned odometry) in place of the unavailable
     `OtosPort`, in the one place this selection is made.
  3. `MotionEngine::goToW()` proceeds exactly as it would with any
     other `PoseSource` — reads pose once, rotates the world delta into
     the body frame, delegates to `goToR()`.
- **Postconditions**: The move executes (dispatched, not
  `kUnimplemented`) on encoder odometry — a materially weaker
  (drifting) promise than the OTOS gives, since encoder odometry has no
  independent world-frame correction. This difference is not currently
  surfaced back through GO_TO_W's own return value; a caller must check
  STATUS's `otos=` flag beforehand to know which promise it is getting
  (see Open Question below).
- **Acceptance Criteria**:
  - [ ] A host test calls `goToW()` through `EncoderPoseSource` with no
        OTOS anywhere in the link (mirroring
        `test_motion_engine_gotow.py`'s existing `FakePoseSource`
        pattern) and asserts the move dispatches and reaches its
        target under scripted odometry.
  - [ ] A host test asserts `engineGoToW()`'s selection rule picks
        `EncoderPoseSource` when `OtosPort::connected()` is false, and
        `OtosPort` when true.
  - [ ] `wire_adapter.cpp`'s comment describing GO_TO_W's
        `kUnimplemented`-without-OTOS behavior is corrected (or removed
        if the behavior no longer exists on any path).

## GitHub Issues

(GitHub issues linked to this sprint's tickets. Format: `owner/repo#N`.)

## Definition of Ready

Before tickets can be created, all of the following must be true:

- [ ] Sprint planning document is complete (sprint.md, including its
      Architecture and Use Cases sections)
- [ ] Architecture review passed (or skipped, for changes with no
      architectural impact)
- [ ] Stakeholder has approved the sprint plan

## Tickets

| # | Title | Issue | Depends On |
|---|-------|-------|------------|
| 001 | goTo geometry: pivot-split fix, short-arc normalization, arrive tolerance | goto-geometry-pivot-split-miss.md | — |
| 002 | Cross-fiber stop delivery inside the settle window | cross-fiber-stop-settle-window-race.md | — |
| 003 | Continuous-mode odometry: fold odomUpdate() into every tick | continuous-mode-odometry-chord-error.md | — |
| 004 | OTOS heading-wrap on seed and PoseSource contract cleanup | otos-seed-heading-clamp.md | — |
| 005 | Encoder glitch-armor rebaseline-on-discontinuity (host-testable) | brick-reset-odometry-teleport.md (partial — `completes_issue: false`) | — |
| 006 | Brick-reset bench experiment handoff checklist | brick-reset-odometry-teleport.md (completes the issue) | 005 |
| 007 | Encoder PoseSource fallback for GO_TO_W | no-encoder-odometry-posesource-fallback.md | 004, 005 |

Tickets execute serially in the order listed. 001-005 have no
inter-ticket dependency and could in principle run in any relative
order among themselves, but are sequenced this way because 004/005
introduce the `PoseSource`/`heading_wrap.h`/`EncoderGlitchArmor` seam
007 depends on — doing them first avoids 007 being planned against a
seam that doesn't exist yet. 006 depends on 005 because its checklist
references the shipped fix by name. 007 depends on both 004 (the
`PoseSource` contract clarification `EncoderPoseSource` must honor —
unwrapped heading) and 005 (the rebaseline guarantee it inherits
rather than re-implements).
