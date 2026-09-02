---
id: '001'
title: Constant-acceleration/deceleration kinematic core in MotionEngine
status: done
use-cases:
- SUC-001
- SUC-002
depends-on: []
github-issue: ''
issue: trajectory-shaping-constant-acceleration-profiles-speed-chosen-by-distance.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Constant-acceleration/deceleration kinematic core in MotionEngine

## Description

`MotionEngine::serviceMove()`'s deceleration term is `remain /
distTaper_` over a fixed 31.5 mm window (`motion_engine.cpp:356-398`),
so the deceleration it demands grows as v^2 — measured 105 mm/s^2 at
cruise 100 up to 5081 mm/s^2 at cruise 600, with the decel phase
collapsing from 26 control ticks to 2. `startSegment()`'s acceleration
ramp (`motion_engine.cpp:166-183`, `elapsed/rampMs_`, `rampMs_` =
400 ms) is time-based, not acceleration-based, so effective accel
scales with whatever cruise is commanded (`1.875 x cruise`) instead of
being a fixed mm/s^2 rate. Full analysis:
`clasi/issues/trajectory-shaping-constant-acceleration-profiles-speed-chosen-by-distance.md`.

Add real engineering-unit acceleration and deceleration terms to
`MotionEngine`, used only when explicitly enabled — this ticket must
leave every existing caller's behavior byte-for-byte unchanged.

`src/core/diffdrive.{h,cpp}` is vendored byte-identical from
radio-robot and MUST NOT be modified — every change here belongs in
`src/motion/motion_engine.{h,cpp}`, which must stay host-portable
(only `<cstdint>`/`<cmath>` plus `diffdrive.h`, no CODAL/PXT type
anywhere).

## Acceptance Criteria

- [x] `MotionEngine` gains four new private fields with sane inert
      defaults: `aAccelMmS2_ = 0.0f`, `aDecelMmS2_ = 0.0f`,
      `vMaxMmS_` (a real, positive ceiling — e.g. matching
      `fullDutyVelocity`'s ballpark; must never be 0, since `v_default`
      in ticket 002 takes a `min()` against it), `brakeFrac_` (a real
      fraction in `(0, 1]`, e.g. 0.35-0.4 per the issue's own
      accuracy-first recommendation).
- [x] Getters and setters for all four new fields, validated the same
      way `setPivotOverrunMm()`/`setRotationalSlip()` are (silently
      keep the prior value on an invalid input — e.g. reject `<= 0`
      for `aAccelMmS2_`/`aDecelMmS2_`/`vMaxMmS_`, reject outside
      `(0, 1]` for `brakeFrac_`), each with a field comment stating it
      is UNVERIFIED pending the Tier-2 bench sweep (per
      `measurement-citations.md` — no fabricated MEASURED claim).
- [x] Getters added for the five existing shaping fields that
      currently have setters only: `distTaper()`, `yawTaper()`,
      `distFloor()`, `turnFloor()`, `rampMs()` (needed by ticket 003's
      `getConfigValue` read-back).
- [x] `serviceMove()`'s deceleration axis-scale: when `aDecelMmS2_ >
      0`, compute `v_allow = sqrt(2 * aDecelMmS2_ * remain_mm)` (using
      `countsPerMm()` to convert `remain` from counts to mm) and set
      `scale = v_allow / cruise` in place of `remain / distTaper_`.
      Still `min()`-combined with `distFloor_`/`turnFloor_`'s existing
      floor, and never engaging outside `remain <= distTaper_`/
      `yawTaper_`'s existing window trigger — `distTaper_`/`yawTaper_`
      remain the window ceiling, not deleted. When `aDecelMmS2_ ==
      0`, the original `remain / distTaper_` formula runs completely
      unchanged (same code path or a provably identical result — your
      choice, but the legacy branch must not import any of the new
      math).
- [x] `startSegment()`'s acceleration ramp: when `aAccelMmS2_ > 0`,
      replace the `elapsed/rampMs_` fraction and the hardcoded `0.25f`
      first-tick literal with a velocity-slew integrator (`v_cmd <=
      v_prev + aAccelMmS2_ * dt`, `dt` from the engine's own `Clock`),
      still `min()`-combined with the end-of-move taper exactly as
      today (a very short move may go straight from ramp to taper
      without reaching full rate). When `aAccelMmS2_ == 0`, the
      original `elapsed/rampMs_` formula AND the `0.25f` first-tick
      literal run completely unchanged.
- [x] Legacy mode is exactly `aAccelMmS2_ == 0 && aDecelMmS2_ == 0`
      (the shipped default) — with both at their default, every
      pinned regression test passes with NO test-file edits:
      `tests/host/test_motion_engine_deadline_boundary.py`,
      `tests/host/test_regression_yaw_taper_pure_turn.py`.
- [x] No change to `src/core/diffdrive.{h,cpp}` (verify with `git diff
      --stat` before committing).
- [x] `motion_engine.{h,cpp}` still compiles and links with only
      `<cstdint>`/`<cmath>` plus `diffdrive.h` — no new include added.

## Implementation Plan

**Approach**: Add the four new fields and their accessors next to the
existing shaping fields at the bottom of `motion_engine.h` (same
section as `distTaper_`/`yawTaper_`/`distFloor_`/`turnFloor_`/
`rampMs_`). Branch `serviceMove()`'s decel block and `startSegment()`'s
accel block on `aDecelMmS2_ > 0.0f` / `aAccelMmS2_ > 0.0f`
respectively, keeping the existing formula as the `else` (or
equivalently the `== 0` default-path) so legacy behavior is provably
untouched code, not merely a coincidentally-equal new formula.

**Files to modify**:
- `src/motion/motion_engine.h` — four new fields + accessors; five new
  getters for existing fields.
- `src/motion/motion_engine.cpp` — `serviceMove()`'s decel branch,
  `startSegment()`'s accel branch.

**Files NOT to modify**: `src/core/diffdrive.{h,cpp}` (hard
constraint — vendored, byte-identical to radio-robot).

## Testing

- **Existing tests to run**: `tests/host/test_motion_engine_deadline_boundary.py`,
  `tests/host/test_regression_yaw_taper_pure_turn.py`,
  `tests/host/test_motion_engine_primitives.py` (sign-convention pins;
  unaffected but cheap to confirm) — all must pass unmodified.
- **New tests to write**: a minimal smoke test in this ticket confirming
  the four new fields have working, validated setters/getters (full
  constant-decel/constant-accel behavioral proof is ticket 004's job,
  sequenced after tickets 002/003 land the rest of the mechanism).
- **Verification command**: `uv run pytest tests/host/test_motion_engine_deadline_boundary.py tests/host/test_regression_yaw_taper_pure_turn.py tests/host/test_motion_engine_primitives.py`
