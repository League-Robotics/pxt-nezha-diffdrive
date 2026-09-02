---
id: '003'
title: Single executor on the protocol fiber
status: exception
use-cases:
- SUC-003
depends-on:
- '001'
- '002'
github-issue: ''
issue: fiber-safety-and-command-dispatch.md
completes_issue: true
exception:
  thrown_by: programmer
  thrown_at: '2026-09-02T17:47:59.639343+00:00'
  attempted: 'Tickets 001 and 002 landed and are what this sprint set out to deliver.
    001 (VFP yield guard) is hardware-confirmed on gopiv -- 0/25 resets on the RUN:
    kill test and 0/4 under the harder telemetry-plus-interleaved-MOVE_X stress, against
    a 3/3 failure baseline the same morning -- and it also cured the documented radio-during-motion
    wedge, verified on vevov over the relay. 002 (real RUN queue) is complete with
    7 host tests and a clean firmware build. Beyond the plan, the sprint also fixed
    the yaw axis''s missing kinematic braking gate (pivot scatter sd 1.14 -> 0.18)
    and added profile-completion move termination, which took square-tour closure
    from 52.3 to 3.9 mm and diamond from 28.6 to 2.2 mm on vevov.'
  conflict: 'Ticket 003 restructures who owns the control tick: split Protocol::run()
    into serviceOnce() plus a loop, dispatch RUN jobs on the protocol fiber via runAction0(),
    add a service hook inside tickDrive(), remove the MessageBus event from the RUN
    path, add motion-ownership arbitration, and raise the fiber stack. Its own estimate
    is 2-3 bench sessions and it is explicitly NOT host-testable -- tests/host cannot
    compile shims.cpp or protocol.cpp at all, so every acceptance criterion needs
    hardware. Two things make finishing it in this sprint the wrong call. First, the
    crash that motivated it is already fixed by 001, so the remaining value is architectural
    (the 4-slot ring''s silent overwrite is separately fixed by 002; what is left
    is the link-hang-under-telemetry issue and making the I2C invariant structural)
    rather than urgent. Second, the only field robot is currently unreachable: magni''s
    USB port has been dropping the board all session (usb 1-1.5 disconnect, and earlier
    device descriptor read/64 error -110), and vevov disconnected mid-flash, so it
    likely needs a reseat and a reflash before any hardware work can proceed. Rushing
    an architecture change that can only be validated on hardware, with no working
    hardware, is how the retracted radio-wedge bisect happened. Recommend carrying
    003 into its own sprint once a robot is reliably reachable.'
  surface: user-visible
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Single executor on the protocol fiber

## Description

**Do not start this ticket until ticket 001's hardware acceptance has
actually passed on gopiv** (0/10 `RUN:straight:20`, 0/10
`RUN:pivot:90`, 0/5 `RUN:square:20`, baseline 3/3 resets confirmed on
unfixed firmware first). This ticket restructures the very fiber the
VFP guard protects; starting it against an unconfirmed guard makes any
failure here ambiguous between "the guard doesn't work" and "this
restructuring is wrong." This is a hard sequencing dependency, not a
convenience ordering — see `clasi/issues/fiber-safety-and-command-dispatch.md`'s
"Proposed fix," which states step 1 must land and be hardware-confirmed
before step 3 begins.

