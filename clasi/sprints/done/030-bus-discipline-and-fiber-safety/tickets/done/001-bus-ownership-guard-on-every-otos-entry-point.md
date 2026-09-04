---
id: '001'
title: Bus-ownership guard on every OTOS entry point
status: done
use-cases:
- SUC-001
depends-on: []
github-issue: ''
issue: code-review/enforce-the-one-fiber-i2c-invariant.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Bus-ownership guard on every OTOS entry point

## Description

`tickDrive()` serializes `kernel.step()` behind `Rig::stepBusy` (a bare
`bool`, `src/shims.cpp:138,663-666,752`) and waits if another fiber
holds it. Nothing else that touches the shared I2C bus does. Four
independent holes let an OTOS transaction land inside the Nezha
encoder's select→read settle window, destroying that encoder sample
(the documented Phase-F signature, `nezha_port.cpp:376-380`):

1. Every OTOS shim entry point — `otosBegin()`, `otosRead()`,
   `otosZero()`, `otosCalibrate()`, `otosSetOffset()`, `seedPose()`
   (`src/shims.cpp:1551-1677`) — issues I2C with no relationship to
   `stepBusy` at all.
2. `SET rebase` (`setKernelValue()` case 32, `shims.cpp:1242-1251`)
   calls `otosRef().setPose(0,0,0)` synchronously on the protocol
   fiber, with no gate against a student's `setWheelSpeeds()` +
   `driveTick()` loop possibly being inside its settle window on the
   main fiber.
3. `test/test.ts:831-836` runs `diffDrive.readWorld()` at 10 Hz inside
   `control.inBackground(...)` — a free-running fiber with, per its own
   comment, "NO mutual exclusion" against the bus.
4. `blocks/motion.ts`'s `startDrive()` (lines 181-189) forks a
   background `control.inBackground` ticker; `blocks/world.ts`'s
   `readWorld()`/`seedPose()`/`calibrateWorldSensor()` (lines 44-104)
   are reachable from any fiber including that background one, with no
   per-function documentation that they are live bus transactions (only
   the file-level comment at `world.ts:9-12` says so).

Confirmed still live against current (post-sprint-029) source — none of
these six call sites take any guard today; sprint 029 touched the
kernel and shaping fields only.

## Remedy

- Add `core/bus_guard.h` — a small, host-portable class (`<cstdint>`
  only, no `pxt.h`, alongside `encoder_glitch_armor.h`/`heading_wrap.h`
  in `src/core/`) named `BusGuard` with:
  - `void acquire(DiffDrive::Sleeper& sleeper)` — spins `while (busy_)
    sleeper.sleepMillis(1);` then sets `busy_ = true`. Byte-identical
    logic to `tickDrive()`'s existing inline loop
    (`shims.cpp:663-666`), extracted so it is host-testable.
  - `void release()` — sets `busy_ = false`.
  - No RAII wrapper is required (the codebase's own style is
    manual acquire/release pairs, matching the original `stepBusy`
    flow) but a scope-guard helper is acceptable if it reads more
    clearly at each call site — implementer's judgment, document the
    choice.
- In `shims.cpp`: replace `Rig::stepBusy` (a `bool`) with `Rig::busGuard`
  (a `BusGuard`). Update `tickDrive()` to call
  `r.busGuard.acquire(r.sleeper)` / `r.busGuard.release()` instead of
  the inline `while`/flag toggle it has today (behavior unchanged).
- Add `r.busGuard.acquire(r.sleeper)` / `r.busGuard.release()` around
  the I2C body of each of the six OTOS entry points listed above
  (`otosBegin`, `otosRead`, `otosZero`, `otosCalibrate`,
  `otosSetOffset`, `seedPose`) — three lines per entry, per the issue's
  own estimate.
- `SET rebase`'s OTOS write (`setKernelValue()` case 32): replace the
  synchronous `otosRef().setPose(0.0f, 0.0f, 0.0f)` call with a
  `pendingOtosZero` flag on `Rig`, consumed inside `tickDrive()` after
  `busGuard.release()` — the same deferred-request shape
  `kernel.rebasePosition()` already uses (see `diffdrive.h`'s own
  deferred-request convention). `k.rebasePosition()`/`r.x/y/heading`
  reset stay synchronous as today; only the OTOS write becomes deferred.
- `test/test.ts`: delete the `control.inBackground` sampler
  (lines 831-836). Move the `readWorld()` call into whichever tick loop
  is already running (the job's own `while (driveTick())` loop for a
  tour; sampled every k-th tick per the existing comment's own 10 Hz
  vs. 50 ms-tick reasoning) so it always runs on the fiber that already
  holds `BusGuard` for that tick.
- `blocks/motion.ts`'s `startDrive()`: add a periodic `readWorld()` call
  inside its own `control.inBackground(() => { while (_tickDrive());
  })` loop (e.g. every Nth iteration), so the one background fiber this
  block creates owns both the tick and the OTOS sample — no other fiber
  needs to call `readWorld()` while this loop is live. Document this in
  `startDrive()`'s own JSDoc.
