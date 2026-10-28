---
id: '004'
title: NezhaMotorPort position moves and move-live latch (C2)
status: open
use-cases: ["SUC-001", "SUC-002"]
depends-on: ["002", "003"]
github-issue: ''
issue: position-moves-through-the-motors-own-position-loop.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# NezhaMotorPort position moves and move-live latch (C2)

## Description

C2. `NezhaMotorPort` implements `PositionMotor` (ticket 002). A move-live latch keeps the kernel's per-tick stop enforcement from cancelling the brick's move (review F3), and makes `driven()` true so `commandLooksActive()`, the settle test and the wedge detector keep their meaning (review F6).

## Files

- `src/platform/nezha_port.h`, `src/platform/nezha_port.cpp`
- new host test `tests/host/test_nezha_port_position_move.py` plus shim as needed (use the sim bus from ticket 003)

## Exact behaviour

- `supportsPositionMove()` true; `positionQuantum()` = 10 counts.
- `beginMove(deltaCounts, degPerSec)`: round `deltaCounts` to the quantum; write `0x77 <degPerSec>` for this port only when it differs from the last value written to this port; then `0x70` direction mode 2 with the distance as integer degrees (counts / 10) and the direction byte for the sign. Frame bytes exactly as the table in `docs/knowledge/2026-10-27-nezha-brick-opcodes.md`. Sets the latch.
- `hardStop()`: one `0x5F` frame for this port; clears the latch.
- Latch live: `setDuty()` is a no-op (nothing written, no dither/slew state advanced), `driven()` true, `moveLive()` true. Latch clears on completion (detected from encoder at rest at the target), `hardStop()` or e-stop.
- `emergencyStop()` with the latch live sends `0x5F` first, then `0x60 0`. With the latch not live behaviour is unchanged.
- `appliedDuty()` consumers: `collect()`'s frozen-read hold and wedge detector must treat `driven()` as driven (replace the `|appliedDuty()| > kMotionThreshold` tests at the sites named in review F6, `nezha_port.cpp` near lines 808-837).
- Never emit `0x1D`.

## Acceptance Criteria

- [ ] frames byte-exact against the ticket 001 reference: `0x77` written once per speed change per port (not repeated for an unchanged speed), then `0x70` dir mode 2 with integer degrees
- [ ] zero `0x60` frames on a live port, even when the kernel calls `setDuty(0)` every tick while the wheel reads above rest (the F3 regression, pinned in a named test)
- [ ] `hardStop()` emits exactly one `0x5F` and clears the latch; `emergencyStop()` on a live move emits `0x5F` then `0x60 0`
- [ ] a wedge/frozen-read test shows a frozen counter mid-move is still detected as a wedge
- [ ] with the latch never set, the frame log of the existing tour is byte-identical to before (no regression)

## Testing

- **Existing tests to run**: `env -u VIRTUAL_ENV uv run pytest tests/host/test_board_nezha_diag.py tests/host/test_frozen_encoder_hold.py tests/host/test_creep_self_lock_stiction_sim.py -q`, and `tests/host/sim_tour.py` via its test
- **New tests to write**: `tests/host/test_nezha_port_position_move.py`
- **Verification command**: `env -u VIRTUAL_ENV uv run pytest tests/host/test_nezha_port_position_move.py tests/host/test_sim_nezha_bus_brick_opcodes.py -q`

## Constraints (all tickets)

- Host-only: there is no hardware in this sprint. Nothing here may claim a hardware result.
- Never send brick opcode `0x1D` (motor reset) from firmware, and never put it in the simulator's command table as something the firmware emits.
- `src/core/diffdrive.h` and `src/core/diffdrive.cpp` (the vendored kernel) stay byte-identical. `git diff --stat` / a checksum before and after must show them untouched.
- Any measured claim in a comment, doc or test names its artifact (`.claude/rules/measurement-citations.md`): cite `docs/knowledge/2026-10-27-nezha-brick-opcodes.md` and the CSVs under `docs/code-review/2026-10-27/data/`, never a bare "measured".
- Defaults this sprint: `position_mode` 0, `speed_path` 0.
- Sources: `docs/code-review/2026-10-27/change-plan.md` section 2, `docs/code-review/2026-10-27/motor-path-review.md` (sections 4, 6).
- Design docs for this sprint are in `clasi/sprints/042-*/design/` (overlay); do not edit canonical `DESIGN.md` files except where the ticket says so.
