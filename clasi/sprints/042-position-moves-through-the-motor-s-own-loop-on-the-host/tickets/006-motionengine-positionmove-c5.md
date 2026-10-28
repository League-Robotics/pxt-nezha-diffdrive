---
id: '006'
title: MotionEngine PositionMove (C5)
status: open
use-cases: ["SUC-001"]
depends-on: ["004"]
github-issue: ''
issue: position-moves-through-the-motors-own-position-loop.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# MotionEngine PositionMove (C5)

## Description

C5. `MotionEngine::PositionMove`: a fourth in-flight command beside `Segment`, `Hold` and `Nudge`. Exactly one of `seg_`/`hold_`/`nudge_`/`posMove_` is live.

## Files

- `src/motion/motion_engine.h`, `src/motion/motion_engine.cpp`; create `src/motion/position_move.h`
- a port accessor: the engine reaches the ports through `PositionMotor*` pointers set at composition (add `setPositionMotors(PositionMotor* left, PositionMotor* right)`; null means unsupported)
- `tests/host/motion_engine_shim.cpp` and `tests/host/conftest.py` (add `extern "C"` entry points and bind them; keep `MOTION_SHIM_SOURCES` the single source list; use `tests/host/fake_ports.h` to add a fake `PositionMotor` or the sim-bus port)
- new test `tests/host/test_motion_engine_position_move.py`

## Exact behaviour

- Plan from the existing segment maths (`rotationalSlip`, `effectiveTrackWidth`, `countsPerMm()`): per-wheel count targets; round each to `positionQuantum()` (10 counts), splitting rounding across the two wheels in opposite directions so heading error stays under half a step.
- per-wheel degrees/second proportional to each wheel's share of the dominant distance (so an arc's two moves finish together), capped by the cruise limit; two `beginMove()` calls back to back.
- service: keep `kernel_.step()` for encoder reads and odometry, stage no wheel commands; completion = both wheels within `arriveDist`/`arriveYaw` and `atRest()`.
- deadline, e-stop, cancel and a stall test (no progress for `stallWindow` while a move is live) end it with `hardStop()` on both.
- `isDriving()` true while live. Nothing here selects the mode: ticket 008 does the routing.

## Acceptance Criteria

- [ ] 50 cm straight, 90 degree pivot and a 300 mm / 45 degree arc on the sim bus land within one quantum of target
- [ ] cancel, e-stop and deadline each produce `0x5F` on both ports within one tick
- [ ] a stall (target unreachable, wheel pinned) ends with `hardStop()` after `stallWindow`
- [ ] arc: the two wheels' moves finish within one tick of each other
- [ ] exactly one of seg_/hold_/nudge_/posMove_ live (starting one cancels the others)
- [ ] kernel files byte-identical; no `0x60` frame while live

## Testing

- **Existing tests to run**: `env -u VIRTUAL_ENV uv run pytest tests/host/test_motion_engine_estop_and_refusal.py tests/host/test_motion_engine_nudge.py tests/host/test_velocity_shaper.py tests/host/test_cross_fiber_stop_settle_window.py -q`
- **New tests to write**: `tests/host/test_motion_engine_position_move.py`
- **Verification command**: `env -u VIRTUAL_ENV uv run pytest tests/host/test_motion_engine_position_move.py -q`

## Constraints (all tickets)

- Host-only: there is no hardware in this sprint. Nothing here may claim a hardware result.
- Never send brick opcode `0x1D` (motor reset) from firmware, and never put it in the simulator's command table as something the firmware emits.
- `src/core/diffdrive.h` and `src/core/diffdrive.cpp` (the vendored kernel) stay byte-identical. `git diff --stat` / a checksum before and after must show them untouched.
- Any measured claim in a comment, doc or test names its artifact (`.claude/rules/measurement-citations.md`): cite `docs/knowledge/2026-10-27-nezha-brick-opcodes.md` and the CSVs under `docs/code-review/2026-10-27/data/`, never a bare "measured".
- Defaults this sprint: `position_mode` 0, `speed_path` 0.
- Sources: `docs/code-review/2026-10-27/change-plan.md` section 2, `docs/code-review/2026-10-27/motor-path-review.md` (sections 4, 6).
- Design docs for this sprint are in `clasi/sprints/042-*/design/` (overlay); do not edit canonical `DESIGN.md` files except where the ticket says so.