Three execution models coexist today: wire motion ticks on the
protocol fiber (`protocol.cpp`'s `if
(wireAdapter_.hasLiveMotionObligation()) tickDrive();`), `RUN:` motion
ticks on a MessageBus-forked fiber (`src/blocks/run.ts`'s
`control.onEvent(RUN_EVENT_SOURCE, ...)` handler, running a `while
(driveTick())` loop on its own fiber), and student blocks tick on the
calling fiber. Only the third is deliberate. The second is also where
the FPU hazard actually fires (two fibers doing float work
concurrently) and, not coincidentally, the second fiber's concurrency
is also *why* `RUN:abort` works today — "by accident," per the issue:
MessageBus forks a second fiber, so an abort sent while a tour runs
executes concurrently with it.

**Invert the pump, do not make the executor drive the tour.** An
earlier design proposed arming the motion obligation from TypeScript so
the protocol fiber ticks TS-issued moves — this is explicitly
superseded (see the issue's "Superseded" section): `tourWorld()` reads
the OTOS on the handler's own fiber between moves, and moving the tick
elsewhere would put those reads inside the encoder select-to-read
window `src/DESIGN.md`'s bus-discipline invariant forbids — trading an
FPU hazard for an I2C hazard. Likewise, do not turn the tour into a
state machine the executor steps — that destroys the explicit
`startMove()` + `driveTick()` shape `test/test.ts` calls deliberately.
Instead: the tour keeps its own tick loop; that loop's *iterations* run
on the executor's fiber via a service hook.

## Acceptance Criteria

- [ ] Ticket 001's hardware acceptance is confirmed passing before any
      code in this ticket is written against hardware — record the
      confirmation (date, board, result) in this ticket's own notes
      before starting.
- [ ] `Protocol::run()` is split into `serviceOnce()` — one
      non-blocking pass: serial read, radio read, telemetry if due —
      and a loop that calls it, dispatches a queued job (via ticket
      002's `run_queue.h`) if one is pending and none is running, then
      ticks or sleeps.
- [ ] `dispatchJob()` invokes the TS dispatcher via `runAction0()` on
      the protocol fiber (mechanically supported: `runAction3` pushes a
      per-fiber `ThreadContext` and `gcProcessStacks` already walks
      it — confirm this against the actual PXT runtime version in this
      tree before relying on it).
- [ ] `tickDrive()` gains one service hook, fired **after
      `r.stepBusy = false` (`shims.cpp:670` at time of writing — confirm
      the current line) and before the pacing sleep** — never inside
      `stepBusy`, because `step()` already yields twice inside the
      encoder select-to-read window. The hook is a function pointer on
      the `Rig`, not new CODAL surface added directly to `shims.cpp`,
      and is host-testable via the existing `FakeSleeper::onSleep`
      injection (`tests/host/kernel_shim.cpp`).
- [ ] `control.onEvent(RUN_EVENT_SOURCE, ...)` (`src/blocks/run.ts`) is
      replaced with a `_registerRunDispatch(cb)` shim; `onRun()`/
      `onRunCommand()` keep their existing public shape (no change to
      the student-facing block API). The `0x2001` event leaves the RUN
      path entirely.
- [ ] **`RUN:abort` and `RUN:clearestop` bypass the queue.** Under one
      executor, a queued abort would sit behind the very job it is
      meant to stop — these two must take effect immediately regardless
      of what else is queued or running.
- [ ] `motionOwner_ ∈ {none, wire, job}` is added to `Protocol` (**not**
      `WireAdapter` — a wire `MOVE_X` mid-tour today overwrites the
      tour's move with no error to either side; keeping this out of
      `WireAdapter` is what lets the existing wire-verb host tests,
      which construct `WireAdapter` standalone, stay valid unmodified).
      A wire motion request arriving while `motionOwner_ == job` is
      arbitrated (rejected with a clear error, or queued behind the
      job's completion — pick one and document why in this ticket's
      notes) rather than silently overwriting the running job's move.
- [ ] `device_stack_size` is raised to 4096 via `pxt.json`'s yotta
      `config` seam (the default is 2048).
- [ ] `hasLiveMotionObligation()` stays **wire-only** — do not extend it
      to RUN jobs. A RUN job needs no obligation tracking of its own,
      since its own tick loop is what's running (inverted onto the
      executor fiber per this ticket); extending the concept would make
      a wire motion incorrectly report `kStop` where `kTimeout` is
      correct.
- [ ] `test_run_abort_source_pin.py` is rewritten — the pin moves from
      "an abort handler exists" to "abort bypasses the queue." Do not
      leave the old pin in place alongside the new behavior.
- [ ] `test_wire_constants_drift.py`'s `RUN_EVENT_SOURCE`/`0x2001`
      literal-pair pin is **deleted**, not left failing or vacuously
      passing — it becomes meaningless once the event leaves the RUN
      path.
- [ ] A RUN handler may block only through `driveTick()`. Note in this
      ticket's implementation (and, if practical, as a lint/test check)
      that `basic.showNumber` scrolls ~1 s per digit and would make the
      executor deaf while it runs — student-facing test code should use
      `showIcon`/`plot`/`emitLine` instead. This is a documentation/
      awareness item, not necessarily an enforced gate.
- [ ] Any wait loop this ticket adds or touches polls `moving()`
      (`shims.cpp:788` at time of writing), **never**
      `isMoving()`/`_updateMove()`, which runs `serviceMove()`'s float
      math on the waiting fiber — reintroducing exactly the class of
      hazard ticket 001 fixes.
- [ ] Firmware build succeeds with `--robot gopiv` explicitly.
- [ ] `tests/system/run_tour.py` (the host-driven `.tour` suite) passes
      unchanged.
- [ ] `uv run pytest` (full host suite) passes.
- [ ] Hardware confirmation on gopiv: a full RUN-driven tour (or the
      individual `RUN:straight`/`RUN:pivot`/`RUN:square` set) completes
      with the new single-executor dispatch, `RUN:abort` sent mid-tour
      stops it immediately, and a wire `MOVE_X` sent mid-tour is
      arbitrated per this ticket's chosen policy rather than silently
      overwriting the tour's move.
- [ ] No new comment names a sprint, a ticket, an `R-NN` code, or any
      `.md` filename — the archaeology marker budget is at 388/388 with
      zero slack (`test_archaeology_marker_budget.py`).

## Implementation Plan

**Approach**: Work in the dependency order the issue lays out — split
`serviceOnce()` out of `Protocol::run()` first (a pure refactor,
provable against existing wire-verb tests before anything else
changes), then add the `run_queue.h`-backed dispatch loop and
`dispatchJob()`, then the `tickDrive()` service hook, then
`motionOwner_` arbitration, then the `RUN:abort`/`RUN:clearestop`
bypass, then the `run.ts` dispatcher rewiring last (it is the part most
visible to students and the easiest to verify once everything
underneath it is stable). Confirm ticket 001's hardware acceptance
before starting; confirm ticket 002's queue is in place and passing
before wiring `dispatchJob()` against it.

**Files to modify**: `src/comms/protocol.h`/`protocol.cpp`
(`serviceOnce()`, `dispatchJob()`, `motionOwner_`), `src/shims.cpp`
(`tickDrive()`'s service hook on `Rig`, kept as a function pointer —
no new CODAL type surface), `src/comms/wire_adapter.h`/`.cpp` (confirm
`hasLiveMotionObligation()` is untouched in its wire-only contract),
`src/blocks/run.ts` (`_registerRunDispatch(cb)`, replacing
`control.onEvent`), `pxt.json` (yotta `config.device_stack_size`),
`tests/host/test_run_abort_source_pin.py` (rewrite),
`tests/host/test_wire_constants_drift.py` (delete the
`RUN_EVENT_SOURCE` pin), `tests/host/kernel_shim.cpp` (if the service
hook needs a new host test seam beyond the existing
`FakeSleeper::onSleep`).

**Files NOT to modify**: `src/core/diffdrive.{h,cpp}` (vendored),
`src/motion/motion_engine.*` (no shaping change in this ticket).

## Testing

- **Existing tests to run**: the full wire-verb host test suite
  (confirm it stays valid with `motionOwner_` added, since the design
  decision here specifically preserves those tests by keeping the field
  out of `WireAdapter`), `tests/system/run_tour.py`, the full
  `uv run pytest`.
- **New tests to write**: a host test for the rewritten
  `test_run_abort_source_pin.py` pin ("abort bypasses the queue"); a
  host test (using `FakeSleeper::onSleep` or an equivalent hook
  injection) proving the `tickDrive()` service hook fires after
  `stepBusy = false` and not before; a test or documented manual
  confirmation of `motionOwner_` arbitration behavior for a wire
  request arriving mid-job.
- **Verification command**:
  `uv run pytest tests/host/test_run_abort_source_pin.py tests/system/run_tour.py`
  plus the full suite, `uv run pytest`, plus a `--robot gopiv` firmware
  build and the gopiv hardware confirmation described above.
