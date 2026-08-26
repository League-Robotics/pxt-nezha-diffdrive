# tests/host — native host test harness

It compiles this extension's portable C++ (starting with
`src/core/diffdrive.h`/`.cpp`) for the host — no micro:bit, no PXT/CODAL, no
MakeCode toolchain — against fake ports, and drives it from `pytest`
via a thin `extern "C"` shim bound through `ctypes`. Modeled on
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

Roughly one shim (`*_shim.cpp`) plus one test file (`test_*.py`) per
subsystem — see each file's own header comment for what it covers.
`fake_ports.h` (`FakeMotor`/`FakeClock`/`FakeSleeper`/
`FakeFiberLauncher`) and `fake_pose_source.h` (`FakePoseSource`) are the
shared test doubles most shims build on; `golden_telemetry.py` is a
shared fixture two telemetry-frame test files import so the emitter and
its (future) parser can't drift apart; `DESIGN.md` is this directory's
own design notes (shim shape, naming conventions, the C++11 syntax-gate
pattern). A single shim is often reused by several `test_*.py` files
(e.g. `wire_grammar_shim.cpp` backs the grammar, reliability,
per-transport-isolation, and telemetry-frame tests) rather than each
test file inventing its own build — extend an existing shim's function
list before adding a new one.

`tests/tools/` is a sibling suite testing `tools/*.py` directly in
plain Python — no compiler, no subprocess, no network. See its own
`tests/tools/DESIGN.md`.

## What this does NOT cover yet

- **CODAL-bound code**: `shims.cpp`'s `tickDrive()` — its own
  fiber-concurrency guard, its `odomUpdate()` call into Rig-local
  x/y/heading, and its starvation watchdog — plus `protocol.cpp`'s
  CODAL protocol fiber and the transport layer
  (`serial_transport`/`radio_transport`). All of these include `pxt.h`
  and cannot be compiled for the host at all. (The settle-then-neutral
  DECISION `tickDrive()` used to make inline is a different story: it's
  been extracted into `MotionEngine::settleToRest()`, which *is*
  host-portable and *is* covered, by `test_motion_engine_settle.py`.)
- **PXT/simulator behavior** (`src/*.ts`, `test/test.ts`,
  `test/testrig.ts`) — a separate MakeCode-side test surface, not this
  one.
- **Target buildability, beyond language standard and manifest
  completeness.** This directory compiles at `-std=c++20`; both real
  embedded targets compile at `-std=c++11` — a gap that once shipped
  firmware which passed 253 host tests and could not be compiled for a
  robot at all. `test_cxx11_syntax_gate.py` closes only the
  language-standard half (syntax-checks host-portable files at
  `-std=c++11`); `test_pxt_manifest_completeness.py` closes the
  manifest half (every `src/*.h`/`*.cpp` is actually listed in
  `pxt.json`'s `files`). Neither one, nor anything else here, actually
  builds the target — only a real build proves target viability.

## Build recipe, spelled out

The single command `compile_shared_lib()` runs under the hood, for
reference (mirrors `radio-robot-lib/tools/sim/README.md`'s own
"no CMake" recipe):

```bash
/usr/bin/c++ -std=c++20 -Wall -Wextra -shared -fPIC \
  -I src -I tests/host \
  src/core/diffdrive.cpp tests/host/kernel_shim.cpp \
  -o /tmp/libkernel_shim.so
```