- `blocks/world.ts`: add a one-line note to `readWorld()`'s,
  `seedPose()`'s, and `calibrateWorldSensor()`'s own JSDoc comments (not
  just the file header) that each is a live I2C bus transaction and
  must not be called concurrently with driving — the file-level comment
  already says this; the per-function ones should too, since that is
  what a student reading a single block's docs actually sees.

## Acceptance Criteria

- [x] `core/bus_guard.h` exists, host-portable (compiles under the
      `-std=c++20` host build and the `-std=c++11` syntax gate), no
      `pxt.h` include.
- [x] A host test (`tests/host/test_bus_guard.py` or similar) scripts
      `FakeSleeper::onSleep` to fire while `BusGuard::acquire()` is
      mid-spin and confirms the caller does not proceed until
      `release()` is called from the scripted callback.
- [x] A source-pin test asserts: every `uBit.i2c` caller in
      `platform/otos_port.cpp`, and every one of `shims.cpp`'s six OTOS
      entry points (`otosBegin/Read/Zero/Calibrate/SetOffset`,
      `seedPose`), acquires/releases `BusGuard` (grep-based, matching
      the style of existing source-pin tests in `tests/tools/` or
      `tests/host/`). REOPENED: `tests/host/test_bus_guard_source_pin.py`
      also discovered a SEVENTH live hole this ticket's own six-entry
      list did not name -- `otosGet()`'s case 8
      (`imuCalibrationSamplesRemaining()`) -- initially shipped as a
      pinned known-gap test rather than fixed, which the team-lead
      judged the wrong resolution against the sprint's own Success
      Criteria ("every OTOS I2C caller reaches the bus through the
      guard"). Closed in the reopened dispatch: case 8 now brackets its
      I2C call in `busGuard.acquire()`/`release()` exactly like the six
      named entry points (`src/shims.cpp` `otosGet()` case 8), and
      `test_otosget_case_8_acquires_and_releases_bus_guard` replaces the
      earlier known-gap pin with a positive assertion. Re-audited every
      other `otosGet()` case (0-7, plus `engineGoToW()`/
      `engineGoToWChord()`'s `otos.connected()`/`pose.x()`/`pose.y()`
      reads): all read cached fields set by the last `read()`/`begin()`
      call, no further I2C -- no other hole found. `resetTracking()`
      remains correctly pinned as unguarded-but-unreachable dead code
      (no call site in `shims.cpp`), per the team-lead's explicit
      instruction to leave that judgment as-is.
- [x] `test/test.ts` has no `control.inBackground` block that calls
      `readWorld()`/`otosRead()`.
- [x] `SET rebase`'s OTOS zero is deferred to `tickDrive()`, not
      synchronous on the protocol fiber — confirmed by reading the
      diff (not host-testable directly, `otos_port.h` includes
      `pxt.h`).
- [x] `blocks/world.ts`'s `readWorld()`, `seedPose()`, and
      `calibrateWorldSensor()` JSDoc comments each state they are live
      bus transactions.
- [x] Existing host suite (`tests/host/`) and the C++11 syntax gate
      (`tests/host/test_cxx11_syntax_gate.py`) pass unchanged. One
      pre-existing test (`tests/host/test_wire_motion_verbs.py::
      test_rebase_shims_cpp_zeroes_encoder_frame_and_reseeds_otos`)
      pinned the OLD synchronous `otosRef().setPose(0,0,0)` call this
      ticket deliberately replaces with the deferred
      `pendingOtosZero` flag -- updated to pin the new behavior
      instead of the old one, since the change is this ticket's own
      Remedy, not a regression.
- [ ] Hardware (team-lead session, deferred to sprint close or a
      dedicated bench session): a wire-issued OTOS read scripted to
      land during a live drive no longer corrupts the encoder sample
      (`i2cf` does not climb) where the pre-fix build reproduces it —
      MEASURED citation required per
      `.claude/rules/measurement-citations.md`. UNVERIFIED in this
      dispatch: no hardware/board access. Left for the team-lead
      session per the ticket's own note.

## Testing

- **Existing tests to run**: `tests/host/` full suite (scoped to the
  files this ticket touches during implementation, per
  `.claude/rules/source-code.md`); `tests/host/test_cxx11_syntax_gate.py`;
  the existing `test_encoder_glitch_armor.py` and
  `test_vfp_guard_source_pin.py` as regression checks (this ticket does
  not touch either, but both share `shims.cpp`/`core/` proximity).
- **New tests to write**: a `BusGuard` host test scripting
  `FakeSleeper::onSleep`-driven contention (per Acceptance Criteria
  above); a source-pin test over `otos_port.cpp` and `shims.cpp`'s OTOS
  entry points.
- **Verification command**: `uv run pytest tests/host/ -k "bus_guard or
  source_pin or cxx11"` during implementation; full `uv run pytest` at
  `close_sprint`.
