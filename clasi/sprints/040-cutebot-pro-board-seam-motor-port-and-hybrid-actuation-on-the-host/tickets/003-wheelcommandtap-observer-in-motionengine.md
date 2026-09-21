---
id: '003'
title: WheelCommandTap observer in MotionEngine
status: open
use-cases: ["SUC-003"]
depends-on: ["001"]
github-issue: ''
issue: cutebot-pro-board-seam-and-hybrid-port.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# WheelCommandTap observer in MotionEngine

## Description

Independent of the Cutebot port itself — this ticket lives entirely in
`motion/`, which this repo owns outright, and touches no I2C or board
code. It only needs ticket 001's seam merged so its own host tests run
against the post-seam tree; it does not need `CutebotMotorPort` to
exist.

Per `docs/design/cutebot-pro-support.md` §3.D ("Where the velocity
setpoint comes from") and §7:

- Add `src/motion/wheel_command_tap.h`: a small, host-portable observer
  interface, e.g. `WheelCommandTap` with `onDrive(float leftMmS, float
  rightMmS)` and `onNeutral()` — no I2C, no board knowledge, no
  dependency beyond libc, matching the layering `heading_wrap.h`/
  `encoder_glitch_armor.h`/`bus_guard.h` already establish for small
  host-portable helpers (`src/DESIGN.md` §1's layer table).
- `MotionEngine` gains one optional (nullable) `WheelCommandTap*`
  member, settable via a new accessor. When set, `MotionEngine`
  notifies it with the shaped `(left, right)` mm/s **alongside**, not
  instead of, every `kernel_.drive()` call
  (`src/motion/motion_engine.cpp:368` for a segment, `:406` for a
  hold — both read during architecture planning and confirmed current)
  and with `onNeutral()` alongside every `kernel_.neutral()` call this
  method makes (the wrong-way/stall/estop/expired abort branch above
  line 368, and the analogous stall/expired branches for the
  continuous-hold path around line 386-395). Audit `motion_engine.cpp`
  for any OTHER `kernel_.neutral()` site this ticket's own read of
  lines 320-413 may not have caught (e.g. inside `endMove()` or a
  pivot-then-straight transition) and notify there too — the whole
  point of a dedicated host test (below) is to make a missed site a
  test failure, not a silent gap.
- When no tap is set (every existing caller, until ticket 002/004's
  `CutebotDevice` registers one), behaviour is **byte-identical** to
  before this ticket — a null check before each notify, zero-cost when
  unset.

## Acceptance Criteria

- [ ] `WheelCommandTap` compiles host-portable (no `pxt.h`, no board
      dependency) and is exercised with zero I2C or kernel-port fakes
      in the link, the same isolation `Odometry`/`VelocityShaper` tests
      already achieve.
- [ ] Every `kernel_.drive()` call site in `motion_engine.cpp` notifies
      the tap with the identical `(left, right)` mm/s values passed to
      `kernel_.drive()` (verified by a test double, not by inspection
      alone).
- [ ] Every `kernel_.neutral()` call site in `motion_engine.cpp`
      notifies the tap's `onNeutral()`.
- [ ] With no tap registered, `MotionEngine`'s behaviour and the full
      existing host suite (particularly
      `tests/host/test_motion_engine_*.py`) are unchanged.

## Testing

- **Existing tests to run**: full `uv run pytest`, especially every
  `test_motion_engine_*.py` file, to confirm the tap is a strict
  addition with the tap unset.
- **New tests to write**: `test_wheel_command_tap.py` — a fake tap
  recording every `onDrive`/`onNeutral` call, driven through
  `MotionEngine::wheelsV`/`wheelsX`/`moveX`/`moveV`/`goToR`/`goToW` and
  every abort path (wrong-way, stall, e-stop, deadline expiry), proving
  the tap sees exactly the values the kernel receives and a
  neutral notification on every path that calls `kernel_.neutral()`.
- **Verification command**:
  `uv run pytest tests/host/test_wheel_command_tap.py`, then full
  `uv run pytest`.
