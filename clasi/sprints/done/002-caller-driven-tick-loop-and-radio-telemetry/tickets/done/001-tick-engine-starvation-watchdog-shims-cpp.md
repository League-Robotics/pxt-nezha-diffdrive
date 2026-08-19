---
id: '001'
title: Tick engine + starvation watchdog (shims.cpp)
status: done
use-cases:
- SUC-001
- SUC-002
- SUC-003
depends-on: []
github-issue: ''
issue: caller-driven-tick-loop-for-diffdrive-pure-tick-model-design-sprint-002-issue.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Tick engine + starvation watchdog (shims.cpp)

## Description

This is the foundational ticket for sprint 002's tick model: it moves
ownership of the kernel's control cycle from the kernel's own
background fiber to whichever fiber calls a new tick primitive, and
adds the safety net that makes that safe. Everything else in the tick
loop half of this sprint (main.ts, protocol.cpp) builds on this
ticket's shims.

Per sprint.md's Architecture (Step 3, "Rig / tick engine") and Design
Rationale, in `shims.cpp`:

- Remove the single `rig->kernel.start()` call in `ensure()`. Replace
  with a comment stating the fiber pacer is intentionally unwired for
  the tick model, and that restoring the call re-enables it (the
  kernel's `start()`/`run()`/`fiberEntry()` stay compiled, untouched,
  unused).
- Extract `serviceMove()` from the existing `updateMove()` body:
  odometry update + progress/deadline/stall check + `kernel.neutral()`
  on done, with a comment stating the no-yield invariant (no
  `fiber_sleep`/yield inside it — this is what keeps the `Rig`
  read-modify-write atomic across fibers/callers). Both the old poll
  path (`updateMove()`) and the new tick path (`tickDrive()`) call it.
- Add `tickDrive()` (new `//%` shim, returns `bool`): records
  `lastTickUs`, runs `kernel.step()` on the caller's own fiber, runs
  `serviceMove()`, then self-paces to the next absolute 24 ms deadline
  before returning (deadline anchored to the previous tick's deadline
  while ticks are consecutive; re-anchored after a gap — lift this
  logic from the kernel's own proven `run()`, `diffdrive.cpp:290-306`).
  It always executes the step this call, even if no move is active —
  see sprint.md's Design Rationale entry on this exact point, since
  continuous-mode driving depends on it. The returned `bool` reports
  `moveActive` state *after* this call's `serviceMove()` ran, matching
  the `while (_tickDrive())` idiom.
- Add `cycleStat(int which)` (new `//%` shim): `0` = period measured µs,
  `1` = busy µs, `2` = overruns (from a NEW Rig-level counter — NOT the
  kernel's own `cycleOverrunCount_`, which is only touched by the
  kernel's unused `run()`), `3` = `cycleCount` (existing kernel Output
  field, unaffected by who calls `step()`).
- Add a concurrency guard: a `stepBusy` flag around `kernel.step()` in
  `tickDrive()` so a second fiber calling `tickDrive()` mid-step (parked
  in the kernel's own settle sleeps) waits on a short poll until clear
  (check-and-set with no intervening yield is atomic on CODAL's
  cooperative fibers).
- Add `Rig` fields: `lastTickUs`, `stepBusy`, and a tick-overrun counter.
- Add the starvation watchdog — **the only background fiber this sprint
  leaves running**, launched from `ensure()` via the existing
  `CodalFiberLauncher`, same mechanism the kernel used to launch its
  own. Every ~50 ms: if (commanded mode is non-neutral OR `moveActive`)
  AND `now - lastTickUs` exceeds ~100 ms (4 periods), call
  `kernel.neutral()`, set `moveActive = false`, and immediately do a
  port-level zero-duty write via the existing `emergencyStop()` path on
  both motor ports (`nezha_port.cpp:80-85` — proven tick-independent,
  the exact-zero short-circuit in `writeShapedDuty()`). This does
  **not** latch the kernel's e-stop — it is a resumable soft stop, a
  third stop flavor distinct from the block API's `stop()`/
  `emergencyStop()` (see sprint.md Design Rationale). Bound: stop within
  ~150 ms of the last tick.

**Architecture-review guidance to carry into this implementation**
(APPROVE WITH CHANGES note from the sprint architecture review): keep
the watchdog's logic clearly delineated within `shims.cpp` — its own
named function/section, not interleaved with the tick engine or
move-engine code — so the file's internal organization stays legible
even as it accumulates responsibilities (composition + odometry +
move-engine + tick-pacing + watchdog, all in one no-header translation
unit per this project's established sprint-001 convention).

## Acceptance Criteria

- [x] `rig->kernel.start()` is no longer called anywhere; the call site
      is replaced by a comment explaining the tick model and how to
      re-enable it.
- [x] `diffdrive.h`/`diffdrive.cpp` are byte-unmodified.
- [x] `serviceMove()` exists as a standalone function with no
      `fiber_sleep`/yield inside it (comment states the invariant); both
      `updateMove()` and `tickDrive()` call it.
- [x] `tickDrive()` always runs exactly one `kernel.step()` +
      `serviceMove()` per call, self-paces to an absolute 24 ms
      deadline (re-anchoring after a gap, no drift while consecutive),
      and returns post-step `moveActive` state.
- [x] `cycleStat(0..3)` reads measured period, busy time, the new
      Rig-level tick-overrun counter, and `cycleCount` respectively.
- [x] A `stepBusy` guard prevents two fibers from executing
      `kernel.step()` concurrently via `tickDrive()`.
- [x] The starvation watchdog is the only background fiber left running
      after this ticket; it never calls into control/PID logic, only
      `kernel.neutral()` + `moveActive = false` + a port-level
      `emergencyStop()` zero-write.
- [x] The watchdog's stop does not latch the kernel's e-stop —
      `kernel.estop()`/`estopLatch_` are untouched by it — and a
      subsequent `tickDrive()` call (a fresh move) resumes motion with
      no `clearEmergencyStop()` needed.
- [x] The watchdog's own code is clearly delineated (its own
      function/section, distinctly commented) within `shims.cpp`, not
      interleaved with tick-engine or move-engine logic.
- [x] No new exported `//%` block-facing surface beyond `tickDrive()`
      and `cycleStat()` — `setWheelsTimed`/`driveTwistTimed`/
      `getConfigValue`'s existing "C++-internal only" convention is
      followed for anything else touched.

## Testing

- **Existing tests to run**: none automated (no unit-test harness in
  this repo, per `docs/design/specification.md` §14) — desk/code review
  against this description and sprint.md's Architecture/Design
  Rationale is the verification for this ticket. The existing simulator
  build (`test.ts` via the MakeCode simulator) should still compile and
  run unaffected, since this ticket touches no simulator-fallback code
  (that's ticket 002's `main.ts` work).
- **New tests to write**: none automated. This ticket's own correctness
  (tick timing, watchdog abandonment bound, resumability without
  e-stop-clear) is not meaningfully testable without real hardware — it
  is covered by sprint.md's Test Strategy deferred-hardware pass
  post-close (tick-count over a timed move, `cycleStat(2)` overrun
  count, the abandoned-loop test, `setWheelSpeeds` without ticking).
  Do not block this ticket on that pass.
- **Verification command**: none (no test runner in this repo). Verify
  by code review against this ticket's acceptance criteria and by
  confirming the MakeCode build still compiles (simulator target).
