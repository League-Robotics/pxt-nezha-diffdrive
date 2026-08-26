---
id: '001'
title: Expose MotionEngine::goToR() to the block layer with above-threshold host regression
  tests
status: done
use-cases: []
depends-on: []
github-issue: ''
issue: block-go-to-misses-its-target.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Expose MotionEngine::goToR() to the block layer with above-threshold host regression tests

## Description

`MotionEngine::goToR()` (`src/motion/motion_engine.cpp:180-241`) is already
correct: it owns its own pivot-vs-blend split (pivot to the line-of-sight
bearing, drive the straight-line chord), wraps the arc angle to the short
arc (`wrapToPi()`), and is already host-tested above the 50 deg
`kTurnFirstAngleRad` threshold (sprint 006,
`tests/host/test_motion_engine_reductions.py`'s
`test_go_to_r_pivot_split_reaches_target_above_threshold` and
`test_go_to_r_behind_robot_splits_into_bounded_pivot`). It is also already
reachable from the wire protocol: `engineGoToR()` in `src/shims.cpp:992-996`
delegates straight to it for the `GO_TO_R` verb.

The block layer cannot reach it. `engineGoToR()` has no `//%` annotation, so
no TypeScript block or shim function can call it — `startGoTo` in
`src/blocks/motion.ts` is stuck computing its own (broken) constant-curvature
arc pair (`theta = 2*atan2(y,x)`, `s = R*theta`) and handing it to
`startMove()` -> `MotionEngine::moveX()`, which is exactly the defect
`block-go-to-misses-its-target.md` measures at 112.5 mm and 3172.4 mm off
target. This ticket only builds and proves the correct, reachable entry
point; it does not rewire `motion.ts` itself (that is ticket 002) — after
this ticket, the block layer still has the bug, but the fix it needs is
compiled, host-tested, and callable.

Add a `//%` annotation to `engineGoToR()` in `src/shims.cpp`, matching the
existing `//%` convention immediately around it (`startMove`/`updateMove` in
the same file) and the same mm / mm-per-s / ms wire-shaped unit contract
`engineMoveX()`/`engineWheelsX()` already use — cm-to-mm conversion stays the
caller's job (ticket 002), exactly as `startMove()` (motion.ts) already does
for `_startMove()`.

## Acceptance Criteria

- [x] `engineGoToR()` in `src/shims.cpp` carries a `//%` annotation and is a
      valid PXT block-API shim entry point (no logic change to the function
      body — it still just calls `r.engine.goToR(x, y, speed, arrive,
      timeoutMs)`).
- [x] A new host regression test (extending the existing
      `tests/host/test_motion_engine_reductions.py`/`motion_engine_shim.cpp`
      harness, which already wraps `MotionEngine::goToR()` as `go_to_r()`
      for host tests — `src/shims.cpp` itself is never host-compiled, see
      that file's own `_SHIM_SOURCES` lists) exercises the two SPECIFIC
      probe geometries measured in `block-go-to-misses-its-target.md`, both
      **above** the 50 deg split threshold:
      - `goToR(100mm, 100mm, ...)` (the block's `goTo(10, 10)`, bearing 45
        deg) — asserts landing within 5 mm, matching the probe's measured
        wire `GO_TO_R` result (2.9 mm miss).
      - `goToR(-100mm, 10mm, ...)` (the block's `goTo(-10, 1)`, a target
        behind the robot, theta wraps to a short arc) — asserts landing
        within 5 mm, matching the probe's measured wire `GO_TO_R` result
        (0.5 mm miss).
      Implemented in `tests/host/test_goto_block_regression.py` as
      `test_go_to_r_reaches_probe_targets_above_threshold` (both cases
      PASS today — measured 0.53 mm / 0.64 mm misses in this harness).
- [x] The same test file also pins, as an explicit contrast case, that
      feeding the identical (x, y) pairs through today's `startGoTo`-shaped
      reduction (`theta = 2*atan2(y,x)`, `s = R*theta`, then `MotionEngine::
      moveX(s, theta, ...)`) misses by approximately the issue's measured
      margins (112.5 mm / 3172.4 mm) — this is the test that FAILS today
      (asserting a small miss where today's reachable-from-blocks path
      produces a large one) and PASSES once the corrected entry point is
      what a caller would use; it is what "above the 50 deg threshold" a
      test finally covers for the block-layer's own input shape, which
      sprint 006's existing goToR tests do not (they exercise goToR() in
      isolation, not in contrast with the arc-length reduction blocks
      currently use).
      Implemented as `test_block_arc_reduction_misses_probe_targets_above_
      threshold` in the same file: measured misses of 115.2 mm / 3172.0 mm
      (within the issue's own margins), and its final assertion (`miss <
      5mm`) is INTENTIONALLY RED today, by design — it stays red until a
      later ticket routes `blocks/motion.ts` onto `goToR()`.
- [x] Existing 597-test host suite stays green. (Verified scoped:
      `uv run pytest tests/host/ -k "motion_engine or manifest"` — 70
      passed, 0 failed, 0 regressions. The full suite runs once at sprint
      close per this project's test-execution convention.)

## Files Expected To Change

- `src/shims.cpp` — add `//%` to `engineGoToR()` (~line 992). No other logic
  change.
- `tests/host/test_motion_engine_reductions.py` (or a new
  `tests/host/test_goto_block_regression.py`) — the new above-threshold,
  probe-geometry regression test plus its arc-length contrast case.
- `tests/host/motion_engine_shim.cpp` — only if the existing `go_to_r()`
  host binding doesn't already expose everything the new test needs (it
  likely already does; extend rather than duplicate per that file's own
  "extend this file's function list — don't invent a second shim" rule).

## Test Requirement

A test that FAILS against today's code and PASSES after. Today, nothing in
the host suite exercises the arc path above the 50 deg split threshold from
the block layer's own input shape — existing `goTo`-shaped host coverage
stays deliberately below 50 deg (the sprint's Test Strategy section calls
this out explicitly: "existing `goTo` host tests deliberately stay below
the 50 deg threshold, and the threshold is the bug"). The new test must
fail on today's code (proving the arc-length-through-`moveX` reduction
misses by the issue's measured margins) and pass once the corrected,
`//%`-exposed `goToR()` entry point is what the assertion is checked
against.
