---
id: '004'
title: Host-simulation acceptance tests for constant-decel, independent accel, and
  v_default
status: done
use-cases:
- SUC-001
- SUC-002
- SUC-003
depends-on:
- '001'
- '002'
- '003'
github-issue: ''
issue: trajectory-shaping-constant-acceleration-profiles-speed-chosen-by-distance.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Host-simulation acceptance tests for constant-decel, independent accel, and v_default

## Description

Tickets 001-003 land the mechanism; this ticket is the Tier-1
cross-cutting acceptance proof from the issue's own Verification
section, tying the kinematic core, the distance-default resolver, and
the wire exposure together end to end. It is sequenced last among the
implementation tickets (rather than folded into 001/002 individually)
because it re-uses ticket 003's wire-settable knobs to drive the same
scenarios a bench operator would, and because "does the whole
mechanism behave as specified" is a different question from "does each
piece work in isolation" (which 001-003 already cover in their own
acceptance criteria).

Use the existing tick-loop harness — `_drive_to_completion()`,
`tests/host/test_motion_engine_deadline_boundary.py:317-351` —
sampling `meOutVelocityLeft`/`meOutVelocityRight` per tick, the same
approach `captures/motion-profile-probe-20260901/profile_probe.py`
used to produce the issue's own measured table, but now inside the
pytest suite as a permanent regression gate.

## Acceptance Criteria

- [x] **Constant decel across cruise.** Drive a 1000 mm leg (matching
      the issue's own probe methodology) at cruise 100, 200, 400, and
      600 mm/s with a fixed `aDecelMmS2_` set. Fit the measured
      deceleration (mm/s^2) from each run's sampled velocity trace.
      Assert all four fits agree with the configured `aDecelMmS2_`
      within a documented tolerance — in explicit contrast to
      legacy mode, where the same sweep is asserted to show the
      measured v^2 growth (105 -> 5081 mm/s^2) the issue's own table
      records, confirming the test actually distinguishes the two
      modes rather than passing vacuously.
- [x] **Independent accel/decel.** Fix `aDecelMmS2_`, vary
      `aAccelMmS2_` across at least two values; assert only the
      measured acceleration phase changes. Fix `aAccelMmS2_`, vary
      `aDecelMmS2_`; assert only the measured deceleration phase
      changes.
- [x] **`v_default(D)` monotonicity and safety.** For a range of leg
      distances `D`, assert the resolved default cruise is
      non-decreasing in `D` up to the `vMaxMmS_` ceiling, and that the
      resulting move never requires braking harder than the configured
      `aDecelMmS2_` at any sampled tick (i.e. the move's own measured
      decel never exceeds what was configured — the whole point of
      SUC-003).
- [x] **Legacy bit-for-bit.** With `aAccelMmS2_ == aDecelMmS2_ == 0`
      (the shipped default), assert the sampled velocity trace for a
      representative move is identical (within floating-point
      tolerance, not merely "close") to a trace captured against the
      pre-sprint formula — a golden/reference trace, or a direct
      re-derivation of `remain/distTaper_` and `elapsed/rampMs_`
      inline in the test, either is acceptable as long as it is not
      simply re-running the same (possibly also-buggy) new code path.
      `test_motion_engine_deadline_boundary.py` and
      `test_regression_yaw_taper_pure_turn.py` passing unmodified
      (already required by ticket 001) is necessary but not
      sufficient on its own — add at least one NEW test in this
      ticket that exercises legacy mode through the exact scenario
      this issue's own measured table used (a straight leg at multiple
      cruise speeds), so a future change to the legacy branch that
      happens to keep the OLD pinned tests green cannot silently
      regress this specific documented case.
- [x] All new tests pass; the full `tests/host/` suite (not just the
      new files) passes with no modification to any pre-existing
      pinned test file. (Run scoped to the new file plus both pinned
      regression files plus the two marker/syntax gates, per explicit
      dispatch instruction — this project's standing convention runs
      the full suite once per sprint inside `close_sprint`, not per
      ticket; `git status` confirms no pinned test file was modified.)

## Implementation Plan

**Approach**: New test file(s) under `tests/host/`, e.g.
`test_motion_engine_acceleration_profile.py`, reusing
`_drive_to_completion()` or an equivalent tick-driver. Use ticket
003's `SET`/`GET` wire path (via the test double) or ticket 001's
direct C++ setters (via `meSetX()`-style exports) to configure
`aAccelMmS2_`/`aDecelMmS2_`/`vMaxMmS_`/`brakeFrac_` per scenario —
either is acceptable, but prefer the wire path where practical since it
also exercises ticket 003's SET/GET plumbing as a side effect.

**Files to create**: one or more new test files under `tests/host/`.

**Files to modify**: none among the existing pinned regression files
(`test_motion_engine_deadline_boundary.py`,
`test_regression_yaw_taper_pure_turn.py`) — this ticket adds tests, it
does not edit existing ones.

## Testing

- **Existing tests to run**: the full `tests/host/` suite.
- **New tests to write**: as described in Acceptance Criteria above —
  constant-decel-across-cruise, independent-accel/decel,
  v_default-monotonicity-and-safety, legacy-bit-for-bit.
- **Verification command**: `uv run pytest tests/host/`
