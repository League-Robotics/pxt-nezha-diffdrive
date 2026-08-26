# tests/host — native host test harness

**Owner:** Eric Busboom · **Last reviewed:** 2026-08-24 · **Status:** stable
(as of sprint 008: boundary-value timeout coverage for all six motion
verbs, `kVersion`/`RUN_EVENT_SOURCE` drift tests, the `WaHandle`
wedge/`setWheelsTimed`/config-rounding re-sync plus its own drift test,
a new settle-loop shim, and `TLM AUTO`/`BUFFER` pinning tests)

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
  production math field-for-field. `getConfigValue`/`setKernelValue`
  fix counts-per-mm at 1.0 (no wire ordinal they reach needs real
  geometry); **sprint 008** ends that shortcut for `setWheelsTimed`
  specifically, below. `WaHandle`'s DIAG double is re-synced to read
  `wedgeSuspectLeft/Right` (matching production's `diagValue()`, not
  the double's previous, different `wedgeLeft/Right` substitution —
  both field pairs exist on the kernel's `Output` struct and mean
  different things); its `setWheelsTimed` double now calls the SAME
  real `MotionEngine::wheelsV()` `engineWheelsX()`/`engineMoveX()`
  already use, not merely a hand-rolled sequence that reaches
  `cancelMove()` — so it also now applies the REAL `countsPerMm()`
  scaling those two already do, ending "fixed at 1.0" for this verb
  too. This changed the MEANING of the pre-existing `WHEELS_V`
  real-effect duty tests (`test_wire_motion_verbs.py`): their expected
  numbers had modeled an uncalibrated 1:1 mm/s->counts/s robot that
  does not exist, passing while describing that robot; both were
  updated to read the handle's own real `waCountsPerMm()`, the same
  way the `WHEELS_X`/`MOVE_X` tests already do, not merely re-tuned to
  keep passing. And its config-rounding double matches
  `std::lround(v * 1000.0)` instead of a truncating
  `static_cast<int>(v * 1000.0f)` — see `src/DESIGN.md`'s own §14 for
  why each was wrong and what production actually does.
  `motion_engine_shim.cpp` (or `kernel_shim.cpp`, whichever the
  extraction ticket judges the better home — the settle helper needs
  only `kernel.step()`/`kernel.output()`, already exposed by
  `kernel_shim.cpp`'s existing `Handle`) gains the new settle-loop
  helper's own handle-plus-free-functions surface, reusing
  `FakeSleeper::onSleep` (`fake_ports.h`) where a test needs to observe
  how many `sleepMillis()` calls the helper's iterations produced.
- **Tests** (`test_*.py`) — each builds its shared library through
  `compile_shared_lib()` (defined in `test_kernel_harness.py`,
  reused by every later suite: same compiler invocation, no CMake)
  and asserts through the handle.

Run: `uv run pytest` from the repo root. Modeled on
radio-robot-lib's `tests/protocol` harness.

## 3. Constraints and Invariants

- **Only portable sources compile here.** A shim's source list may
  include `src/core/diffdrive.cpp`, `motion/motion_engine.cpp`,
  `comms/wire_handler.cpp`, `comms/wire_adapter.cpp` — never a `pxt.h`-including
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
(`test_wire_motion_verbs.py`). **Sprint 008** adds: boundary-value
timeout/duration coverage (`0`, `2^31−1`, `2^31`, uint32-max) across
all six motion verbs; a `kVersion`/`pxt.json` drift test and an
`emitLine`/transport line-cap test; a `RUN_EVENT_SOURCE` cross-language
drift test; a `WaHandle` drift test for the three re-synced doubles
(wedge fields, `setWheelsTimed`/`cancelMove()`, config rounding),
demonstrated to fail when only one side changes; the extracted
settle-loop helper's bounded-iteration/break-on-rest behavior, exercised
directly through its own new shim (not merely argued for by
`test_regression_post_move_neutral.py`, which stays as the "why this
matters" test); and `TLM AUTO`/`BUFFER` `thdr`/`err` pinning.

Not covered, by design (CODAL-bound): `nezha_port`, `otos_port`, the
transports, `protocol.cpp`'s fiber loop and RUN bridge, and
`shims.cpp`'s real Rig composition/odometry/watchdog — hardware
sessions are their only test. **Narrower than before sprint 008**:
`tickDrive()`'s post-move settle loop is no longer entirely
hardware-only — its bounded-iteration/break-on-rest *decision* is now a
`MotionEngine` method, host-tested directly; what remains hardware-only
is `odomUpdate(r)`'s actual encoder-driven pose fold and the loop's
real `kernel.step()` calls against physical motors, which stay in
`shims.cpp` unmoved (see `src/DESIGN.md` §9/§14 for the exact boundary
this extraction drew).

**Target-viability reminder (sprint 008).** Every test in this
directory, including everything this sprint adds, still only proves
`-std=c++20` compilation for the four portable translation units (plus
the `-std=c++11 -fsyntax-only` gate's narrower syntax check over the
same four files and their extracted-header siblings — none added by
this sprint, since the settle helper landed on an already-covered
file). None of it is evidence that `protocol.cpp`, `radio_transport.h`,
or `shims.cpp`'s changed call site actually link for either real
target — that is what this sprint's own mandatory build-checkpoint
ticket proves instead (see `src/DESIGN.md` §11/§14 and
`docs/design/design.md`'s matching convention). This directory's own
tests and a real target build are complementary, not substitutes for
each other, and this sprint is the one that made that relationship a
named, standing practice rather than an implicit assumption.

Known nit: this directory's `README.md` "What this does NOT cover
yet" section predates sprint 003's later tickets — the wire and
motion-engine modules it says "don't exist yet" exist and are covered
above.
