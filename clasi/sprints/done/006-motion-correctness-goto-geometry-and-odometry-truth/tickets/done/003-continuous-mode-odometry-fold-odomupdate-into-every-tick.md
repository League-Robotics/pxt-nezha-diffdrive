---
id: '003'
title: 'Continuous-mode odometry: fold odomUpdate() into every tick'
status: done
use-cases:
- SUC-003
depends-on: []
github-issue: ''
issue: continuous-mode-odometry-chord-error.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Continuous-mode odometry: fold odomUpdate() into every tick

## Description

In velocity mode (`setWheelSpeeds`/`driveTwist` under a
`while (tickDrive())` loop), nothing calls `odomUpdate()`. All nine
existing call sites are move-path or pose-read
(`shims.cpp::tickDrive()`/`updateMove()` gate `odomUpdate()` on
`wasActive` — i.e. only while a move-engine move is/was active — plus
the explicit pose-read/reset/seed call sites). The next `pose x/y`
read therefore integrates the *entire* driven interval as one straight
chord regardless of actual curvature: drive a full circle under
constant twist in an unconditional tick loop and pose reports
approximately the whole path length instead of ~0 (code review R-09,
BLK-05, CONFIRMED with the scenario corrected to an unconditional tick
loop — the documented `while (diffDrive.driveTick())` idiom actually
exits after one tick in continuous mode, a separate, already-known
discrepancy this ticket does not need to fix).

This directly contradicts `docs/design/usecases.md`'s own UC-009
postcondition, which already states "pose is always live-updated from
odometry regardless of command mode" — today that sentence is
aspirational, not true.

**Fix, at the module level:** `tickDrive()` folds `odomUpdate()` into
**every** tick unconditionally, not only while `wasActive`
(`r.engine.isMoveActive()`) is true. `updateMove()`'s own odometry
gating (only while a move is active — the correct behavior for
move-engine polling, a different call path from continuous-mode
driving) is unchanged.

**C++11 gate coverage:** this fix lives entirely in `shims.cpp`, which
is **not** covered by `tests/host/test_cxx11_syntax_gate.py`. A green
host suite proves the logic is correct; it does not prove this
ticket's code compiles for either real embedded target.

## Acceptance Criteria

- [x] A host test drives a full circle under constant twist
      (`wheelsV`/`moveV`-equivalent continuous command) in an
      unconditional tick loop (mirroring `testrig.ts:118-120`'s
      pattern, not the documented-but-broken
      `while (driveTick())` idiom) and asserts pose reads back near
      the origin, not approximately the full path length.
- [x] `updateMove()`'s existing odometry gating (`if (wasActive)
      odomUpdate(r);`) is unchanged — a host test confirms no
      regression to move-engine polling's existing odometry behavior.
- [x] No double-integration: a test confirms a single `tickDrive()`
      call during an *active move* does not call `odomUpdate()` twice
      (once from the new unconditional fold, once from any
      move-active-gated path) — `tickDrive()`'s own existing
      `if (wasActive) odomUpdate(r);` call ahead of `serviceMove()`
      must be reconciled with the new unconditional call, not
      duplicated.
- [x] Existing move-engine odometry tests (any test asserting pose
      correctness immediately after a discrete `moveX`/`goToR` move)
      pass unchanged.

## Implementation Plan

**Approach:** in `tickDrive()`, change the existing
`const bool wasActive = r.engine.isMoveActive(); if (wasActive)
odomUpdate(r);` (called once before `serviceMove()`) to call
`odomUpdate(r)` unconditionally, once per tick, while still computing
`wasActive` for the existing post-`serviceMove()` settle-loop gate
(`if (wasActive && !moveActive) { ... }`), which is unaffected by this
change. Verify `odomUpdate()` itself is idempotent/safe to call on a
tick with zero encoder movement (it should already be — it computes a
delta against the last-read kernel `Output` positions, which is `0` if
nothing moved).

**Files to modify:**
- `src/shims.cpp` — `tickDrive()`'s odometry call.
- `tests/host/` — new continuous-mode circle-closure test; a
  double-integration regression test.

**Testing plan:** host-only. Use the existing kernel/motion-engine host
harness to script a constant-twist velocity command and tick it
through a closed circle's worth of ticks, then assert pose.

**Documentation updates:** none beyond `design/DESIGN.md`'s overlay,
which this ticket implements.
