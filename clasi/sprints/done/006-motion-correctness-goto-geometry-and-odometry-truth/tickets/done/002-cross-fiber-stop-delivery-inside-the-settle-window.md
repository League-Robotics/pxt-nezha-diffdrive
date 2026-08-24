---
id: '002'
title: Cross-fiber stop delivery inside the settle window
status: done
use-cases:
- SUC-002
depends-on: []
github-issue: ''
issue: cross-fiber-stop-settle-window-race.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Cross-fiber stop delivery inside the settle window

## Description

`stopMove()`/`stop()` (block API) — and the `isMoving()`/`move progress`
poller ending a move at its deadline — can land inside
`kernel.step()`'s ~8 ms settle window (`diffdrive.cpp`: `neutral()` at
:364-368 only stages `command_`; the duty write at :493 happens
*before* the two settle sleeps at :496/:500). If a *different* fiber
than the one currently inside `step()` calls `stopAll()`/`endMove()`,
or `updateMove()`'s own `serviceMove()` call decides the move is done,
during that settle window, the staged `neutral()` is not delivered to
the motors until another `step()` runs — and if the very call that
staged it is what ended the caller's `while (tickDrive())` loop (the
common case), no further `step()` runs until the ~100–150 ms
starvation watchdog fires. This reintroduces the measured +9–13°/turn
overshoot the settle logic exists to eliminate (code review R-08,
BLK-01, CONFIRMED, timing independently re-derived — window arithmetic
puts this at roughly a third of calls).

**Fix, at the module level** (see `design/DESIGN.md` §9 for the full
write-up): `stopAll()`, `endMove()` (the `shims.cpp` free function
bound to `stop move`), and `updateMove()`'s own move-completion branch
each additionally push an immediate, port-level zero write to both
motors — reusing the exact primitive the starvation watchdog already
uses (`Motor::emergencyStop()`, proven tick-independent by its
exact-zero short-circuit in `writeShapedDuty()`) — alongside the
pre-existing staged `kernel.neutral()`. This delivers the stop within
the same tick regardless of where in `step()`'s settle window the race
lands, adds **no new fiber/ticker** (the one-ticker-per-move invariant
is unaffected — this is a synchronous call on whichever fiber is
already running), and does **not** touch the vendored kernel
(`diffdrive.{h,cpp}` stay byte-unchanged — no cross-repo resync with
the radio-robot firmware). It also never touches `kernel.estop()`/
`estopLatch_`, staying in the same resumable "soft stop" family the
watchdog already established (UC-011's distinction between `stop` and
`emergency stop` is preserved).

**Known, accepted, pre-existing risk (not introduced by this ticket):**
the new port write shares the Nezha brick's I2C bus with the encoder
settle window; landing there is exactly the kind of "other I2C traffic
during the settle window" `diffdrive.h`'s own kernel invariant warns
can corrupt a sample. This exposure already exists today in the
starvation watchdog's own port writes (same primitive, no fiber
coordination) — this ticket increases how *often* the window can be
hit, not the consequence: `refreshSample()`'s existing fault path
already treats a corrupted collect as a held sample plus an
`i2cFaultCount_` increment, and the robot is stopping in that same
tick regardless. See `design/DESIGN.md`'s Migration Concerns for the
full analysis. Add the test called out below rather than trying to
eliminate the window (that would mean serializing all port writes
through the tick fiber — out of scope for this ticket).

**C++11 gate coverage:** this fix lives entirely in `shims.cpp`, which
includes `pxt.h` and is **not** covered by
`tests/host/test_cxx11_syntax_gate.py`. A green host suite proves the
logic is correct; it does **not** prove this ticket's code compiles
for either real embedded target. Do not report "host tests pass" as
target-build evidence for this ticket's changes.

## Acceptance Criteria

