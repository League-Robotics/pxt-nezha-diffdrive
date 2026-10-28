---
id: 008
title: Route verbs and blocks to PositionMove (C7)
status: open
use-cases: ["SUC-001", "SUC-003"]
depends-on: ["007"]
github-issue: ''
issue: position-moves-through-the-motors-own-position-loop.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Route verbs and blocks to PositionMove (C7)

## Description

C7. Route the position verbs to `PositionMove` (ticket 006) when `position_mode` allows and the composed board's ports `supportsPositionMove()`.

## Files

- `src/comms/wire_handler.cpp`, `src/shims.cpp`, `src/blocks/motion.ts`
- `tests/host/test_wire_motion_verbs.py` (extend), `tests/host/wire_motion_verb_shim.cpp` as needed; `tests/host/sim_robot_shim.cpp` for the end-to-end sim path

## Exact behaviour

- Built-in path (mode 1: straights and pivots; mode 2: arcs too): `WHEELS_X`, `MOVE_X`, `GO_TO_R`/`GO_TO_W`, `move`, `goTo`, `whileMoving`, pivots.
- Never the built-in path: `WHEELS_V`, `MOVE_V`, `setWheelSpeeds`, `driveTwist`, line following.
- `position_mode 0`, or a board whose ports do not support position moves (Cutebot), falls back to the kernel path with unchanged behaviour.
- `isDriving()` true during a live move (so `commandLooksActive()` sees it).
- `STATUS` carries a position-move flag naming which path ran (so `tools/mb50.py` can tell); append it in a backward-compatible way and update the STATUS grammar docs/golden telemetry if they pin the field list (`tests/host/golden_telemetry.py`).
- `tests/host/sim_tour.py` closes with `position_mode 1` (a tour leg run in mode 1 on the sim bus, ending within quantum tolerance).

## Acceptance Criteria

- [ ] each position verb takes the built-in path at mode 1 (arcs also at 2) and the kernel path at 0, asserted from the sim-bus frame log (`0x70` present/absent)
- [ ] `WHEELS_V`/`MOVE_V`/twist never produce a `0x70`
- [ ] `STATUS` flag set only during a built-in move
- [ ] `test_continuous_drive_command_looks_active.py` still passes
- [ ] sim tour closes with `position_mode 1`
- [ ] the full motion-verb test file passes with the new cases

## Testing

- **Existing tests to run**: `env -u VIRTUAL_ENV uv run pytest tests/host/test_wire_motion_verbs.py tests/host/test_continuous_drive_command_looks_active.py tests/host/test_wire_motion_completion.py tests/host/test_goto_block_regression.py -q`
- **New tests to write**: extend `test_wire_motion_verbs.py`; add a sim-tour case with `position_mode 1`
- **Verification command**: `env -u VIRTUAL_ENV uv run pytest tests/host/test_wire_motion_verbs.py tests/host/test_continuous_drive_command_looks_active.py -q`

## Constraints (all tickets)

- Host-only: there is no hardware in this sprint. Nothing here may claim a hardware result.
- Never send brick opcode `0x1D` (motor reset) from firmware, and never put it in the simulator's command table as something the firmware emits.
- `src/core/diffdrive.h` and `src/core/diffdrive.cpp` (the vendored kernel) stay byte-identical. `git diff --stat` / a checksum before and after must show them untouched.
- Any measured claim in a comment, doc or test names its artifact (`.claude/rules/measurement-citations.md`): cite `docs/knowledge/2026-10-27-nezha-brick-opcodes.md` and the CSVs under `docs/code-review/2026-10-27/data/`, never a bare "measured".
- Defaults this sprint: `position_mode` 0, `speed_path` 0.
- Sources: `docs/code-review/2026-10-27/change-plan.md` section 2, `docs/code-review/2026-10-27/motor-path-review.md` (sections 4, 6).
- Design docs for this sprint are in `clasi/sprints/042-*/design/` (overlay); do not edit canonical `DESIGN.md` files except where the ticket says so.
