---
id: '011'
title: nudge in hundredths of a millimetre (C10)
status: done
use-cases:
- SUC-005
depends-on: []
github-issue: ''
issue: nudge-rounds-to-whole-millimetres.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# nudge in hundredths of a millimetre (C10)

## Description

C10. `nudge()` and `beginNudgeWheels()` pass distance as an integer mm, so a 1.79 mm pulse (the measured unit, `captures/039-003-pulse-gate-20260916/notes.md`) cannot be asked for and sub-millimetre trims round away (review F12). Both take hundredths of a millimetre on the shim boundary; the block keeps its mm face and scales.

## Files

- `src/blocks/motion.ts` (`export function nudge(left, right)` near line 364; the `//% block="nudge left %left mm right %right mm"` keeps mm; scale by 100 before the shim call)
- `src/shims.cpp` (`beginNudgeWheels` near line 740: arity/units now hundredths of a mm; divide by 100.0f into the engine)
- every other caller of the shim: grep `beginNudgeWheels` across `src/`, `tools/`, `test/`, `tests/` and fix each
- tests: `tests/host/test_nudge_block_regression.py`, `tests/host/test_identity_setters_shim_arity_source_pin.py` style arity pin for the shim, `tests/host/test_motion_engine_nudge.py` for sim parity

## Acceptance Criteria

- [x] a 0.5 mm nudge request reaches the engine as 50 hundredths and as 0.5 mm distance
- [x] shim arity/units source pin updated and passing
- [x] sim parity: whole-mm nudges give the same engine inputs and pulse counts as before
- [x] no caller left passing whole mm to `beginNudgeWheels`

## Testing

- **Existing tests to run**: `env -u VIRTUAL_ENV uv run pytest tests/host/test_nudge_block_regression.py tests/host/test_motion_engine_nudge.py tests/host/test_motion_engine_nudge_stiction.py tests/host/test_identity_setters_shim_arity_source_pin.py -q`
- **New tests to write**: a 0.5 mm case and the arity pin for the changed shim signature
- **Verification command**: `env -u VIRTUAL_ENV uv run pytest tests/host/test_nudge_block_regression.py tests/host/test_motion_engine_nudge.py -q`

## Constraints (all tickets)

- Host-only: there is no hardware in this sprint. Nothing here may claim a hardware result.
- Never send brick opcode `0x1D` (motor reset) from firmware, and never put it in the simulator's command table as something the firmware emits.
- `src/core/diffdrive.h` and `src/core/diffdrive.cpp` (the vendored kernel) stay byte-identical. `git diff --stat` / a checksum before and after must show them untouched.
- Any measured claim in a comment, doc or test names its artifact (`.claude/rules/measurement-citations.md`): cite `docs/knowledge/2026-10-27-nezha-brick-opcodes.md` and the CSVs under `docs/code-review/2026-10-27/data/`, never a bare "measured".
- Defaults this sprint: `position_mode` 0, `speed_path` 0.
- Sources: `docs/code-review/2026-10-27/change-plan.md` section 2, `docs/code-review/2026-10-27/motor-path-review.md` (sections 4, 6).
- Design docs for this sprint are in `clasi/sprints/042-*/design/` (overlay); do not edit canonical `DESIGN.md` files except where the ticket says so.
