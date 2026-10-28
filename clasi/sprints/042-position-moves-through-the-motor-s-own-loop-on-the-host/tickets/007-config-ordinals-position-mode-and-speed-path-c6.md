---
id: '007'
title: Config ordinals position_mode and speed_path (C6)
status: in-progress
use-cases:
- SUC-003
- SUC-004
depends-on:
- '005'
- '006'
github-issue: ''
issue: position-moves-through-the-motors-own-position-loop.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Config ordinals position_mode and speed_path (C6)

## Description

C6. Two config ordinals and their plumbing, using the single-source generator flow.

## Files

- `src/comms/config_fields.h`: append `position_mode` (next ordinal after `twist_ff` 51, so 52) and `speed_path` (53); verify the table ends at 51 first. Default strings `"0"` and `"0"`.
- run `env -u VIRTUAL_ENV uv run python tools/gen_config_field_enum.py` and commit its output in `src/blocks/motion.ts` (never hand-edit the generated enum)
- `src/shims.cpp` config table/accessors: `position_mode` (0 kernel, 1 built-in for straights and pivots, 2 built-in for arcs too; default 0) stored on `Rig`; `speed_path` (0 `0x60`, 1 `0x77`+`0x70` mode 3) forwarded to the Nezha ports; Cutebot-composed builds refuse/ignore both the way `onboard_pid` is documented to on the wrong board
- `set config` names resolve through the descriptor table

## Acceptance Criteria

- [ ] `position_mode` and `speed_path` appear in the descriptor table, the generated block enum, and `set config` by name and ordinal
- [ ] defaults are 0 and 0
- [ ] values outside the documented range are refused with the existing config error shape
- [ ] `test_config_descriptor_table.py` and `test_config_surface_single_source.py` pass (extend them for the new rows)
- [ ] generator run leaves a clean second run (idempotent)

## Testing

- **Existing tests to run**: `env -u VIRTUAL_ENV uv run pytest tests/host/test_config_descriptor_table.py tests/host/test_config_surface_single_source.py -q`
- **New tests to write**: extend the two tests above with the new rows, default values and range refusals
- **Verification command**: `env -u VIRTUAL_ENV uv run pytest tests/host/test_config_descriptor_table.py tests/host/test_config_surface_single_source.py -q`

## Constraints (all tickets)

- Host-only: there is no hardware in this sprint. Nothing here may claim a hardware result.
- Never send brick opcode `0x1D` (motor reset) from firmware, and never put it in the simulator's command table as something the firmware emits.
- `src/core/diffdrive.h` and `src/core/diffdrive.cpp` (the vendored kernel) stay byte-identical. `git diff --stat` / a checksum before and after must show them untouched.
- Any measured claim in a comment, doc or test names its artifact (`.claude/rules/measurement-citations.md`): cite `docs/knowledge/2026-10-27-nezha-brick-opcodes.md` and the CSVs under `docs/code-review/2026-10-27/data/`, never a bare "measured".
- Defaults this sprint: `position_mode` 0, `speed_path` 0.
- Sources: `docs/code-review/2026-10-27/change-plan.md` section 2, `docs/code-review/2026-10-27/motor-path-review.md` (sections 4, 6).
- Design docs for this sprint are in `clasi/sprints/042-*/design/` (overlay); do not edit canonical `DESIGN.md` files except where the ticket says so.
