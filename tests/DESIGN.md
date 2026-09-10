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

Ten `.cpp` files under `src/` reach `pxt.h` — directly, or
transitively through `platform/platform_ports.h` or
`platform/otos_port.h`. `pxt.h` ships with the `core` dependency
declared in `pxt.json`, brings CODAL's whole type set (`uBit`, fibers,
`NRF52Serial`, `MicroBitRadio`) and PXT's `//%` annotation machinery,
and none of it exists on the host. They are gated by other means
instead, and that is a decision (sprint 034 ticket 011), not an
oversight.

**One caveat this table's own guard cannot express.**
`platform/nezha_port.cpp` still appears below because
`test_pxt_bound_exclusion_is_current.py` matches `#include` lines with
a regex and cannot evaluate a preprocessor condition — but that file's
`#include "pxt.h"` now sits inside `#ifndef DIFFDRIVE_HOST_BUILD`,
guarding only CODAL and the naked-asm fault handlers. Compiled with
`-DDIFFDRIVE_HOST_BUILD` the rest of it — the entire shaping pipeline
and encoder path — builds and runs on the host, and IS host-tested
(`tests/host/sim_tour.py`). It is the one row here whose right-hand
column names a real host test rather than only the hex checkpoint.
`platform/nezha_port.h` is no longer a route to `pxt.h` at all:

| file | what binds it to the target | what gates it |
|---|---|---|
| `shims.cpp` | the PXT `//%` block surface itself, plus the real `Rig` composition and watchdog | hex checkpoint; the extracted math is host-tested (`motion/odometry.h`, `core/bus_guard.h`, `core/fiber_identity.h`) |
| `comms/protocol.cpp` | the serial/radio fiber loop, via `platform_ports.h` | hex checkpoint; `test_wire_constants_drift.py` pins the RX drain bound as source text; the cleartext RUN rules were extracted to `comms/run_bridge.cpp`, which **is** in the C++11 gate |
| `comms/radio_transport.cpp` | `MicroBitRadio`, `uBit.radio` datagram callbacks | hex checkpoint; the RX accept/drop decision and counters live in `radio_transport.h` and are host-tested (`radio_rx_classify_syntax_check.cpp`, `test_radio_transport_rx_capacity.py`) |
| `comms/serial_transport.cpp` | `uBit.serial` ring sizing and writes | hex checkpoint (the real build's own `-Woverflow`); the `Wire::Sink` half is `comms/transport_sink.h`, host-tested |
| `comms/wifi_uart.cpp` | `new NRF52Serial(uBit.io.P8, uBit.io.P1, NRF_UARTE1)` — one CODAL-facing byte pipe | hex checkpoint; the whole AT state machine is `comms/wifi_link.cpp`, which **is** in the C++11 gate and host-tested (`test_wifi_link.py`) |
| `platform/nezha_port.cpp` | the ARM fault handlers (naked `__asm`) and `diffdrive_emergency_motor_stop()`'s CODAL write — **both inside `#ifndef DIFFDRIVE_HOST_BUILD`** | hex checkpoint for the guarded half; everything else compiles and runs on the host over a simulated brick (`tests/host/sim_nezha_bus.h`, driven by `sim_tour.py`), which is what finally put the shaping layer — quantizer, deadband, slew, write throttle, **reversal dwell** — under simulation |
| `platform/microbit_i2c_bus.cpp` | `uBit.i2c` itself: the codebase's entire CODAL I²C dependency, deliberately concentrated here so `nezha_port.cpp` need not carry it | hex checkpoint; there is no logic to test — every line forwards to `uBit.i2c`, and the interface it implements (`platform/i2c_bus.h`) is host-compiled by every `sim_tour.py` build |
| `platform/otos_port.cpp` | SparkFun OTOS I²C transactions, via `otos_port.h` | hex checkpoint; the heading-wrap math is `core/heading_wrap.h`, host-tested |
| `platform/vfp_guard.cpp` | `fiber_sleep()` | hex checkpoint; `test_vfp_guard_source_pin.py` |
| `platform/wifi_flash_port.cpp` | `codal::MicroBitFlash::flash_write()`/`erase_page()` — one dedicated flash page (sprint 038 ticket 002) | hex checkpoint; on-hardware page-survival is ticket 004's job, not a host test's. Record layout, truncation-vs-reject policy, and list semantics live in `comms/wifi_credential_store.cpp`, which **is** in the C++11 gate and host-tested (`test_wifi_credential_store.py`) against a fake `WifiFlashPort` (`wifi_flash_port_shim.cpp`) |

Two things cover all ten regardless:
`host/test_include_paths_match_target.py` checks every `#include`
under `src/` with no compiler at all, these files included, and the
**hex checkpoint** — a real PXT build for a real target — is the only
thing that compiles them as the robot will. `host/test_cxx11_syntax_gate.py`
covers a deliberate list that excludes all ten.

**Why no stub `pxt.h`.** A stub would only re-prove that these files
parse, which the include gate plus the hex checkpoint already cover
between them, and it could not be honest: `serial_transport.cpp:40`'s
`uBit.serial.setRxBufferSize(kRingBytes)` shipped a silent `uint8_t`
truncation (sprint 004 ticket 007, Defect B) that the real build's
`-Woverflow` caught — a stub has to invent that parameter's type, so
it would only catch the bug if it already encoded the fact under test.
The project's standing remedy for "logic in a `pxt.h`-bound TU is
untested" is the pattern in the right-hand column above: move the
decision into a host-portable header and test it there.

**Adding a ninth.** `host/test_pxt_bound_exclusion_is_current.py`
re-derives this list from the tree and fails if it and the table
disagree, so a new `pxt.h`-bound `.cpp` cannot land silently
uncovered.

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
