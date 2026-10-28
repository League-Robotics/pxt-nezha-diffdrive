---
id: '010'
title: Jerk path honours the speed floor (C9)
status: open
use-cases: ["SUC-005"]
depends-on: []
github-issue: ''
issue: jerk-path-skips-the-speed-floor.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Jerk path honours the speed floor (C9)

## Description

C9. With `jerk > 0` the shaper's ramp-down skips `vFloor` and the command decays through the stiction band (review F8). Apply the floor on the jerk path: ramp down to the floor and never through it.

## Files

- `src/motion/velocity_shaper.cpp` (the step-4 guard around lines 104-106: `if (lim.jerk <= 0.0f && remain >= 0.0f && vNext < floor) vNext = floor;` exempts the jerk path)
- `tests/host/test_velocity_shaper.py` (and `velocity_shaper_shim.cpp` if a new probe is needed)

Keep the "a jerk-limited reference must ramp through it instead of stepping to it" intent: the ramp reaches the floor smoothly, then holds it until the arrival logic completes the segment; do not reintroduce a step to the floor from above it. Existing jerk-ramp shape tests must keep passing; if one pinned the through-the-floor behaviour, change it deliberately and say so in the ticket.

## Acceptance Criteria

- [ ] with `jerk > 0`, the last nonzero command is >= the floor
- [ ] with `jerk > 0`, the ramp is still jerk-limited (no step above the jerk bound before the floor)
- [ ] all existing `test_velocity_shaper.py` cases pass unchanged (or an updated case is justified in the ticket)

## Testing

- **Existing tests to run**: `env -u VIRTUAL_ENV uv run pytest tests/host/test_velocity_shaper.py tests/host/test_motion_engine_nudge.py -q`
- **New tests to write**: a jerk > 0 stop that asserts the last nonzero command >= floor
- **Verification command**: `env -u VIRTUAL_ENV uv run pytest tests/host/test_velocity_shaper.py -q`

## Constraints (all tickets)

- Host-only: there is no hardware in this sprint. Nothing here may claim a hardware result.
- Never send brick opcode `0x1D` (motor reset) from firmware, and never put it in the simulator's command table as something the firmware emits.
- `src/core/diffdrive.h` and `src/core/diffdrive.cpp` (the vendored kernel) stay byte-identical. `git diff --stat` / a checksum before and after must show them untouched.
- Any measured claim in a comment, doc or test names its artifact (`.claude/rules/measurement-citations.md`): cite `docs/knowledge/2026-10-27-nezha-brick-opcodes.md` and the CSVs under `docs/code-review/2026-10-27/data/`, never a bare "measured".
- Defaults this sprint: `position_mode` 0, `speed_path` 0.
- Sources: `docs/code-review/2026-10-27/change-plan.md` section 2, `docs/code-review/2026-10-27/motor-path-review.md` (sections 4, 6).
- Design docs for this sprint are in `clasi/sprints/042-*/design/` (overlay); do not edit canonical `DESIGN.md` files except where the ticket says so.
