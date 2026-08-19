---
status: done
sprint: '002'
tickets:
- 002-001
- 002-002
- 002-003
- 002-004
---

# Pure caller-driven tick loop (generator-style next()); unwire fiber pacer

## Description

Replace the background-fiber control model with a caller-driven tick model. Today
the drive kernel runs as a CODAL fiber: move commands post to a shared mailbox, the
fiber picks them up at a 24 ms cadence, and TS code polls for completion
(`while (_updateMove()) basic.pause(10)`). The stakeholder wants a generator/loop
model instead: start a move, then repeatedly call a `tick()` (the generator's
`next()`) that executes one control step on the **caller's** fiber and self-paces to
hold the cadence, with sensor/comms checks running in the loop body between ticks.

Stakeholder decisions (2026-08-19):

1. **Pure tick model** — the fiber pacer is unwired entirely: no dual mode, no
   block/JS way to start the fiber. The structure to restore it stays: the vendored
   kernel keeps `DifferentialDrive::start()` untouched; only the single call site in
   shims is removed, with a re-enable comment.
2. **Cadence stays 24 ms (41.7 Hz)** — meets the ≥ 40 Hz PID requirement with zero
   retuning, and avoids the 19 ms motor write-throttle hazard (`nezha_port.h:87`)
   plus two tick-count kernel constants (`kStopEnforceTicks`, `kAccelSmoothing`)
   that a 20 ms cadence would disturb.
3. Lands as **sprint 002**, after sprint 001 closes. Sprint 001's architecture froze
   `diffdrive.*` and the `main.ts` public API and ratified the fiber model
   (`sprint.md:104-105, 335-355`); this issue supersedes that decision through
   normal sprint planning.

Feasibility, verified in code:

- The vendored kernel was designed for a host-owned loop: `diffdrive.h:18-20` —
  "a host that owns its own loop never calls start() and drives step() directly
  instead." `step()` is public; the fiber is a 17-line optional pacer
  (`diffdrive.cpp:275-306`) whose absolute-deadline logic is directly liftable.
- `step()` busy time is ~10-15 ms per cycle (8 ms of it is two fixed 4 ms
  encoder-settle sleeps), leaving ~9-14 ms of loop-body headroom at 24 ms. TS↔C++
  shim calls compile to native ARM — microseconds, immaterial at 40 Hz.
- The control law computes dt from the measured wall clock, so it is
  cadence-agnostic; only the pacer knows the period (`cyclePeriod`, `shims.cpp:80`).

## Cause

Two forces motivate the change:

- **Programming model**: student loop bodies currently beat against the fiber's
  cadence (`basic.pause(24)` in `whileMoving`, `main.ts:178-202`) instead of being
  phase-locked to the control cycle; the fiber model hides when control runs.
- **Latent concurrency bug**: `Rig`'s odometry and move state (`shims.cpp:31-56`,
  `odomUpdate` at `shims.cpp:90-109`) is an unprotected read-modify-write touched
  from multiple fibers; sprint 001's protocol tickets add a third context. A single
  tick that owns odometry + move stepping + control stepping removes the class.
- **Safety hazard the design must close**: lease expiry, stall latch, and stop
  enforcement all execute *inside* `step()` (`diffdrive.cpp:454-467, 685,
  696-702`), and the Nezha brick physically latches its last commanded duty across
  MCU resets (`nezha_port.h:11-13`). With no background pacer, an abandoned tick
  loop mid-move would leave duty standing forever.

## Proposed fix

### Ownership model: tick is the only executor

- **Remove `rig->kernel.start()` at `shims.cpp:83`.** Replace with a comment:
  fiber pacer intentionally unwired — tick model owns stepping; re-enable by
  restoring this call. `diffdrive.*` untouched, so `start()`/`run()`/`fiberEntry()`
  remain available for later re-wiring. Nothing exports fiber-start to TS.
- **`tickDrive()` (new shim)** — the generator's `next()`. Records `lastTickUs`,
  runs `kernel.step()` on the caller's fiber, runs `serviceMove()`, then sleeps to
  an absolute deadline (anchored to the previous tick's deadline while ticks are
  consecutive, re-anchored after a gap — no drift; overruns counted in a Rig
  counter, since the kernel's own `cycleOverrunCount_` is only touched by the
  unused `run()`). Returns `bool` still-moving (false immediately when no move is
  active, matching the `while(...)` idiom).
- **Starvation watchdog (the only background fiber; does NO control).**
  Launched from `ensure()` via the existing `CodalFiberLauncher`. Every ~50 ms:
  if (commanded mode non-neutral OR `moveActive`) AND `now - lastTickUs` > 4
  periods (~100 ms) → `kernel.neutral()` + `moveActive = false` + immediate
  port-level zero-duty write (the `emergencyStop()` path, `nezha_port.cpp:71-76` —
  needs no `step()`, does not latch the kernel estop, so the program can simply
  resume ticking later). This makes "the robot only moves while your loop ticks"
  literally true, with a ≤~150 ms stop bound on abandonment.
