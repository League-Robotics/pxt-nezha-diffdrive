---
id: '001'
title: Native host test harness scaffold
status: done
use-cases:
- SUC-002
- SUC-003
depends-on: []
github-issue: ''
issue:
- implement-protocol-v6-wire-grammar-and-reliability.md
- implement-motion-api-six-operations.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Native host test harness scaffold

## Description

Stand up the first test suite this repo has ever had: a native host
build of the (already-portable) `DiffDrive::DifferentialDrive` kernel
against fake `Motor`/`Clock`/`Sleeper`/`FiberLauncher` ports, driven
from `pytest` via a `ctypes` shim, following
`radio-robot-lib/tests/protocol/{mock_adapter.h,protocol_shim.cpp}` and
`tools/sim/` as the working reference for shape (sprint.md Architecture
Design Rationale: "ctypes + pytest, matching radio-robot-lib's own
pattern exactly"). This ticket does NOT touch the wire grammar or
motion engine yet — it only proves the host-compile + fake-port +
pytest pipeline works end to end, against code that already exists and
is already portable (`src/diffdrive.h`/`.cpp` depend on nothing but
`<cstdint>` and their own four ports). Every later ticket in this
sprint extends this harness rather than inventing its own scaffolding.

## Acceptance Criteria

- [x] A `FakeMotor` (implementing `DiffDrive::Motor`), `FakeClock`,
      `FakeSleeper`, and a no-op `FakeFiberLauncher` (per
      `diffdrive.md` §2: "a synchronous test harness can decline
      `FiberLauncher`") exist under a new test-scaffolding directory
      and compile against `src/diffdrive.h` with no micro:bit/PXT/CODAL
      header anywhere in the include path.
- [x] `src/diffdrive.cpp` compiles standalone for the host with a
      single, documented `/usr/bin/c++ -std=c++20 ...` command (no
      CMake), mirroring `radio-robot-lib/tools/sim/README.md`'s build
      recipe.
- [x] A thin `extern "C"` shim (mirroring `protocol_shim.cpp`) exposes
      construct/destroy/step/inspect functions a `ctypes` module can
      bind by name.
- [x] `pyproject.toml` is added (or extended) so `uv run pytest` is the
      single command that builds (if needed) and runs the suite from a
      clean checkout.
- [x] One smoke test exists and passes: constructing the kernel over
      `FakeMotor`s, calling `begin()`, then `drive(velocity, twist,
      lease)` followed by `step()`, asserts the `FakeMotor`s received
      the expected staged duty and that `output()` reports the expected
      commanded velocity/twist.
- [x] `pxt.json`'s `files`/`testFiles` arrays are unaffected by this
      ticket (no production `src/` file changes) — confirmed, not
      assumed.
- [x] README or a short doc comment in the harness states the one
      verification command (`uv run pytest`) so later tickets and
      `close_sprint` know what to run.

## Implementation Plan

**Approach**: Build the fake ports first (small, mechanical — each
`DiffDrive::Motor`/`Clock`/`Sleeper` method records/returns a
test-settable value, matching `FakeMotionAdapter`'s spirit of "no
timer, no clock, deterministic, caller-driven"). Then a minimal
`extern "C"` shim bundling one kernel instance + its fake ports behind
opaque handle functions. Then a `pyproject.toml` with `uv`-managed
`pytest`, and a `conftest.py`/helper that compiles the C++ into a
shared library once per test session (mirroring
`test_protocol_harness.py`'s own `_compile_shared_lib` pattern) and
loads it via `ctypes.CDLL`.

**Files to create**:
- `tests/host/fake_ports.h` — `FakeMotor`/`FakeClock`/`FakeSleeper`/
  `FakeFiberLauncher`.
- `tests/host/kernel_shim.cpp` — `extern "C"` surface over
  `DiffDrive::DifferentialDrive` + the fake ports.
- `tests/host/test_kernel_harness.py` — the smoke test plus the
  shared-library-compile helper other tickets' test files will import.
- `pyproject.toml` (repo root) — `uv`/`pytest` dependency declaration.

**Files to modify**: none under `src/`.

**Testing plan**: This ticket's own subject IS the test infrastructure;
its acceptance criteria are self-verifying (`uv run pytest` green from
a clean checkout, no cached build artifacts required).

**Documentation updates**: A short "Testing" section/README note under
`tests/host/` naming the one verification command and what the harness
does and does not cover yet (protocol/motion logic land in later
tickets).

**Testing**

- **Existing tests to run**: none exist yet in this repo.
- **New tests to write**: one smoke test per Acceptance Criteria above.
- **Verification command**: `uv run pytest`
