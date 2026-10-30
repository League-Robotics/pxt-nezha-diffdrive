# tests — Python-run test root

**Owner:** Eric Busboom · **Last reviewed:** 2026-09-06 · **Status:** stable

Every test in this tree lives in a subdirectory named for its **type**,
and the type answers one question: *what does it need, and does CI run
it?*

| directory | needs | run by `uv run pytest` | lifetime |
|---|---|---|---|
| [`host/`](host/DESIGN.md) | a C++ compiler | yes | permanent |
| [`tools/`](tools/DESIGN.md) | nothing (bar the lint gate's `ruff`) | yes | permanent |
| [`calibration/`](calibration/DESIGN.md) | a robot, the playfield and its camera | its **programs** no; its two pure-logic unit tests yes | permanent |
| [`system/`](system/DESIGN.md) | a real robot | **no** — run by hand | permanent |
| [`dev/`](dev/DESIGN.md) | a real robot | **no** | disposable |

The mechanism is the `test_` prefix, not a directory list:
`pyproject.toml` sets `testpaths = ["tests"]`, so `uv run pytest`
descends the whole tree and collects whatever is named like a test.
`system/`, `dev/` and every measurement program in `calibration/` are
named for what they do (`run_tour.py`, `turn_calibration.py`,
`closure.py`, `consolidation_acceptance.py`), so nothing collects them
— they need hardware that is not present in a clean checkout, and a
suite that cannot run everywhere is not a suite.
`calibration/test_turn_calibration_gates.py` and
`calibration/test_consolidation_acceptance.py` are the two exceptions
and both are deliberate: the pass/fail logic of a gate, and the
argument parsing, pre-flight checks and refusal paths of an acceptance
program, are pure, so they are named as tests and run in the ordinary
suite while the programs around them stay a person's tools. Both drive
their subject through injected fakes — a fake link, a fake camera, a
fake HTTP getter — and neither touches hardware.

## The two permanent pytest suites

- **`host/`** — this extension's portable firmware C++ (kernel, motion
  engine, v6 wire stack, wire adapter) compiled for the desktop with the
  system compiler and driven from pytest through `ctypes`, against fake
  ports. No micro:bit, PXT, or CODAL anywhere in the link.
- **`tools/`** — plain-Python unit tests over `tools/` scripts' own
  logic, no shim compilation and no hardware or network. It also holds
  the repo's **lint gate**, `test_ruff_clean.py` (sprint 034 ticket
  010): `ruff check tools tests`, run as a test rather than as a CI
  workflow because `uv run pytest` is this project's developer signal.
  Note its scope is `tools/` and `tests/` entire, not just what pytest
  collects — which is the point: the findings it first caught were in
  `dev/` and `system/`, where nothing else looks.
  `test_make_deploy_triage.py` pins `tools/make_deploy.py`'s
  `classify_attempt()` against saved/synthetic build logs;
  `test_tlm.py` pins `tools/tlm.py`'s `TlmStream` parser against the
  shared golden fixture in `tests/host/golden_telemetry.py`.

## Translation units nothing on the host compiles

Twelve `.cpp` files under `src/` reach `pxt.h` — directly, or
transitively through `platform/platform_ports.h` or
`platform/otos_port.h`. `pxt.h` ships with the `core` dependency
declared in `pxt.json`, brings CODAL's whole type set (`uBit`, fibers,
`NRF52Serial`, `MicroBitRadio`) and PXT's `//%` annotation machinery,
and none of it exists on the host. Eight of them are gated by other
means instead, and that is a decision (sprint 034 ticket 011), not an
oversight. **Sprint 044 ticket 011 reversed it for the other four**
(`shims.cpp`, `platform/otos_port.cpp`, `platform/vfp_guard.cpp`,
`platform/microbit_i2c_bus.cpp`): they now compile on the host against
a stub `pxt.h` (`tests/host/pxt_host_stub/pxt.h`) and are listed under
"Compiled against the stub" below, not in the table.

