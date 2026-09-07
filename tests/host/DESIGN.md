# tests/host — native host test harness

**Owner:** Eric Busboom · **Last reviewed:** 2026-09-06 · **Status:**
stable. The motion-engine shim is compiled once per session in
`conftest.py` (§2); which translation units this harness can and cannot
reach is enumerated in `tests/DESIGN.md` and enforced by
`test_pxt_bound_exclusion_is_current.py` (§6).

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
  `odometry_shim.cpp`, `run_queue_shim.cpp`, `run_bridge_shim.cpp`,
  `wire_grammar_shim.cpp`, `wire_motion_verb_shim.cpp`) — the
  `extern "C"` surfaces ctypes can bind: each bundles the class under
  test with its private fakes behind an opaque handle plus free
  functions. `run_bridge_shim.cpp` (sprint 033) exposes
  `diffDrive::RunBridge` — the `RUN` bridge's sanitize/
  dedupe/park/bypass rules, extracted out of the `pxt.h`-bound
  `protocol.cpp` and therefore executable here for the first time.
  Its clock is an `offer()` argument rather than a member, which is
  what lets `test_run_bridge.py` land timestamps exactly on the dedupe
  window's edges instead of sleeping. `odometry_shim.cpp` (sprint 033)
  bundles a real
  `diffDrive::Odometry` over a real `MotionEngine`/kernel and
  synthesizes the kernel `Output`s it integrates, so
  `test_odometry.py` can script an exact wheel-count path with no
  encoder, clock or control loop in the link — the first host coverage
  of the dead-reckoning math, which lived in `shims.cpp` (`pxt.h`-bound,
  unlinkable here) until `Odometry` made it portable.
  `transport_sink_shim.cpp` (sprint 033) exposes
  `diffDrive::TransportSink` and the `wireLineContentLength()` decision
  behind it — the outbound half of the same kind of extraction: three
  hand-copied `Wire::Sink` subclasses inside the `pxt.h`-bound
  `protocol.cpp` became one class in a header with no CODAL dependency,
  so `test_transport_sink.py` can drive the real sink, through the real
  `Wire::Sink&` the wire stack holds, over a recording fake transport.
  The transports those sinks write to are still out of reach here.
  `radio_transport_rx_capacity_shim.cpp` follows the same rule on the
  inbound side: `radioRxLineFits()` and, since sprint 033,
  `radioRxClassify()` over an accumulating `RadioRxCounters` — the RX
  path's whole accept/drop decision and its four counters, which have
  no CODAL in them even though their one call site (`onDatagram()`)
  cannot be compiled here at all.
  `wire_motion_verb_shim.cpp` carries two handles:
  `WvHandle` (WireHandler + mock adapter — decode/dispatch mechanics)
  and `WaHandle` (WireHandler + the **real** `WireAdapter` + a
  **real** kernel over FakeMotors — end-to-end verb effect), and
  supplies its own test-double definitions of the `shims.cpp` free
  functions `wire_adapter.cpp` forward-declares, mirroring the
  production math field-for-field. `getConfigValue`/`setKernelValue`
  fix counts-per-mm at 1.0 (no wire ordinal they reach needs real
  geometry); **sprint 008** ends that shortcut for `setWheelsTimed`
  specifically, below. Since sprint 033 ticket 003 those two doubles
  mirror production's SHAPE as well as its math — one
  `kWaConfigAccessors` row per ordinal, against production's
  `kConfigAccessors` — and `test_config_surface_single_source.py`
  fails if the two tables cover different ordinals. That matters more
  here than symmetry usually does: every compiled `SET`/`GET` test in
  this directory runs against the double, so a double covering a
  different surface than the robot means those tests pass while
  describing a machine that does not exist. The wire NAMES are not
  doubled at all — the real `comms/config_fields.h` is compiled in
  through the real `wire_adapter.cpp`. `WaHandle`'s DIAG double is re-synced to read
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
  `static_cast<int>(v * 1000.0f)`, matching what production actually
  does.
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
- **`conftest.py`** (sprint 034 ticket 010) — the ONE place the
  motion-engine shim is compiled. Thirteen files here drive the same
  four translation units behind the same `meCreate()` handle, and each
  used to carry its own copy of the source list, its own `_bind()` and
  its own session-scoped `motion_lib` fixture with its own `out_name` —
  so the identical compile ran thirteen times a session, and one source
  list existed in thirteen places to drift. `conftest.py` now holds
  `MOTION_SHIM_SOURCES`, a `_bind_motion_lib()` that is the union of
  those thirteen binders (70 symbols; no two files had disagreed about
  a signature), and the `motion_lib` fixture they all take by name.
  MEASURED 2026-09-06, `uv run pytest tests/host tests/tools -q`:
  75.30 s before (1719 passed), 57.88 s / 58.47 s after (1722 passed --
  three new tests this ticket adds). The remainder of the run is not the
  compile: `tests/tools` alone takes ~28 s on its own, unchanged by this. Consequence: those
  files share ONE `ctypes.CDLL` object now, so a binder applied at call
  time (`test_segment_lazy_origin.py`'s `_bind_rebase()`) mutates shared
  state and must stay signature-compatible with the union. This is not a
  general "fixtures go in conftest" policy — the kernel, wire and
  run-queue shims are different source lists with one owner file each,
  and they stay where they are.

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
- **`motion_lib`** (`conftest.py`) — the compiled-once, fully bound
  motion-engine shim, available by name to every test file in this
  directory.
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

Not covered, by design (CODAL-bound) — the canonical list, per file,
with what gates each one instead, is `tests/DESIGN.md` "Translation
units nothing on the host compiles", held against the tree by
`test_pxt_bound_exclusion_is_current.py`. In summary: `nezha_port`, `otos_port`, the
transports, `protocol.cpp`'s fiber loop and RUN bridge, and
`shims.cpp`'s real Rig composition/watchdog — hardware sessions are
their only test. Where a decision inside one of those has been pulled
into a header with no CODAL in it, the decision IS covered and only
its wiring is not: `radioRxClassify()`'s dispositions and counters are
host-tested while the `onDatagram()` call and the diag ordinals
surfacing them are review-verified, and `Protocol::serviceOnce()`'s
per-pass RX drain bound is pinned as source text
(`test_wire_constants_drift.py`) rather than executed. Text pins are
weaker than execution and are used only where execution is impossible
— they catch a renumbered ordinal or a second spelling of a bounded
loop, not a behavioural regression. **Narrower again as of sprint 033**: the odometry
*math* left `shims.cpp` for `motion/odometry.h` and is now host-tested
directly (`test_odometry.py`); what stays hardware-only is the real
encoder stream feeding it — `shims.cpp`'s `odomUpdate(r)` is now a
one-line `kernel.output()` fetch. **Narrower than before sprint 008**:
`tickDrive()`'s post-move settle loop is no longer entirely
hardware-only — its bounded-iteration/break-on-rest *decision* is now a
`MotionEngine` method, host-tested directly; what remained hardware-only
after that sprint was `odomUpdate(r)`'s actual encoder-driven pose fold
and the loop's real `kernel.step()` calls against physical motors (see
`src/DESIGN.md` §9 for the exact boundary that extraction drew; sprint
033 moved the pose fold itself into `Odometry`, leaving only the real
encoder stream and the real `step()` calls).

**Target-viability reminder (sprint 008).** Every test in this
directory, including everything this sprint adds, still only proves
`-std=c++20` compilation for the four portable translation units (plus
the `-std=c++11 -fsyntax-only` gate's narrower syntax check over the
same four files and their extracted-header siblings — none added by
this sprint, since the settle helper landed on an already-covered
file). None of it is evidence that `protocol.cpp`, `radio_transport.h`,
or `shims.cpp`'s changed call site actually link for either real
target — that is what this sprint's own mandatory build-checkpoint
ticket proves instead (see `src/DESIGN.md` §11 and
`docs/design/design.md`'s matching convention). This directory's own
tests and a real target build are complementary, not substitutes for
each other, and this sprint is the one that made that relationship a
named, standing practice rather than an implicit assumption.

Known nit: this directory's `README.md` "What this does NOT cover
yet" section predates sprint 003's later tickets — the wire and
motion-engine modules it says "don't exist yet" exist and are covered
above.
