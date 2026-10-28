---
id: '002'
title: PositionMotor port interface (C1)
status: done
use-cases:
- SUC-001
depends-on:
- '001'
github-issue: ''
issue: position-moves-through-the-motors-own-position-loop.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# PositionMotor port interface (C1)

## Description

C1. Add the position-move port seam in `core/`, libc only, beside `DiffDrive::Motor`. The kernel does not include it.

## Files

- Create `src/core/position_motor.h` (namespace `DiffDrive`, class `PositionMotor`, pure virtual, C++11 only)
- Edit `pxt.json` to list it (see `tests/host/test_pxt_manifest_completeness.py` for how files are checked)
- Create `tests/host/position_motor_syntax_check.cpp` and a test in the style of the existing `*_syntax_check.cpp` files (e.g. `tests/host/test_cxx11_syntax_gate.py`, `heading_wrap_syntax_check.cpp`) so the header is compiled with the C++11 gate

## Interface

```
class PositionMotor {
 public:
  virtual ~PositionMotor() {}
  virtual bool  supportsPositionMove() const = 0;
  virtual float positionQuantum() const = 0;                 // counts; 10 on the brick
  virtual bool  beginMove(float deltaCounts, float degPerSec) = 0;  // relative; returns false if refused
  virtual bool  hardStop() = 0;                              // brick 0x5F
  virtual bool  moveLive() const = 0;
  virtual bool  driven() const = 0;                          // wheel driven by either path
};
```

`beginMove` takes the signed relative target in counts and the speed in degrees per second (the review's earlier `speedFraction` is replaced by the plan's `degPerSec`). Document, in the header comment, that the port rounds `deltaCounts` to the quantum and the caller reads the rounded value back through a second method you add if the engine needs it (ticket 006 splits rounding across wheels): add `float lastMoveCounts() const` returning the delta actually commanded. The kernel and `core/diffdrive.*` must not include this header.

## Acceptance Criteria

- [x] `src/core/position_motor.h` compiles under the project's C++11 syntax gate with libc only (no `pxt.h`, no I2C)
- [x] header listed in `pxt.json`; `test_pxt_manifest_completeness.py` passes
- [x] `src/core/diffdrive.h` / `diffdrive.cpp` byte-identical (checksum before/after)
- [x] no file under `src/core/` other than the new header changes

## Testing

- **Existing tests to run**: `env -u VIRTUAL_ENV uv run pytest tests/host/test_cxx11_syntax_gate.py tests/host/test_pxt_manifest_completeness.py -q`
- **New tests to write**: a syntax-check translation unit for `position_motor.h` wired into the C++11 gate
- **Verification command**: `env -u VIRTUAL_ENV uv run pytest tests/host/test_cxx11_syntax_gate.py tests/host/test_pxt_manifest_completeness.py -q`

## Constraints (all tickets)

- Host-only: there is no hardware in this sprint. Nothing here may claim a hardware result.
- Never send brick opcode `0x1D` (motor reset) from firmware, and never put it in the simulator's command table as something the firmware emits.
- `src/core/diffdrive.h` and `src/core/diffdrive.cpp` (the vendored kernel) stay byte-identical. `git diff --stat` / a checksum before and after must show them untouched.
- Any measured claim in a comment, doc or test names its artifact (`.claude/rules/measurement-citations.md`): cite `docs/knowledge/2026-10-27-nezha-brick-opcodes.md` and the CSVs under `docs/code-review/2026-10-27/data/`, never a bare "measured".
- Defaults this sprint: `position_mode` 0, `speed_path` 0.
- Sources: `docs/code-review/2026-10-27/change-plan.md` section 2, `docs/code-review/2026-10-27/motor-path-review.md` (sections 4, 6).
- Design docs for this sprint are in `clasi/sprints/042-*/design/` (overlay); do not edit canonical `DESIGN.md` files except where the ticket says so.
