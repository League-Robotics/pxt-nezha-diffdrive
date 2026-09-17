---
id: '002'
title: 'Diagnose and fix: STATUS active staleness + reverse-to-forward driveTick hang'
status: done
use-cases:
- SUC-003
depends-on: []
github-issue: ''
issue: status-active-stays-1-after-a-soft-stop.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Diagnose and fix: STATUS active staleness + reverse-to-forward driveTick hang

## Description

Two symptoms, diagnosed together because the new hardware evidence
suggests one mechanism rather than two:

**1. `STATUS active` sticks at 1 after a stop.** `Rig::softStop()`
(`src/shims.cpp:391`) clears the move engine, commands the kernel
neutral, and writes the motor port directly — but never forces a fresh
kernel `Output`. `WireAdapter::status()`'s `active` bit
(`src/comms/wire_adapter.cpp:312`) is `ready && !estopped &&
!leaseExpired && !stallHalted && (velocityLeft != 0 || velocityRight
!= 0)`, reading whatever `Output` the kernel last published — the
stale mid-drive velocity, forever, if nothing steps the kernel again.
The "natural deadline" path already has a fix for this shape
(`tickDrive()`'s `settleToRest()` call, `shims.cpp:716-719`,
`motion_engine.h:195-199`); the explicit stop paths (`stop()`,
wire `STOP`, the starvation watchdog) do not.

**2. NEW, 2026-09-15: a `driveTick()` loop following a reversal
sometimes does not finish its tick budget and never prints its
completion line.** Evidence:
`captures/calibratel-vevov-20260915/bench-log.md` (git-add -f'd copy
in this repo; frames beside it; original at
`/Volumes/Proj/proj/league-projects/scratch/nezha-robot-template/captures/calibratel-vevov-20260915/`):

- Run 7: `reverse -10/-10 x40` completes normally (`i2cf +3 over cyc
  +40`, prints `CALL:nudged x=-7.2cm heading=2.71deg`); the immediately
  following `forward 10/10 x40` ends at `cyc +16` with **no**
  `CALL:nudged` line printed within an 8 s wait.
- Run 8: `reverse -4/-4 x40` completes normally (`i2cf +36 over cyc
  +40`, prints its line); the immediately following `forward 4/4 x40`
  ends at `cyc +17`, again **no** completion line.
- Run 9: `STOP` issued right after, then `STATUS` three times, 3 s
  apart: `active=1`, `cyc` frozen at 2901 across all three reads.

