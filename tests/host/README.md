# tests/host — native host test harness

This repo's first test suite. It compiles this extension's portable C++
(starting with `src/diffdrive.h`/`.cpp`) for the host — no micro:bit, no
PXT/CODAL, no MakeCode toolchain — against fake ports, and drives it from
`pytest` via a thin `extern "C"` shim bound through `ctypes`. Modeled on
`radio-robot-lib/tests/protocol/{mock_adapter.h,protocol_shim.cpp}` and
`radio-robot-lib/tools/sim/README.md`'s build recipe.

## Run it

```
uv run pytest
```

That's the one command: it builds the shared library (if needed) and
runs every test, from a clean checkout, with nothing installed globally.
Scope to just this file with `uv run pytest tests/host/test_kernel_harness.py`.

## What's here

- `fake_ports.h` — `FakeMotor`/`FakeClock`/`FakeSleeper`/
  `FakeFiberLauncher`, implementing `DiffDrive::Motor`/`Clock`/`Sleeper`/
  `FiberLauncher` (`src/diffdrive.h`) as plain, caller-driven test
  doubles: no timer, no clock, no simulated physics — a test arms
  exactly the value each method should return, then calls
  `DifferentialDrive::step()` to advance by one cycle. Honors the two
  sharp `Motor` semantics called out in
  `radio-robot-lib/docs/design/diffdrive.md` §2.1: `sampleTime()` stamps
  only on a successful collect, and `rebaseline()` issues no bus
  traffic. `FakeFiberLauncher` is a true no-op — this harness drives the
  kernel by calling `step()` directly and never calls `start()`, per
  `diffdrive.md` §2's "a synchronous test harness can decline
  `FiberLauncher`".
- `kernel_shim.cpp` — the `extern "C"` surface: one opaque handle
  bundling a `DiffDrive::DifferentialDrive` with its own private
  `FakeMotor` x2/`FakeClock`/`FakeSleeper`/`FakeFiberLauncher`, plus free
  functions a `ctypes` module binds by name (construct/destroy, config
  setters, commands, `Output` readback, fake-port control/readback).
  Extend this file's function list — don't invent a second shim — when a
  later ticket needs another `DifferentialDrive` knob exposed.
- `test_kernel_harness.py` — the compile helper (`compile_shared_lib()`,
  reusable by later tickets' own test files against their own source
  lists) and this ticket's tests, including the required smoke test:
  construct the kernel over `FakeMotor`s, `begin()`, `drive(velocity,
  twist, lease)`, `step()`, and confirm the motors received the expected
  staged duty and `output()` reports the expected commanded
  velocity/twist.

## What this does NOT cover yet

Protocol v6 wire grammar and the six-operation Motion API land in later
sprint 003 tickets (`wire_handler`/`wire_adapter`/`motion_engine`, none
of which exist yet) — each extends this harness (mainly `fake_ports.h`,
and `compile_shared_lib()`'s pattern for its own shim) rather than
building its own scaffolding from scratch.

## Build recipe, spelled out

The single command `compile_shared_lib()` runs under the hood, for
reference (mirrors `radio-robot-lib/tools/sim/README.md`'s own
"no CMake" recipe):

```bash
/usr/bin/c++ -std=c++20 -Wall -Wextra -shared -fPIC \
  -I src -I tests/host \
  src/diffdrive.cpp tests/host/kernel_shim.cpp \
  -o /tmp/libkernel_shim.so
```
