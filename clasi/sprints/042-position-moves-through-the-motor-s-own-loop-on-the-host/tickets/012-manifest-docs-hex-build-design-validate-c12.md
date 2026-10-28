---
id: '012'
title: Manifest, docs, hex build, design validate (C12)
status: in-progress
use-cases:
- SUC-001
- SUC-005
depends-on:
- '001'
- '002'
- '003'
- '004'
- '005'
- '006'
- '007'
- 008
- 009
- '010'
- '011'
github-issue: ''
issue: position-moves-through-the-motors-own-position-loop.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Manifest, docs, hex build, design validate (C12)

## Description

C12 and the sprint's proof. Make the build manifest and deploy tooling carry the new files, bring the canonical docs in line with the overlay edits, and build a hex.

## Files

- `pxt.json` and `tools/make_deploy.py`: carry `src/core/position_motor.h` and `src/motion/position_move.h` (and the new test shims if the manifest lists them)
- `src/DESIGN.md` sections 3 (motion engine: `PositionMove`) and 7 (hardware ports: position path, move-live latch, the two speed paths, stop paths hard-stopping live moves); describe the system as it stands, no sprint narration (`docs/design/design.md`, "Subsystem-doc contract: content, not sprint history"). This file could not be seeded into the sprint overlay (its basename collides with `tests/DESIGN.md`), so edit it directly here.
- `README.md`: tick contract states D1 (ticket 009 may already have done this; confirm)
- `tests/host/DESIGN.md`: one paragraph on the extended sim bus and which tests cite the opcode reference
- cite `docs/knowledge/2026-10-27-nezha-brick-opcodes.md` from `src/platform/DESIGN.md` (the overlay copy already does)

## Proof steps (run in order)

1. `env -u VIRTUAL_ENV uv run pytest tests/host tests/tools -q` (full suite green)
2. `env -u VIRTUAL_ENV PXT_FORCE_LOCAL= uv run python tools/make_deploy.py --robot vevov --no-otos` (cloud compiler). The "not all translation units compiled" complaint is expected from the cloud compiler. The hex must land at `.tmp/deploy-head/built/binary.hex`; record its size and `ls -l` line in the ticket.
3. `clasi design validate`. A pre-existing finding exists: `tools/canplay` has no `DESIGN.md`. If it still reports, add a thin `tools/canplay/DESIGN.md` following the other tools subdirectory docs (and the inventory test `tests/tools/test_tools_design_inventory.py`), or report it to the team-lead rather than ignoring it. Diff-file findings for the sprint overlay are generated at sprint close and are not defects here.
4. Confirm `src/core/diffdrive.h` and `src/core/diffdrive.cpp` are byte-identical to the vendored copy (the repo's kernel-sync check, if present, or a checksum against the start of the sprint).
5. Confirm the position-move regression is pinned: a test named for "no `0x60` during a move" exists and passes (`tests/host/test_nezha_port_position_move.py`).

## Acceptance Criteria

- [ ] `test_pxt_manifest_completeness.py` passes with the new files
- [ ] full host + tools suite green
- [ ] a hex exists at `.tmp/deploy-head/built/binary.hex` from the cloud-compile command above
- [ ] `clasi design validate` is clean (or the remaining finding is reported with a reason)
- [ ] `src/DESIGN.md` sections 3 and 7 describe `PositionMove`, the latch, both speed paths and the stop paths, with no sprint history
- [ ] README tick contract states D1
- [ ] kernel files byte-identical; no `0x1D` in `src/` (`grep -rn "0x1D\|03 1D" src/` shows nothing emitted)

## Testing

- **Existing tests to run**: `env -u VIRTUAL_ENV uv run pytest tests/host tests/tools -q`
- **New tests to write**: none beyond the manifest check; this ticket proves the sprint
- **Verification command**: `env -u VIRTUAL_ENV uv run pytest tests/host/test_pxt_manifest_completeness.py -q` then the cloud-compile command above

## Constraints (all tickets)

- Host-only: there is no hardware in this sprint. Nothing here may claim a hardware result.
- Never send brick opcode `0x1D` (motor reset) from firmware, and never put it in the simulator's command table as something the firmware emits.
- `src/core/diffdrive.h` and `src/core/diffdrive.cpp` (the vendored kernel) stay byte-identical. `git diff --stat` / a checksum before and after must show them untouched.
- Any measured claim in a comment, doc or test names its artifact (`.claude/rules/measurement-citations.md`): cite `docs/knowledge/2026-10-27-nezha-brick-opcodes.md` and the CSVs under `docs/code-review/2026-10-27/data/`, never a bare "measured".
- Defaults this sprint: `position_mode` 0, `speed_path` 0.
- Sources: `docs/code-review/2026-10-27/change-plan.md` section 2, `docs/code-review/2026-10-27/motor-path-review.md` (sections 4, 6).
- Design docs for this sprint are in `clasi/sprints/042-*/design/` (overlay); do not edit canonical `DESIGN.md` files except where the ticket says so.