- [x] A host test scripts a stop call (via `stopAll`'s or `endMove`'s
      C++ entry point, or the `updateMove()` completion path) landing
      inside the settle window, using the existing
      `FakeMotor`/`FakeSleeper`/`FakeClock` harness pattern to control
      when the "other fiber" call happens relative to `step()`'s
      sleeps, and asserts the motor's commanded duty reads zero within
      that same tick — not after an additional watchdog-scale delay.
      Verified by test: `tests/host/test_cross_fiber_stop_settle_window.py::
      test_cross_fiber_stop_during_settle_window_zeros_duty_within_the_same_tick`
      (parametrized over both of `step()`'s two settle sleeps), exercising
      the kernel-level primitive (`Motor::emergencyStop()`, via a new
      `FakeSleeper.onSleep` hook) `deliverStopNow()` is built on — not
      `shims.cpp` itself, which is not host-linkable (see report).
- [x] No new fiber or ticker is introduced; `tickDrive()`'s existing
      settle-loop (the 12-iteration post-move loop) is left
      structurally unchanged — this ticket's fix is placed in
      `stopAll()`/`endMove()`/`updateMove()`, not inside that loop, so
      it does not collide with `settle-tick-loop-is-not-host-testable`
      (sprint 008)'s planned extraction of that loop's logic.
      Verified by code review of the diff (not host-testable): `tickDrive()`
      in `src/shims.cpp` is byte-for-byte unchanged; the fix is a single
      `static void deliverStopNow(Rig&)` helper called synchronously from
      `stopAll()`/`endMove()`/`updateMove()` only.
- [x] The fix does not set `estopLatch_` — a fresh `tickDrive()` call
      after the stop resumes motion with no `clearEmergencyStop()`
      needed. Assert this directly (kernel accepts a new `drive()` call
      without refusal after the fix fires).
      Verified by test: the same test above additionally asserts
      `kernel.output().estopped == 0` and that a subsequent `drive()`
      call returns `STATUS_OK` after the stop fires.
- [x] A host test confirms a corrupted collect landing during this
      exact window (scripted via the fake motor's collect-failure path)
      increments `i2cFaultCount_` / holds the last-good sample, rather
      than being silently accepted as a valid new reading (closes the
      known risk noted above).
      Verified by test: `tests/host/test_cross_fiber_stop_settle_window.py::
      test_cross_fiber_stop_with_corrupted_collect_holds_last_good_sample`.
- [x] Existing `tests/host/test_regression_post_move_neutral.py` and
      any other tests exercising `stopAll`/`endMove`/`updateMove`
      still pass unchanged.
      Verified: full host suite run, 268 passed (265 baseline + 3 new),
      no failures or changed behavior in any existing test.

## Implementation Plan

**Approach:**
1. Add a small `shims.cpp`-internal helper (e.g.
   `static void deliverStopNow(Rig& r)`) that calls
   `r.left.emergencyStop(); r.right.emergencyStop();` — the exact
   pattern `watchdogEntry()` already uses.
2. Call it from `stopAll()` (after `r.engine.endMove(); r.kernel.neutral();`),
   from the `endMove()` free function (after `rig->engine.endMove();`),
   and from `updateMove()` immediately after `serviceMove()` transitions
   `isMoveActive()` from true to false (mirroring `tickDrive()`'s own
   `wasActive && !moveActive` gate, but delivering the port write here
   instead of relying on a settle-loop re-step that this call path
   never runs).
3. Do not modify `tickDrive()`'s own settle-loop (see AC above) or
   `diffdrive.{h,cpp}`.

**Files to modify:**
- `src/shims.cpp` — new helper; three call sites (`stopAll`, `endMove`,
  `updateMove`).
- `tests/host/` — new settle-window-timing test(s); a corrupted-collect
  test per the AC above. Extend `fake_ports.h` only if the existing
  `FakeMotor`/`FakeSleeper` cannot already script "a call happens
  between the two settle sleeps" — check before adding new fake
  surface.

**Testing plan:** host-only. This is the trickiest test in the sprint
to write correctly — it must control *when* the cross-fiber call
happens relative to `step()`'s internal sleeps, which the existing
`FakeSleeper` may or may not already support hooking. If it doesn't,
extending `FakeSleeper` with a callback-on-sleep hook is in scope for
this ticket (it is test infrastructure, not `src/` source).

**Documentation updates:** none beyond what `design/DESIGN.md`'s
overlay already states — this ticket implements that write-up.
