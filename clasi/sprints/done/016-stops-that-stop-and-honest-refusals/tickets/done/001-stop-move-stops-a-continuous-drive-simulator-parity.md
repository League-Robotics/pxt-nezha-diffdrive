---
id: '001'
title: stop move stops a continuous drive; simulator parity
status: done
use-cases:
- SUC-001
depends-on: []
github-issue: ''
issue: stop-move-does-not-stop-continuous-drive.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# stop move stops a continuous drive; simulator parity

## Description

**Stakeholder decision (already made — see the sprint's `stakeholder_approval`
gate, recorded 2026-08-26): the contract is "STOP", not "end the move".**
Do not re-open this choice. Add `kernel.neutral()` to `shims.cpp`'s
`endMove()` free function; leave `blocks/sim.ts`'s `_endMove()` exactly as
it is today (it already performs a full stop, which is now the *correct*
simulator behavior, not a divergence to fix).

`stop move` (`stopMove()` block → `_endMove()` shim → `shims.cpp`'s
`endMove()` free function, line ~699) currently reads:

```cpp
void endMove() {
  if (rig == nullptr) return;
  rig->engine.endMove();
  deliverStopNow(*rig);
}
```

`MotionEngine::endMove()` (`motion_engine.cpp:93-96`) only stages
`kernel_.neutral()` when a move-engine move (`startMove`/`startGoTo`) was
active. After a continuous-drive command (`setWheelSpeeds`/`driveTwist`,
which call `wheelsV()` → `cancelMove()` on the way in) no move-engine move
is active, so nothing is staged; `deliverStopNow()`'s port-level zero
write is momentary and the kernel's held commanded velocity (up to
`kLeaseMax`, one hour) re-commands on the very next `step()`. Measured
(`docs/code-review/2026-08-26/raw/stop_probe.cpp`, scenario A): duty is
back at 23.5% one tick later and *climbing* to 24.3% ten ticks later — the
PID makes up the ground the momentary zero cost it.

`stopAll()` (the `stop` block, same file, a few lines below `endMove()`)
already has the correct three-line shape:

```cpp
void stopAll() {
  Rig& r = ensure();
  r.engine.endMove();
  r.kernel.neutral();      // <-- the line endMove() is missing
  deliverStopNow(r);
}
```

The fix is to give the `endMove()` free function the same shape:
`rig->engine.endMove(); rig->kernel.neutral(); deliverStopNow(*rig);` —
one added line, in the same file, using the same `ensure()`/`rig`
composition `stopAll()` already uses (note `endMove()` currently guards on
`rig == nullptr` and returns rather than calling `ensure()`; preserve
that early-return shape, just add the `kernel.neutral()` call on the
non-null path).

`src/core/diffdrive.{h,cpp}` is vendored and byte-stable — this ticket
touches only `shims.cpp` composition, never the kernel itself.

### Documentation to update (part of this ticket, not follow-on work)

- `src/blocks/motion.ts`'s `stopMove()` doc comment (~line 224-235):
  currently says "End the current move now (no-op if none)... this just
  clears the move-engine state" — written for the old, incomplete
  behavior. Update it to state plainly that `stop move` stops the robot
  now, including a continuous drive command in progress, matching the
  `stop` block's own contract and the simulator's existing behavior.
- `docs/design/specification.md` S4.4's table row for `stop move` (line
  157): currently `"Ends the current move now; no-op if none is active
  (\`_endMove\`)."` — update to state the same full-stop contract (still
  fine to say "no-op" in the sense of "nothing to stop if the robot was
  already idle," but the row must no longer read as if a continuous drive
  survives it).
- Leave `src/blocks/sim.ts`'s `_endMove()` (line ~208-212) **unmodified**
  — it already zeros `simVel`/`simYawRate` unconditionally, which is now
  the correct, matching behavior.

## Acceptance Criteria

- [x] `shims.cpp`'s `endMove()` free function calls `rig->kernel.neutral()`
      (staged) in addition to `rig->engine.endMove()` and
      `deliverStopNow(*rig)` — the same three-call shape `stopAll()` uses.
- [x] `src/core/diffdrive.h`/`diffdrive.cpp` are byte-unchanged (`git diff`
      shows no changes to either file).
- [x] `src/blocks/sim.ts`'s `_endMove()` is byte-unchanged.
- [x] `src/blocks/motion.ts`'s `stopMove()` doc comment states the full-stop
      contract (matches `stop`'s doc comment in spirit: stops the robot
      now, not just "ends the move-engine's own bookkeeping").
- [x] `docs/design/specification.md` S4.4's `stop move` row states the same
      contract.
- [x] A new host test (see Testing below) proves the *mechanism* the fix
      adds — `kernel.neutral()` staged after a continuous drive zeros duty
      within one tick and it does not climb back up on subsequent ticks —
      and this test fails if the `kernel.neutral()` call is the one the
      old `endMove()` was missing (i.e., the test mirrors the exact
      pre-fix vs. post-fix call sequence, not just the kernel's own
      already-proven `neutral()` primitive in isolation).
