---
id: 009
title: 'Regression: a move that ends still delivers the kernel''s neutral (3e919e5)'
status: done
use-cases:
- SUC-003
- SUC-004
depends-on:
- '007'
github-issue: ''
issue: implement-motion-api-six-operations.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Regression: a move that ends still delivers the kernel's neutral (3e919e5)

## Description

Add a dedicated, host-run regression test for the second hard-won
behavior ticketing requirement 5 makes mandatory: a move that ends must
still deliver the kernel's staged neutral command to the motors — the
staged zero needs one more `kernel.step()` after the move-completion
check clears the active-move flag, or the wheels coast at full duty
until the starvation watchdog eventually intervenes (measured cost:
~100-150 ms, +9-13 deg per turn, +15-22 mm per leg). Fixed on commit
`3e919e5` in `src/shims.cpp`'s `tickDrive`. This ticket locks that fix
into `motion_engine`'s ported version (ticket 007).

## Acceptance Criteria

- [x] A test drives a `MotionEngine` move (either `moveX` or `wheelsX`,
      whichever the engine's completion path shares) to completion
      against a `FakeMotor` that records every `setDuty()` call in
      order, and asserts that the LAST `setDuty()` call recorded before
      the engine reports the move complete is a neutral (zero) command
      — not the last nonzero commanded duty.
- [x] A second assertion confirms the `FakeMotor`'s recorded velocity
      reads at the moment of completion are at or below the "settle"
      threshold `shims.cpp`'s own `serviceMove` uses (~2 mm/s
      equivalent) — i.e. the settle-tick loop (up to 12 extra steps,
      breaking early once both wheels read near rest) is exercised, not
      just a single extra step assumed sufficient. NOTE (see report):
      the actual up-to-12-iteration loop lives only in
      `shims.cpp::tickDrive()`, which depends on CODAL/PXT platform
      types this host build cannot compile — this assertion is
      satisfied by mirroring that loop's shape (bounded iteration,
      break-on-rest, no re-energizing) against the same portable
      velocity-computation machinery (`diffdrive.cpp`) it depends on,
      not by executing `tickDrive()`'s own loop body. See ticket 013.
- [x] The test's docstring cites commit `3e919e5` and the measured cost
      of the regression, so a future reader can find the original
      incident.
- [x] This test is part of the default `uv run pytest` run.

## Implementation Plan

**Approach**: Same posture as ticket 008 — this is a test-writing
ticket against `motion_engine`'s already-ported completion path
(ticket 007). If the port in ticket 007 dropped the extra
step/settle-loop behavior, fix it in `motion_engine`, not just in the
test.

**Files to create**:
`tests/host/test_regression_post_move_neutral.py` (or a dedicated test
class inside `test_motion_engine_reductions.py`, matching whatever
convention ticket 008 established).

**Files to modify**: none expected.

**Testing plan**: This ticket IS a testing ticket.

**Documentation updates**: none beyond the test file's own
commit-citing docstring.

**Testing**

- **Existing tests to run**: `uv run pytest tests/host/`.
- **New tests to write**: as described in Acceptance Criteria.
- **Verification command**: `uv run pytest tests/host/test_regression_post_move_neutral.py`
