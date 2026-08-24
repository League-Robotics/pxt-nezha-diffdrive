# tests/host — native host test harness

**Owner:** Eric Busboom · **Last reviewed:** 2026-08-23 · **Status:** stable

---

## 1. Purpose

The repo's only assertion-based test suite. It compiles the
extension's *portable* firmware C++ — the kernel, the motion engine,
the v6 wire grammar, and the wire adapter — for the desktop with the
plain system compiler, and drives it from pytest through thin
`extern "C"` shims bound with `ctypes`. The seam that justifies the
boundary: everything under `src/` that is host-portable by
construction (no `pxt.h`, no CODAL) gets tested *here*, with no
micro:bit, no PXT toolchain, and no hardware in the link; everything
CODAL-bound gets tested only by flashing a robot. This directory owns
the fakes, the shims, the compile recipe, and the tests — nothing
under `src/` knows it exists.

## 2. Orientation

Three kinds of file, one pattern:

- **Fakes** (`fake_ports.h`, `fake_pose_source.h`,
  `wire_mock_adapter.h`) — caller-driven test doubles for the
  firmware's own port seams: `FakeMotor`/`FakeClock`/`FakeSleeper`/
  `FakeFiberLauncher` for the kernel's four ports, `FakePoseSource`
  for `goToW()`, `WireMockAdapter` (a recording double) for
  `Wire::Adapter`. No timers, no simulated physics: a test arms
  exactly what each port method should report, then advances the code
  under test one step at a time.
- **Shims** (`kernel_shim.cpp`, `motion_engine_shim.cpp`,
  `wire_grammar_shim.cpp`, `wire_motion_verb_shim.cpp`) — the
  `extern "C"` surfaces ctypes can bind: each bundles the class under
  test with its private fakes behind an opaque handle plus free
  functions. `wire_motion_verb_shim.cpp` carries two handles:
  `WvHandle` (WireHandler + mock adapter — decode/dispatch mechanics)
  and `WaHandle` (WireHandler + the **real** `WireAdapter` + a
  **real** kernel over FakeMotors — end-to-end verb effect), and
  supplies its own test-double definitions of the `shims.cpp` free
  functions `wire_adapter.cpp` forward-declares, mirroring the
  production math field-for-field with counts-per-mm fixed at 1.0.
- **Tests** (`test_*.py`) — each builds its shared library through
  `compile_shared_lib()` (defined in `test_kernel_harness.py`,
  reused by every later suite: same compiler invocation, no CMake)
  and asserts through the handle.

Run: `uv run pytest` from the repo root. Modeled on
radio-robot-lib's `tests/protocol` harness.

## 3. Constraints and Invariants

- **Only portable sources compile here.** A shim's source list may
  include `src/diffdrive.cpp`, `motion_engine.cpp`,
  `wire_handler.cpp`, `wire_adapter.cpp` — never a `pxt.h`-including
  file. If a link fails because a "portable" file grew a CODAL
  dependency, the *file* is wrong, not the harness: this suite is the
  enforcement mechanism for `src/DESIGN.md` §1's layering table.
- **Drive `step()`, never `start()`.** `FakeFiberLauncher` is a true
  no-op; the kernel is advanced synchronously one cycle at a time. A
  test that "waits" for a fiber will hang forever by design.
- **Fakes stay caller-driven.** `FakeMotor` honors the two sharp
  `Motor` semantics: `sampleTime()` stamps only on a successful
  collect (that's how `i2cFaultCount_` paths are exercised) and
  `rebaseline()` issues no bus traffic. Adding a clock or physics to
  a fake breaks the determinism every existing test assumes.
- **One `WaHandle` at a time, single-threaded.** The test-double
  `shims.cpp` functions take no handle (they must match the
  production signatures exactly), so they route through one
  process-wide active-handle pointer armed by `waCreate()`. Safe only
  under pytest's default serial execution — never drive two
  `WaHandle`s from separate threads, and never add xdist parallelism
  to this repo's test config without fixing this first.
- **Extend the existing shims; don't invent parallel scaffolding.** A
  new knob gets a new free function on the matching existing shim; a
  new module gets its own shim only when it has its own class under
  test.
- **Sign-convention tests are load-bearing.**
  `test_motion_engine_primitives.py` pins CCW-positive explicitly so
  a future cable-order "fix" fails a test instead of shipping (this
  project has shipped that bug and patched it downstream four times).
  Do not "simplify" them to magnitude checks.

## 4. Design

The compile step (`compile_shared_lib()`) invokes
`c++ -std=c++20 -Wall -Wextra -shared -fPIC -I src -I tests/host
<sources> -o <tmpdir>/lib*.so` into a pytest tmpdir, once per source
list, cached by pytest fixtures. ctypes cannot call C++ methods, so
every shim is handle-plus-free-functions; reply bytes are captured by
a `RecordingSink` accumulating every `Sink::write()` for the Python
side to slice on `\n`. The `WaHandle` design deliberately reuses the
production forward-declaration seam as the test seam: because
`wire_adapter.cpp` reaches hardware only through free functions, the
harness substitutes a FakeMotor-backed kernel by *linking different
definitions*, not by mocking — the same trick production uses to keep
`wire_adapter.cpp` and `shims.cpp` decoupled. `waNowMs()` wires a
real (fake-clock-backed) `NowMsFn` into the adapter, which is what
made the motion-obligation arming bug observable from a test.

## 5. Interfaces

### Exposes
- **`uv run pytest`** — the whole suite from a clean checkout;
  scope with a path (`uv run pytest tests/host/test_wire_grammar.py`).
  Also the once-per-sprint gate `close_sprint` runs.
- **`compile_shared_lib(tmp_path_factory, sources, include_dirs,
  out_name)`** — the reusable build helper for any future suite.

### Consumes
- **`src/` portable modules** (`diffdrive.*`, `motion_engine.*`,
  `wire_handler.*`, `wire_adapter.*`): compiled directly from source —
  see [`src/DESIGN.md`](../../src/DESIGN.md) for their contracts.

## 6. Coverage — what is and is not tested here

Covered: kernel harness smoke + fault paths
(`test_kernel_harness.py`); the two primitives and their sign
conventions (`test_motion_engine_primitives.py`); the move-engine
reductions, taper/ramp/wrong-way (`test_motion_engine_reductions.py`);
`goToW` world→body math (`test_motion_engine_gotow.py`); two pinned
regressions — post-move neutral delivery shape and the pure-turn yaw
taper (`test_regression_*.py`); the v6 grammar mechanics, golden
vectors, and malformed-input behavior (`test_wire_grammar.py`); the
reliability layer (`test_wire_reliability.py`); and all six motion
verbs end-to-end through the real `WireAdapter`
(`test_wire_motion_verbs.py`).

Not covered, by design (CODAL-bound): `nezha_port`, `otos_port`, the
transports, `protocol.cpp`'s fiber loop and RUN bridge, `shims.cpp`'s
real Rig composition/odometry/watchdog, and `tickDrive()`'s post-move
settle loop — hardware sessions are their only test.

Known nit: this directory's `README.md` "What this does NOT cover
yet" section predates sprint 003's later tickets — the wire and
motion-engine modules it says "don't exist yet" exist and are covered
above.
