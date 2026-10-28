---
id: '003'
title: Simulated brick learns the sniffed opcodes (C4)
status: in-progress
use-cases:
- SUC-001
- SUC-004
depends-on:
- '001'
- '002'
github-issue: ''
issue: position-moves-through-the-motors-own-position-loop.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Simulated brick learns the sniffed opcodes (C4)

## Description

C4. Teach the simulated Nezha brick the behaviour recorded in `docs/knowledge/2026-10-27-nezha-brick-opcodes.md` (ticket 001) so ports and the engine can be tested against it.

## Files

- Edit `tests/host/sim_nezha_bus.h`
- Create `tests/host/test_sim_nezha_bus_brick_opcodes.py` (and a small C++ shim next to it if it needs one; follow how `tests/host/sim_robot_shim.cpp` and `tests/host/conftest.py` compile shims)
- Keep every existing `sim_nezha_bus.h` consumer passing (`sim_tour.py`, `sim_robot_shim.cpp`, `test_board_nezha_diag.py`)

## Behaviour to model

- per-port `0x77` store of degrees per second; a `0x77` alone does not retarget a move or a run
- `0x70` mode 0/1 (turns), mode 2 (integer degrees, ramp to the count, quantum 10 counts), mode 3 (timed run at the stored degrees/s for `(10n - 3) x 100 ms`)
- `0x5F`: hold within 5 degrees, target dropped
- `0x60 0` during a move: ramp at v^2/2a and drop the target; nonzero `0x60` takes over the wheel
- a second `0x70` supersedes from the current position
- frame logging so tests can assert exact bytes and count `0x60` frames per port
- do NOT model or accept `0x1D` as something the firmware emits; if the table must name it, it is rejected and logged as a violation the tests can assert is zero

## Acceptance Criteria

- [ ] `test_sim_nezha_bus_brick_opcodes.py` reproduces every row of the ticket 001 reference that has a measured number (7a stop travel ramp vs hard, 7b fine velocity), each assertion citing the doc row and CSV
- [ ] a test asserts `0x77` alone leaves a running wheel and a pending move unchanged
- [ ] a test asserts a second `0x70` supersedes from the current position
- [ ] the simulator counts `0x60` frames per port and exposes a `0x1D` violation counter that stays 0
- [ ] existing sim consumers still pass

## Testing

- **Existing tests to run**: `env -u VIRTUAL_ENV uv run pytest tests/host/test_board_nezha_diag.py tests/host/test_creep_self_lock_stiction_sim.py -q` (plus any test that includes `sim_nezha_bus.h`: `grep -l sim_nezha_bus tests/host/*`)
- **New tests to write**: `tests/host/test_sim_nezha_bus_brick_opcodes.py`
- **Verification command**: `env -u VIRTUAL_ENV uv run pytest tests/host/test_sim_nezha_bus_brick_opcodes.py -q`

## Constraints (all tickets)

- Host-only: there is no hardware in this sprint. Nothing here may claim a hardware result.
- Never send brick opcode `0x1D` (motor reset) from firmware, and never put it in the simulator's command table as something the firmware emits.
- `src/core/diffdrive.h` and `src/core/diffdrive.cpp` (the vendored kernel) stay byte-identical. `git diff --stat` / a checksum before and after must show them untouched.
- Any measured claim in a comment, doc or test names its artifact (`.claude/rules/measurement-citations.md`): cite `docs/knowledge/2026-10-27-nezha-brick-opcodes.md` and the CSVs under `docs/code-review/2026-10-27/data/`, never a bare "measured".
- Defaults this sprint: `position_mode` 0, `speed_path` 0.
- Sources: `docs/code-review/2026-10-27/change-plan.md` section 2, `docs/code-review/2026-10-27/motor-path-review.md` (sections 4, 6).
- Design docs for this sprint are in `clasi/sprints/042-*/design/` (overlay); do not edit canonical `DESIGN.md` files except where the ticket says so.