- [x] Sprint Success Criteria item 1 (`stop_probe.cpp`, re-run unmodified,
      shows 0.0% duty one tick after `stop move` following a continuous
      command) and item 2 (simulator and hardware agree, stated in one
      place) are satisfied by this ticket's changes — `stop_probe.cpp`
      itself is a throwaway manual probe (not wired into `pytest`); re-run
      it by hand (`c++ ... docs/code-review/2026-08-26/raw/stop_probe.cpp
      ...` — see its own `#include`s for the exact build line, mirroring
      `tests/host/motion_engine_shim.cpp`'s compile recipe) as a final
      manual confirmation, in addition to (not instead of) the new
      automated host test below.

## Implementation Plan

### Approach

1. Edit `shims.cpp`'s `endMove()` free function: add
   `rig->kernel.neutral();` between the existing `rig->engine.endMove();`
   and `deliverStopNow(*rig);` calls. Update the function's own comment
   to say it now delivers a real stop (staged `neutral()` + immediate
   port-level zero), not just move-engine bookkeeping + a momentary
   port-level zero.
2. Update `src/blocks/motion.ts`'s `stopMove()` doc comment and
   `docs/design/specification.md` S4.4's `stop move` row as described
   above.
3. Do **not** touch `src/blocks/sim.ts`, `src/core/diffdrive.h`, or
   `src/core/diffdrive.cpp`.
4. Add the host test described below.

### Files to modify

- `src/shims.cpp` — `endMove()` free function (~line 699) and its comment.
- `src/blocks/motion.ts` — `stopMove()` doc comment (~line 224-235).
- `docs/design/specification.md` — S4.4 table, `stop move` row (~line 157).

### Files explicitly NOT to modify

- `src/blocks/sim.ts` (already correct).
- `src/core/diffdrive.h`, `src/core/diffdrive.cpp` (vendored, byte-stable).

### Testing plan

`shims.cpp` includes `pxt.h` and cannot be host-compiled at all (see
`tests/host/README.md`'s "What this does NOT cover yet" and
`test_cross_fiber_stop_settle_window.py`'s own "WHAT THIS FILE CANNOT
PROVE" section for this project's standing convention on that boundary)
— so no `pytest` test can call the real `endMove()` free function
directly. Follow the same precedent
`docs/code-review/2026-08-26/raw/stop_probe.cpp` and
`tests/host/motion_engine_shim.cpp` already establish: build the
scenario from the same host-portable primitives shims.cpp composes
(`DiffDrive::DifferentialDrive` kernel + `diffDrive::MotionEngine` +
`FakeMotor`/`FakeClock` from `fake_ports.h`), driven through a small
new or extended `extern "C"` shim function that mirrors the exact
`endMove()` call sequence (`engine.endMove()`, then `kernel.neutral()`,
then a port-level `emergencyStop()` on both motors matching
`deliverStopNow()`'s primitive). Extend `tests/host/motion_engine_shim.cpp`
per its own header comment ("Extend this file's function list -- don't
invent a second shim") rather than adding a new shim file, unless the
new function set is large enough to warrant its own file (follow
existing precedent either way).

- **New test** (e.g. `tests/host/test_stop_move_zeros_continuous_drive.py`):
  mirror `stop_probe.cpp`'s scenario A — drive continuously
  (`wheelsV`/equivalent) to a nonzero measured duty (same
  `_drive_to_nonzero_duty`-style setup `test_cross_fiber_stop_settle_
  window.py` already uses), then invoke the shim function mirroring the
  FIXED `endMove()` sequence, then assert applied duty is 0.0% one tick
  later and stays 0.0% ten ticks later (not climbing). Also assert that
  invoking a shim function mirroring the OLD (pre-fix) sequence —
  `engine.endMove()` + port-level zero, no `kernel.neutral()` — leaves
  duty nonzero/climbing, as a documented regression pin (this half is
  optional but strongly preferred: it is what makes the test fail
  against a reversion of this exact fix, not just against an unrelated
  regression). This test necessarily encodes the shims.cpp call sequence
  in the test's own shim rather than calling shims.cpp directly (the same
  boundary `test_cross_fiber_stop_settle_window.py` documents) — keep
  the shim mirror and the real `shims.cpp::endMove()` in sync by hand;
  note this explicitly in the new test file's header comment, the same
  way `test_cross_fiber_stop_settle_window.py`'s own header comment does.
- **Existing tests to run**: `uv run pytest tests/host/test_motion_engine_*.py
  tests/host/test_cross_fiber_stop_settle_window.py
  tests/host/test_regression_post_move_neutral.py` — scoped to the
  motion/stop-delivery neighborhood this ticket touches (per
  `.claude/rules/source-code.md`, full-suite run is `close_sprint`'s own
  gate, not a per-ticket step).
- **Verification command**: `uv run pytest tests/host/test_stop_move_zeros_continuous_drive.py`
  plus the scoped run above.
- **Manual/bench confirmation** (documentation, not a `pytest` gate): re-run
  `stop_probe.cpp` unmodified after the fix and confirm scenario A now
  reads 0.0% duty one tick after `stop move`, matching what `stop`
  already showed. Hardware/bench re-confirmation beyond the host-portable
  probe is not required for this ticket to close — the sprint's build
  checkpoint (ticket 007) is the standing per-sprint convention for that.

### Documentation updates

- `src/blocks/motion.ts` doc comment (part of Acceptance Criteria above).
- `docs/design/specification.md` S4.4 (part of Acceptance Criteria above).
- `src/DESIGN.md` is **not** touched by this ticket — the stop taxonomy
  table (which entry point delivers which of the five mechanisms) is
  ticket 006's deliverable, written after all of 001/002/003/005 land so
  it reflects the sprint's final state.
