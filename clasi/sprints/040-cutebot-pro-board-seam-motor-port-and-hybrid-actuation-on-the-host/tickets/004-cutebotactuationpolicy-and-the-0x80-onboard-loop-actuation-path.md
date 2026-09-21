---
id: '004'
title: CutebotActuationPolicy and the 0x80 onboard-loop actuation path
status: open
use-cases: ["SUC-003", "SUC-004"]
depends-on: ["002", "003"]
github-issue: ''
issue: cutebot-pro-board-seam-and-hybrid-port.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# CutebotActuationPolicy and the 0x80 onboard-loop actuation path

## Description

Depends on ticket 002 (`CutebotMotorPort`/`CutebotDevice` must exist to
ship a frame) and ticket 003 (`WheelCommandTap` is the policy's other
input). This is the sprint's hybrid-actuation payload — §3.D and §1.5
of the design doc, and the stakeholder's 2026-09-21 direction: our
kernel below the handoff, the Cutebot's own loop at cruise.

- `src/platform/cutebot_actuation_policy.h/.cpp`: a **pure function**,
  `CutebotActuationPolicy::decide(PolicyState prevState, WheelStaged
  kernelDuty, WheelSetpoint tapSetpoint, int mode, float floorMmS) ->
  {FrameChoice, PolicyState}` (exact types at the implementer's
  discretion, but it must take no I2C/board/kernel reference — testable
  with zero simulated bus in the link, matching `MotionLimits`/
  `VelocityShaper`'s existing pattern per this sprint's Design
  Rationale). Three modes: `0` off (always PWM), `1` threshold with
  hysteresis (engage at both |v| ≥ some configured threshold, release
  below a lower one), `2` plateau-only (engage only once the shaper
  reports cruise, release the moment braking begins — the tap or a
  companion signal must carry enough phase information for this; if
  `WheelCommandTap` as built in ticket 003 does not yet expose a
  phase/"is cruising" signal, extend it here rather than inventing a
  second channel).
- **Both-wheels eligibility gate**: `0x80` treats 0 as "stop" but
  clamps any nonzero value below 200 mm/s up to 200 (design doc §1.5),
  so a wheel commanded under the floor (other than exactly 0) can never
  be handed to the onboard loop. The policy must gate on BOTH wheels —
  an arc whose inner wheel is under the floor keeps the WHOLE pair on
  PWM, never split one wheel per frame (the hardware takes one frame
  for both wheels; there is no way to split it).
- `CutebotDevice` (ticket 002) calls the policy once per kernel cycle
  with its own currently-staged duties and the tap's currently-shaped
  setpoint, and ships exactly the frame the policy returns — PWM
  (`0x10`) or the onboard setpoint (`0x80`).
- Two new `comms/config_fields.h` rows, appended after the existing
  last ordinal (42): `{"onboard_pid", 43, "1"}` and `{"onboard_floor",
  44, "mm/s"}`, following the existing `ConfigFieldDescriptor`
  pattern exactly (see the header's own row-comment convention,
  `// ConfigField.<Name>: "<label>"`). Wire behaviour lives in
  `shims.cpp`'s `kConfigAccessors`/board-diagnostics-hook pattern (per
  the seam from ticket 001), reading/writing the policy's mode/floor on
  whichever board is composed — a Nezha build's accessor is a no-op
  that reports `0`/refuses `SET`, since the fields are meaningless
  without a Cutebot. `SET onboard_pid 0` must always be reachable and
  must always ship PWM only, with no dependency on any other config
  value — the sprint's own explicit escape-hatch requirement.
- Re-run `tools/gen_config_field_enum.py` and commit the regenerated
  `blocks/motion.ts` `ConfigField` enum; `tests/tools/
  test_gen_config_field_enum.py` must pass.
- Extend `tests/host/sim_cutebot_bus.h` (from ticket 002) with a
  simulated onboard loop for `0x80`: a first-order lag driving the
  shared `SimWheel` toward the commanded setpoint, with the 200 mm/s
  clamp modelled (nonzero inputs below 200 clamp up; zero passes
  through), per design doc §7's own description of this fixture — so a
  policy bug that hands the loop an under-floor nonzero setpoint is
  visible on the host, not just a bench finding for sprint 041.

## Acceptance Criteria

- [ ] `CutebotActuationPolicy::decide()` is a pure function (no I2C,
      no `MotionEngine`, no kernel reference) exercised entirely
      through `test_cutebot_actuation_policy.py`.
- [ ] Mode `0` ships PWM unconditionally regardless of setpoint or
      floor — a host test drives both wheels well above the floor with
      mode 0 and asserts the PWM frame is chosen every tick.
- [ ] Mode `1`'s hysteresis is proven: engages at/above the upper
      threshold, stays engaged through the gap between thresholds, and
      releases at/below the lower one — not a single crossing value.
- [ ] Mode `2` engages only once cruise/plateau phase is reported and
      releases at the first sign of braking.
- [ ] The both-wheels eligibility gate is proven with one wheel above
      floor and the other below (or one exactly 0, one nonzero-under-
      floor) — the pair stays on PWM in every such case.
- [ ] `onboard_pid` (43) and `onboard_floor` (44) are reachable
      `GET`/`SET` rows, covered by `test_config_surface_single_source.py`
      and `test_gen_config_field_enum.py`; the regenerated
      `ConfigField` enum is committed.
- [ ] `sim_cutebot_bus.h`'s simulated onboard loop models the 200 mm/s
      clamp (nonzero-under-200 clamps up; exactly 0 passes through) and
      a plausible first-order response, exercised by at least one new
      host test distinct from `sim_tour.py` (ticket 006 covers the
      full-tour case).
- [ ] A Nezha-composed build's `onboard_pid`/`onboard_floor` accessors
      do not crash and behave as a documented no-op/refusal — the
      config rows exist on the wire for every board (append-only
      table), but only mean something on a Cutebot.

## Testing

- **Existing tests to run**: full `uv run pytest`, plus
  `test_config_surface_single_source.py` and
  `test_gen_config_field_enum.py` specifically (both must be extended,
  not just re-run, per the acceptance criteria above).
- **New tests to write**: `test_cutebot_actuation_policy.py` (pure
  policy, all three modes, the eligibility gate);
  `sim_cutebot_bus.h`'s onboard-loop extension gets its own focused
  test (or is folded into `test_cutebot_port.py`'s file, at the
  implementer's discretion) proving the clamp and lag model in
  isolation, ahead of ticket 006's full-tour proof.
- **Verification command**:
  `uv run pytest tests/host/test_cutebot_actuation_policy.py`, then
  full `uv run pytest`.
