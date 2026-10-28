---
id: '005'
title: speed_path 1 in NezhaMotorPort (C3)
status: in-progress
use-cases:
- SUC-004
depends-on:
- '004'
github-issue: ''
issue: fine-velocity-actuator-behind-a-speed-path-switch.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# speed_path 1 in NezhaMotorPort (C3)

## Description

C3, under decision D2: the fine-velocity actuator behind `speed_path`. This ticket adds the port-side switch (a setter/member on `NezhaMotorPort`); ticket 007 wires it to config. Default 0 is byte-identical to today.

## Files

- `src/platform/nezha_port.h`, `src/platform/nezha_port.cpp`
- new test `tests/host/test_nezha_port_speed_path.py` (sim bus from ticket 003)

## Exact behaviour at `speed_path 1`

- `setDuty(pct)` becomes `0x77 round(pct x 11.5)` degrees per second, written only on change per port, followed by `0x70` direction mode 3 with n = 1 (run time `(10n - 3) x 100 ms` = 0.7 s, so a starved firmware self-stops).
- both frames go out per change (a `0x77` alone does not retarget).
- the existing deadband, reversal dwell, slew and write throttle stay in front of it; the sigma-delta dither is bypassed.
- stop from speed is `0x5F`; a stop that starts at or below the kernel floor keeps today's `0x60 0` (a `0x5F` and `0x60 0` travel the same 0.6 mm from the 8% floor, `docs/knowledge/2026-10-27-nezha-brick-opcodes.md` 7a, `mb_probe_stops1.csv`).
- the position-move latch (ticket 004) still wins: no speed frames on a live move.
- `speed_path 0`: byte-identical frame log to the current pin.

## Acceptance Criteria

- [ ] a ramp 0 -> 60 -> 0 % at `speed_path 1` yields the expected `0x77`/`0x70` pairs (each pair only on change) and exactly one `0x5F`
- [ ] at `speed_path 0` the frame log is unchanged against the existing pin (find the pin among existing tests, e.g. the creep/dither tests, and keep it passing)
- [ ] no `0x1D` frame anywhere

## Testing

- **Existing tests to run**: `env -u VIRTUAL_ENV uv run pytest tests/host/test_creep_self_lock_stiction_sim.py tests/host/test_board_nezha_diag.py tests/host/test_nezha_port_position_move.py -q`
- **New tests to write**: `tests/host/test_nezha_port_speed_path.py`
- **Verification command**: `env -u VIRTUAL_ENV uv run pytest tests/host/test_nezha_port_speed_path.py -q`

## Constraints (all tickets)

- Host-only: there is no hardware in this sprint. Nothing here may claim a hardware result.
- Never send brick opcode `0x1D` (motor reset) from firmware, and never put it in the simulator's command table as something the firmware emits.
- `src/core/diffdrive.h` and `src/core/diffdrive.cpp` (the vendored kernel) stay byte-identical. `git diff --stat` / a checksum before and after must show them untouched.
- Any measured claim in a comment, doc or test names its artifact (`.claude/rules/measurement-citations.md`): cite `docs/knowledge/2026-10-27-nezha-brick-opcodes.md` and the CSVs under `docs/code-review/2026-10-27/data/`, never a bare "measured".
- Defaults this sprint: `position_mode` 0, `speed_path` 0.
- Sources: `docs/code-review/2026-10-27/change-plan.md` section 2, `docs/code-review/2026-10-27/motor-path-review.md` (sections 4, 6).
- Design docs for this sprint are in `clasi/sprints/042-*/design/` (overlay); do not edit canonical `DESIGN.md` files except where the ticket says so.
