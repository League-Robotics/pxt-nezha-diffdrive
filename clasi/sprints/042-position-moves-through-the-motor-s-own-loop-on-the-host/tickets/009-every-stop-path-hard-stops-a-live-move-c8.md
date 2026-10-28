---
id: 009
title: Every stop path hard-stops a live move (C8)
status: open
use-cases:
- SUC-002
depends-on:
- 008
github-issue: ''
issue: every-stop-path-hard-stops-a-live-move.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Every stop path hard-stops a live move (C8)

## Description

C8 (decision D1: the starvation watchdog keeps its invariant and hard-stops a live move). Every stop path sends `0x5F` first when a move is live or the wheel is above the floor, then the existing `0x60 0`. The kernel's own ramp-to-floor stop stays as it is (identical to hard stop from the floor, `docs/knowledge/2026-10-27-nezha-brick-opcodes.md` 7a, `mb_probe_stops1.csv`).

## Files

- `src/shims.cpp`: `Rig::softStop()`, the watchdog fiber and `commandLooksActive()`, `endMove()`, `STOP`/`ESTOP` handlers, `configureWiring()` call site; add one helper (for example `Rig::hardStopLive()`) so every path funnels through it
- `src/platform/board_nezha.cpp`: `diffdrive_emergency_motor_stop()` loops ports 1 to 4 (was 1..2), keeps the `#ifndef DIFFDRIVE_HOST_BUILD` guard for the real write
- `src/platform/nezha_port.cpp`: `configureWiring()` hard-stops a live port before rewiring
- `README.md`: the tick contract states D1 (a live position move is stopped 100 to 150 ms after the last tick)
- tests: `tests/host/test_position_move_stop_paths.py` (new), source pin for the fault frame's port range

## Acceptance Criteria

- [ ] host test: a live move plus 200 ms without a tick produces `0x5F` on both ports (watchdog), and no further motion
- [ ] `STOP`, `ESTOP`, `stop move` (`endMove()`), `softStop()` and `configureWiring()` during a live move each produce `0x5F` on both ports within one tick, then `0x60 0`
- [ ] a stop on a non-live wheel at or below the floor sends no `0x5F` (frame log unchanged)
- [ ] source pin: the fault frame loop covers ports 1 to 4
- [ ] existing stop pins pass: `test_soft_stop_source_pin.py`, `test_staged_stop_source_pin.py`, `test_status_active_after_soft_stop.py`, `test_stop_move_zeros_continuous_drive.py`

## Testing

- **Existing tests to run**: `env -u VIRTUAL_ENV uv run pytest tests/host/test_soft_stop_source_pin.py tests/host/test_staged_stop_source_pin.py tests/host/test_status_active_after_soft_stop.py tests/host/test_stop_move_zeros_continuous_drive.py tests/host/test_cross_fiber_stop_settle_window.py tests/host/test_board_nezha_diag.py -q`
- **New tests to write**: `tests/host/test_position_move_stop_paths.py`
- **Verification command**: `env -u VIRTUAL_ENV uv run pytest tests/host/test_position_move_stop_paths.py -q`

## Constraints (all tickets)

- Host-only: there is no hardware in this sprint. Nothing here may claim a hardware result.
- Never send brick opcode `0x1D` (motor reset) from firmware, and never put it in the simulator's command table as something the firmware emits.
- `src/core/diffdrive.h` and `src/core/diffdrive.cpp` (the vendored kernel) stay byte-identical. `git diff --stat` / a checksum before and after must show them untouched.
- Any measured claim in a comment, doc or test names its artifact (`.claude/rules/measurement-citations.md`): cite `docs/knowledge/2026-10-27-nezha-brick-opcodes.md` and the CSVs under `docs/code-review/2026-10-27/data/`, never a bare "measured".
- Defaults this sprint: `position_mode` 0, `speed_path` 0.
- Sources: `docs/code-review/2026-10-27/change-plan.md` section 2, `docs/code-review/2026-10-27/motor-path-review.md` (sections 4, 6).
- Design docs for this sprint are in `clasi/sprints/042-*/design/` (overlay); do not edit canonical `DESIGN.md` files except where the ticket says so.
