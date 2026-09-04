---
id: '002'
title: 'MotionLimits and VelocityShaper: new host-portable objects, not yet wired
  in'
status: open
use-cases: [SUC-002, SUC-003, SUC-004]
depends-on: []
github-issue: ''
issue: code-review/one-velocity-shaper-profile-object-out-of-servicemove.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# MotionLimits and VelocityShaper: new host-portable objects, not yet wired in

## Description

Build the two new host-portable objects design §4.1-4.2 defines, in
isolation — **not yet wired into `MotionEngine`** (that is ticket 003).
Independent of ticket 001 (design §11: "Tickets 1 and 2 are independent
of each other and of the rest").

`MotionLimits` (`src/motion/motion_limits.h`, new): a value object
holding the nine shaping fields (`accel`, `decel`, `jerk`, `vMax`,
`omegaMax`, `vFloor`, `omegaFloor`, `stopDistance`, `arriveDist`,
`arriveYaw` — design §4.1's exact struct), each with a trailing
`// [unit]` comment per `.claude/rules/no-units-in-identifiers.md`, plus
`omegaFloorAsWheelSpeed(trackWidth)`/the equivalent ceiling conversion
(design §6.2), and "positive, else keep" setters matching the existing
pattern (`setTrackWidth()` etc. in `MotionEngine`). `<cstdint>` and libc
only — no CODAL, no I2C.

`VelocityShaper` (`src/motion/velocity_shaper.h/.cpp`, new): the single
`advance()` function — design §6.1's five-step algorithm verbatim
(braking plan, rate limit, optional jerk rounding, floor, arrival
decision) — plus `reset()`, `velocity()`, `acceleration()`. Stateful
only in its own last-commanded speed/acceleration (design §4.2's exact
class shape). Host-portable: no counts, no wheels, no kernel knowledge.

## Acceptance Criteria

- [ ] `tests/host/test_velocity_shaper.py` (design §9.1), green: from
      rest the first command is the floor; accel never exceeds
      `accel` above the floor; decel never exceeds `decel`; with
      `jerk` set, acceleration never steps by more than `jerk·dt`;
      `arriving` fires exactly when `remain <= v·dt + stop`.
- [ ] `MotionLimits` compiles host-portable (`<cstdint>` + libc only,
      verified by the existing host-portability link check).
- [ ] Every field name matches design §4.7's wire-name mapping (this
      ticket does not wire the wire surface — ticket 004 — but the
      struct's field names must already match what ticket 004 will
      expose, to avoid a rename later).
- [ ] No `MmS`/`Ms`/`Mm`/`Rad`/`Counts` suffix on any new identifier in
      these two files (`.claude/rules/no-units-in-identifiers.md`);
      every field carries a trailing `// [unit]` comment.
- [ ] Neither file is referenced by `MotionEngine` yet (confirmed by
      `motion_engine.cpp` having zero new includes from this ticket).

## Implementation Plan

**Approach**: Write `VelocityShaper::advance()` test-first against
design §6.1's pseudocode, one property per test (braking-plan, rate
limit, jerk, floor, arrival) before implementing. `MotionLimits` is a
plain struct with setters; no algorithm to test beyond validation
(reject non-positive values, matching the existing
`setTrackWidth()`/`setRotationalSlip()` pattern in `MotionEngine`).

**Files to create**:
- `src/motion/motion_limits.h`
- `src/motion/velocity_shaper.h`
- `src/motion/velocity_shaper.cpp`
- `tests/host/test_velocity_shaper.py`

**Testing plan**: `tests/host/test_velocity_shaper.py`, scoped run
(`.claude/rules/source-code.md`). No hardware, no simulator — purely
host-side per design §9.1.

**Documentation updates**: None yet — `src/motion/DESIGN.md`'s and
`src/DESIGN.md`'s references to these new files are updated by ticket
003, once they are actually wired in (documenting an unwired object
would describe dead code).