- **Semantics change for continuous modes:** `setWheelSpeeds`/`driveTwist` post a
  command but the robot only moves while ticks land — the caller must run a
  `driveTick()` loop (watchdog stops the robot otherwise). Document in the blocks'
  JSDoc and README. The standard move blocks tick internally, so beginner UX is
  unchanged.
- **Concurrency guard:** `stepBusy` flag around `kernel.step()` in `tickDrive()` —
  a second fiber calling `tickDrive()` while one is mid-step (parked in the settle
  sleeps) waits on a 1 ms poll until clear. CODAL fibers are cooperative, so
  check-and-set with no intervening yield is atomic.

### API surface

- `shims.cpp`: refactor `updateMove()` body (`shims.cpp:178-210`) into private
  `static bool serviceMove(Rig&)` — odometry + progress/deadline/stall check +
  `kernel.neutral()` on done. Invariant, stated in a comment: no fiber_sleep/yield
  inside (makes the Rig read-modify-write atomic across fibers). `updateMove()` and
  `tickDrive()` both call it.
- New exports: `//% bool tickDrive()`, `//% int cycleStat(int which)` (0=period
  measured µs, 1=busy µs, 2=overruns from the Rig counter, 3=cycleCount — Output
  fields at `diffdrive.h:118-121`).
- `main.ts`: `_tickDrive`/`_cycleStat` shim declarations **with simulator bodies**
  (kinematic integrate + `basic.pause` to a 24 ms absolute schedule); new block
  `driveTick()` ("drive tick", Move group). Rewire internals, signatures unchanged:
  - `move()`/`goTo()` (`main.ts:88-104`): `while (_tickDrive());` — blocking moves
    become caller-driven.
  - `whileMoving()`/`whileGoingTo()` (`main.ts:178-202`): `while (_tickDrive()) {
    body(...) }` — body phase-locked to the control cycle (replaces `pause(24)`
    beating against the fiber).
  - `isMoving()` keeps the non-stepping `_updateMove()` check.
- `test.ts`: keep the sprint-001 square; add a loop-style square variant (button B):
  per leg `startMove(...)` then `while (diffDrive.driveTick()) { pose readout }` —
  the demonstration artifact for the generator model.

### Files

| File | Change |
|---|---|
| `diffdrive.h/.cpp`, `nezha_port.*`, `platform_ports.h` | **No change** (kernel keeps `start()` — the re-wire structure; split-phase encoder ordering untouched) |
| `shims.cpp` | remove the `kernel.start()` call (re-enable comment); `serviceMove()` extraction; starvation watchdog fiber; `tickDrive()`; `cycleStat()`; `lastTickUs`/`stepBusy`/overrun counter in `Rig` |
| `main.ts` | shim decls + simulator bodies; `driveTick` block; rewire 4 wait loops; JSDoc on continuous-mode ticking contract |
| `test.ts` | loop-style square variant |
| `README.md` | document the tick contract ("robot moves while your loop ticks") |

## Verification

- Simulator: existing square test net-zero pose; loop-form blocks compile/run.
- Hardware (micro:bit "zetuv" via mbdeploy):
  - count `driveTick()` returns over a 5 s move → ~208 at 24 ms;
  - `cycleStat(2)` overruns stay 0 through the square;
  - hostile-body test — loop body calling `basic.showNumber` mid-move: PID rate
    drops (expected in this model) but the move completes and the robot stops;
  - abandoned-loop test — start a move, never tick again: watchdog stops the
    robot within ~150 ms, program can start a new move without any estop-clear;
  - `setWheelSpeeds` without ticking → robot does not move (new contract).
- Behavioral parity: square end-pose in old (poll) vs new (tick) builds within
  existing tolerance.

## Related

- Sprint 001 (protocol v5 + square test): its architecture ratified the fiber model
  and froze the kernel and `main.ts` API — this issue supersedes that via sprint 002
  planning. Interlock with tickets 003-005: protocol-driven moves have no student
  loop, so the protocol fiber becomes the tick caller for its own moves (its
  handler ticks until done, or on its TLM cadence); the watchdog covers protocol
  abandonment identically. Cheap optional amendment for the remaining sprint-001
  work: write protocol handlers against `serviceMove()`/`tickDrive()` from day one
  so sprint 002 doesn't refactor their call sites.
- Bench characterization constraint (radio-robot-elite
  `docs/design/encoder-refresh-characterization.md`): never interleave a duty write
  between an encoder select and its read — the kernel's split-phase ordering must
  be preserved by any tick restructuring.