**One caveat this table's own guard cannot express.**
`platform/nezha_port.cpp` and `platform/board_nezha.cpp` (sprint 040
ticket 001) still appear below because
`test_pxt_bound_exclusion_is_current.py` matches `#include` lines with
a regex and cannot evaluate a preprocessor condition — but each file's
`#include "pxt.h"` now sits inside `#ifndef DIFFDRIVE_HOST_BUILD`,
guarding only CODAL-bound code (the naked-asm fault handlers in
`nezha_port.cpp`; the fault-context emergency-stop frame's real
`uBit.i2c.write()` in `board_nezha.cpp`, which ticket 001 moved there
from `nezha_port.cpp`). Compiled with `-DDIFFDRIVE_HOST_BUILD` the rest
of `nezha_port.cpp` — the entire shaping pipeline and encoder path —
builds and runs on the host, and IS host-tested
(`tests/host/sim_tour.py`); it is the one row here whose right-hand
column names a real host test of the WHOLE remaining file rather than
only the hex checkpoint. `board_nezha.cpp` does not get that same
treatment: its own non-target-bound half (the `NezhaBoard` singleton,
`boardMotors()`/`boardWiring()`/`boardConfigureWiring()`/
`boardDiagValue()`) constructs its two `NezhaMotorPort`s through the
DEFAULT bus argument (`defaultI2CBus()`), which only the target's
`platform/microbit_i2c_bus.cpp` defines — there is no host definition,
by design (`platform/i2c_bus.h`'s own comment). Since sprint 044
ticket 011 the stub-built `shims.cpp` library links that file too, so
`board_nezha.cpp` does link and run there (its pair of ports, `boardMotors()`,
`boardDiagValue()`); only its `#ifndef DIFFDRIVE_HOST_BUILD` half, the
fault-context stop frame and the Trackbit line sensors, stays
hex-checkpoint-only. The Nezha-specific field mapping each
hook delegates to (`nezhaBoardDiagValue()`, the wiring readback
methods) is host-tested where it actually lives, in
`platform/nezha_port.h`/`.cpp` (`tests/host/test_board_nezha_diag.py`);
what is NOT independently host-proved is `board_nezha.cpp`'s own thin
one-line delegation into that computation, which
`tests/host/test_board_seam_source_pin.py` pins as source text instead.
`platform/nezha_port.h` is no longer a route to `pxt.h` at all.

**Sprint 040 ticket 002 adds a twelfth: `platform/board_cutebot.cpp`**,
the Cutebot Pro's own half of the same seam, guarded by
`#ifndef DIFFDRIVE_HOST_BUILD` for the identical reason
(`diffdrive_emergency_motor_stop()`'s real `uBit.i2c.write()`) and
not host-linkable as a whole for the identical reason (its
`CutebotBoard` singleton also constructs through the default-bus
argument). Unlike `board_nezha.cpp`, though, `platform/cutebot_port.h`/
`.cpp` — the Cutebot's equivalent of `nezha_port.h`/`.cpp` — has NO
`pxt.h` route at all, not even a guarded one: the fault-context frame
lives entirely in `board_cutebot.cpp`, so `cutebot_port.cpp` is a plain
entry in the C++11 gate (`test_cxx11_syntax_gate.py`) rather than a row
in this table, and is host-tested directly, over a simulated Cutebot
bus, by `tests/host/test_cutebot_port.py`. `board_cutebot.cpp`'s own
thin hook wiring is source-pinned the same way `board_nezha.cpp`'s is,
by `tests/host/test_board_cutebot_source_pin.py`. **Sprint 040
ticket 006** adds the same whole-tour proof `nezha_port.cpp`'s own row
above gets: `sim_tour.py --board cutebot-pro`, over
`tests/host/sim_cutebot_robot_shim.cpp`, drives `cutebot_port.cpp` AND
`cutebot_actuation_policy.cpp` under the real kernel and `MotionEngine`
through a full square tour at all three `onboard_pid` modes — the
first host proof that the hybrid actuation policy's handoffs survive a
real move sequence rather than only the synthetic per-tick inputs
`test_cutebot_actuation_policy.py`/`test_cutebot_hybrid_actuation.py`
already cover.

| file | what binds it to the target | what gates it |
|---|---|---|
| `comms/protocol.cpp` | the serial/radio fiber loop, via `platform_ports.h` | hex checkpoint; `test_wire_constants_drift.py` pins the RX drain bound as source text; the cleartext RUN rules were extracted to `comms/run_bridge.cpp`, which **is** in the C++11 gate |
| `comms/radio_transport.cpp` | `MicroBitRadio`, `uBit.radio` datagram callbacks | hex checkpoint; the RX accept/drop decision and counters live in `radio_transport.h` and are host-tested (`radio_rx_classify_syntax_check.cpp`, `test_radio_transport_rx_capacity.py`) |
| `comms/serial_transport.cpp` | `uBit.serial` ring sizing and writes | hex checkpoint (the real build's own `-Woverflow`); the `Wire::Sink` half is `comms/transport_sink.h`, host-tested |
| `comms/wifi_uart.cpp` | `new NRF52Serial(uBit.io.P8, uBit.io.P1, NRF_UARTE1)` — one CODAL-facing byte pipe | hex checkpoint; the whole AT state machine is `comms/wifi_link.cpp`, which **is** in the C++11 gate and host-tested (`test_wifi_link.py`) |
| `platform/nezha_port.cpp` | the ARM fault handlers (naked `__asm`), unmoved — **inside `#ifndef DIFFDRIVE_HOST_BUILD`** | hex checkpoint for the guarded half; everything else compiles and runs on the host over a simulated brick (`tests/host/sim_nezha_bus.h`, driven by `sim_tour.py`), which is what finally put the shaping layer — quantizer, deadband, slew, write throttle, **reversal dwell** — under simulation; its new `nezhaBoardDiagValue()` free function is additionally host-tested directly by `test_board_nezha_diag.py` |
| `platform/board_nezha.cpp` | the `NezhaBoard` singleton's default-bus port construction (no host `defaultI2CBus()` exists) AND, inside `#ifndef DIFFDRIVE_HOST_BUILD`, `diffdrive_emergency_motor_stop()`'s CODAL write — moved here from `nezha_port.cpp` (sprint 040 ticket 001) per docs/design/cutebot-pro-support.md S2.1, since a second board's frame at the same address must not answer for this one | hex checkpoint for the whole file (unlike `nezha_port.cpp`, no host-linkable half); the field mapping its `boardDiagValue()` hook delegates to is host-tested via `nezha_port.h`'s `nezhaBoardDiagValue()` (`test_board_nezha_diag.py`); the hook wiring itself is source-pinned (`test_board_seam_source_pin.py`) |
| `platform/board_cutebot.cpp` | the `CutebotBoard` singleton's default-bus device construction (no host `defaultI2CBus()` exists) AND, inside `#ifndef DIFFDRIVE_HOST_BUILD`, `diffdrive_emergency_motor_stop()`'s CODAL write for the Cutebot's single-frame both-wheels-zero (sprint 040 ticket 002) per docs/design/cutebot-pro-support.md S1.2/S2.1 | hex checkpoint for the whole file (same shape as `board_nezha.cpp`, no host-linkable half); the Cutebot-specific field mapping its `boardDiagValue()` hook delegates to is host-tested via `cutebot_port.h`'s `cutebotBoardDiagValue()` (`test_cutebot_port.py`); the hook wiring itself is source-pinned (`test_board_cutebot_source_pin.py`) |
| `platform/wifi_flash_port.cpp` | `codal::MicroBitFlash::flash_write()`/`erase_page()` — one dedicated flash page (sprint 038 ticket 002) | hex checkpoint; on-hardware page-survival is ticket 004's job, not a host test's. Record layout, truncation-vs-reject policy, and list semantics live in `comms/wifi_credential_store.cpp`, which **is** in the C++11 gate and host-tested (`test_wifi_credential_store.py`) against a fake `WifiFlashPort` (`wifi_flash_port_shim.cpp`) |

Two things cover all eight regardless:
`host/test_include_paths_match_target.py` checks every `#include`
under `src/` with no compiler at all, these files included, and the
**hex checkpoint** — a real PXT build for a real target — is the only
thing that compiles them as the robot will. `host/test_cxx11_syntax_gate.py`
covers a deliberate list that excludes all eight.

### Compiled against the stub

Sprint 044 ticket 011, at the stakeholder's direction, host-compiles
`shims.cpp` and the three pxt-bound platform files its composition needs:

| file | how it runs on the host |
|---|---|
| `shims.cpp` | the real `Rig`, `ensure()` boot probe, `tickDrive()`, `idleSense()`, `seedPose()`, `diagValue()` and the config tables, behind `tests/host/shims_cpp_shim.cpp` |
| `platform/otos_port.cpp` | the real `OtosPort` over a simulated OTOS I2C slave (`tests/host/sim_otos_bus.h`) |
| `platform/vfp_guard.cpp` | `vfpSafeSleep()` onto the stub's `fiber_sleep()`, which advances the test's clock |
| `platform/microbit_i2c_bus.cpp` | `defaultI2CBus()` onto the stub's `uBit.i2c`, which routes each address to a simulated slave |

The recipe is `tests/host/shims_cpp_rig.py`; its tests are
`test_shims_cpp_estimator_wiring.py` (and the pose-estimator suite
beneath it). `protocol.cpp` and the other transports are still
excluded, so the `protocol*()` functions `shims.cpp` forward-declares are faked
in the shim.

**Why a stub now, when sprint 034 said no.** The objection was that a
stub only re-proves that the files parse, and cannot be honest about CODAL
signatures (`serial_transport.cpp:40`'s `setRxBufferSize` truncation, caught
only by the real build's `-Woverflow`). Both still hold for the files that
stay in the table, which is why they stay. What changed is the cost of the
alternative: the sprint 044 estimator wiring in `shims.cpp` (boot probe, idle
sensing and its gates, sample cadence, re-prime after a seed) held
behaviour that text pins could only check for spelling, and tickets 007/008
add more of it in the same file. The stub here is not inert — a
test-owned clock, recorded fibers, per-address I2C slaves — and it declares
only names the compiled sources use, so it cannot be mistaken for a model of
CODAL. It proves the wiring executes as written, not that the types match
the target; the hex build still does that.

**Adding a ninth.** `host/test_pxt_bound_exclusion_is_current.py`
re-derives this list from the tree and fails if it and the table
disagree, so a new `pxt.h`-bound `.cpp` cannot land silently
uncovered. Files compiled against the stub are named in that test and
checked against `shims_cpp_rig.SOURCES`.

## `system/` — the hardware tour suite

Not pytest. `system/run_tour.py` drives a **real robot** through a
`.tour` script and charts what came back, so it is run deliberately,
one tour at a time, at a bench with a board attached:

```
uv run --with numpy --with matplotlib python tests/system/run_tour.py \
    tests/system/tours/square.tour --host localhost --out reports/tours-<date>
```

`system/tourfile.py` parses the `.tour` format (documented in its own
docstring) and `system/tours/` holds the figures. These are permanent —
they are the regression the motion work is judged against, re-run
whenever shaping, geometry, or a robot's tuning changes. Results go to
`reports/` as markdown with the charts beside them.

## `dev/` — development scripts, deliberately disposable

Measurement harnesses written to answer **one open question**. They are
kept only while that question is open; when it closes, or when a
permanent test or a `.tour` covers the same ground, the script is
deleted rather than left to rot. Nothing imports from here, and nothing
in CI touches it.

Currently live:

- `closure.py` — square-tour closure on the bench in pure odometry,
  with the tuning knobs (`--overrun`, `--twist`, `--floor`,
  `--yawtaper`) as flags. Backs `reports/gopiv-closure-20260901.md`;
  keep while closure tuning is still being re-measured per robot and
  per battery.
- `sweep_tcp.py` — measures the velocity profile the wheels **actually**
  execute over a farm-node serial daemon: peak speed, accel ramp, decel
  slope, braking distance. The one thing the host harness cannot
  supply, because it measures the compiled engine rather than the robot.

Deleted 2026-09-01, and why, as the standard for what belongs here:
`tight_tour.py` (superseded by `system/run_tour.py`, which does the same
job for any `.tour` file and charts it) and `profile_probe.py` (asked
what shape the compiled profile has; that is now pinned by
`host/test_motion_engine_acceleration_profile.py` and friends, so a
script that prints it answers nothing a failing test would not).

Not to be confused with the sibling `test/` root (singular) — those are
PXT `testFiles`, on-robot MakeCode programs with no assertions,
documented in [`test/DESIGN.md`](../test/DESIGN.md). `RUN square`,
`RUN infinity` and `RUN spline` live there: the same three figures
`system/tours/` drives from the host, but running on the robot itself.