Both early endings happen on a reverse-to-forward transition, and in
both the test's own post-loop sequence (`stop(); pause(40);` then an
`emitLine()` with the pose) never printed anything at all — not "ended
early with a printed result", but silence. That points at something
not returning control to the caller, not merely an early-terminating
loop. Run 9's frozen `active=1`/frozen `cyc` may be the SAME mechanism
as symptom 1 (nothing stepped the kernel since the stop) or may be
downstream of symptom 2 (the RUN fiber itself never resumed to call
`STOP`'s own subsequent ticks) — the repro below is designed to tell
them apart.

**Candidates for symptom 2**, all to check on hardware before touching
code:

- The port's 100 ms reversal dwell (`src/platform/nezha_port.cpp:236-250`)
  interacting with `driveTick()`'s return value or the starvation
  watchdog (`src/shims.cpp:661-800`, `commandLooksActive()`,
  `src/shims.cpp:848-862`) — e.g. a return-value/active-detection edge
  case around a dwelling wheel that makes the loop's own `while
  (driveTick())` exit silently, or the watchdog force-stopping a fiber
  that was about to print.
- A `busGuard.acquire()` that never returns for some caller, deadlocking
  the fiber that was going to run the loop's tail (`stop(); pause(40);
  emitLine(...)`).
- A dropped `emitLine()` — the emit ring can silently drop a line under
  load, counted in diag 29 (`src/shims.cpp:29` comment area /
  `WireAdapter`'s diag table) — which would explain a missing
  completion line without a real hang, but does NOT by itself explain
  `cyc` stalling at +16/+17 instead of +40.

This is fiber-scheduling-adjacent code
(`.claude/rules/fiber-yield-safety.md`): if the root cause turns out to
be a genuine stuck fiber (not just a silently dropped line), treat it
with the same seriousness as that rule's own 2026-09-01 hard-fault
precedent — a wedged fiber is a real safety concern, not a cosmetic
telemetry gap. If any new or touched code yields, it must go through
`vfpSafeSleep()`/`vfpSafeYield()`.

## Why this ticket is sequenced before tickets 003/004

The characterization gate (003) fires hundreds of individual pulses
across amplitude/width/wheel/temperature cells, and the nudge stepper
(004) pays a reversal dwell on every direction flip by design (issue
text). An unresolved hang on exactly a reverse-to-forward transition
would silently corrupt either one's hardware data. Resolve this first.

## Acceptance Criteria

- [x] A host test (style of `tests/host/test_wire_motion_verbs.py`)
      pins `STATUS active == 0` promptly after every soft-stop path:
      `stop()`/block, wire `STOP`, and the starvation watchdog's own
      forced stop. Done via `tests/host/test_status_active_after_soft_
      stop.py`, exercising the shared `Rig::softStop()` mechanism every
      one of those three call sites routes through (hand-mirrored in
      `motion_engine_shim.cpp::meEndMoveSettledStopSequence()`, since
      `shims.cpp` itself is not host-compilable — see that test file's
      own header comment). Confirmed the test actually detects the
      regression by reverting the fix locally and observing the test
      fail, then restoring it.
- [x] A hardware repro session (**team-lead runs this**, per
      `hardware-tickets-run-them-yourself`), with `TLM FULL` streaming
      and diags 28 and 29 read before and after each step, reproduces
      runs 7-9's pattern (`captures/calibratel-vevov-20260915/bench-log.md`)
      on the current build, to isolate which candidate mechanism is at
      fault. **DONE.** MEASURED vevov 2026-09-15/16,
      `captures/039-002-repro-20260915/notes.md` (pre-fix control) and
      `captures/039-002-repro-20260915/repro-results.md` (repro proper).
      The isolation the criterion asked for did not land a root cause —
      see the fallback criterion below and
      `clasi/issues/reverse-to-forward-drivetick-hang-never-reproduced.md` —
      but the session itself ran: pre-fix control confirmed the stale
      `active=1`/frozen-`cyc` baseline
      (`calibrate-l-bench 1.20260912.8`, `notes.md` lines 14-40), and the
      post-fix repro exercised 22 reverse/forward transitions (14
      wheels-up, 8 loaded on the floor) with `TLM`-visible tick counts
      and completion-line/drop accounting throughout
      (`repro-results.md`).
- [x] After the fix, the same hardware repro is repeated and shows: the
      reverse-then-forward `driveTick()` loop completes its full
      commanded tick count and prints its completion line every time
      (run it enough times to be confident it is not intermittent), and
      `STATUS active` reads `0` promptly after a subsequent `STOP`.
      **DONE, both halves.** MEASURED vevov 2026-09-16,
      `captures/039-002-repro-20260915/repro-results.md`: Defect 1
      (stale `active`) is CONFIRMED FIXED — post-fix idle reads
      `active=0` every time after real motion (`cyc` 198/473/841/1205
      across four checks; Result 1, Result 3). Defect 2 (the hang) did
      NOT reproduce in 22 reversal transitions at both -4/+4 and
      -10/+10 cm/s, unloaded and loaded (`ranTicks=40/40`, completion
      line present, `runDrops=0`/`emitDrops=0` on every run; Result 2,
      Result 3). Per the same capture's "What this does and does not
      settle" section: not-reproduced is measured, "the hang was fixed"
      is not, because this build also carries the Defect 1
      `settleToRest()` change to the same stop path the hang followed —
      see the fallback criterion below.
- [x] The fix does not edit `src/core/diffdrive.{h,cpp}`. Confirmed —
      the Defect 1 fix touches only `src/shims.cpp` (production) and
      `tests/host/` (test scaffolding).
- [x] Any new yield point goes through
      `vfpSafeSleep()`/`vfpSafeYield()`. No new yield points: the fix
      reuses `MotionEngine::settleToRest()` and `BusGuard::acquire()`,
      both already-existing, already-hardened call paths this file uses
      elsewhere for the identical purpose — no new call site added.
- [ ] **Fallback**: if the debugging budget (see `systematic-debugging`
      skill's attempt cap) is exhausted without isolating a root cause,
      document findings, apply the documented workaround (avoid
      reverse-then-immediate-forward `driveTick()` loops in ticket
      003's characterization script and ticket 004's nudge sequencing),
      and file a follow-up issue — do not block sprint close
      indefinitely on this ticket. **STILL PARTIAL, updated after the
      hardware session.** Findings are documented in
      `docs/knowledge/2026-09-15-reverse-to-forward-drivetick-hang-
      diagnosis.md` (source audit, leading hypothesis) and now also in
      `captures/039-002-repro-20260915/repro-results.md`'s "What this
      does and does not settle" section: MEASURED vevov 2026-09-16, 22
      reversal transitions (14 wheels-up, 8 loaded) produced zero
      repros of the original hang, but the tested build also carries
      the Defect 1 fix (`engine.settleToRest()` added to the same stop
      path the hang followed), so "does not reproduce on this build" is
      the honest finding — NOT "root cause isolated" and NOT "fixed".
      The root cause was never isolated. The follow-up issue is now
      filed and committed:
      `clasi/issues/reverse-to-forward-drivetick-hang-never-reproduced.md`
      (states what would settle it — reflash the original firmware and
      retry). Left unchecked: the documented workaround (avoiding
      reverse-then-immediate-forward loops in tickets 003/004) has not
      been applied anywhere, because tickets 003 and 004 are still
      `open` (not yet executed) as of this ticket's close — that
      remains for whoever executes them next, informed by the filed
      issue.

## Testing

- **Existing tests to run**: `tests/host/test_wire_motion_verbs.py`
  and the `Rig`/`WireAdapter`/watchdog host suites (scope to touched
  modules per `.claude/rules/source-code.md`).
- **New tests to write**: a host test for `Rig::softStop()`'s explicit
  path publishing a fresh, at-rest `Output` before `STATUS` is read
  (not relying on a later `tickDrive()` call); if the reversal-hang
  root cause is isolated to host-reachable logic (the watchdog/
  `commandLooksActive()`/dwell interaction), a host test reproducing it
  with a fake motor port and a fake clock.
- **Verification command**: the project's host test runner, scoped to
  touched modules; the hardware repro is run separately by team-lead,
  never piped (`.claude/rules/never-pipe-a-hardware-gate` /
  memory `never-pipe-a-hardware-gate.md`), gate result read first.
