---
source_paths:
- /Volumes/Proj/proj/RobotProjects/pxt-nezha-diffdrive/src
- /Volumes/Proj/proj/RobotProjects/pxt-nezha-diffdrive/tools
- /Volumes/Proj/proj/RobotProjects/pxt-nezha-diffdrive/tests
- /Volumes/Proj/proj/RobotProjects/pxt-nezha-diffdrive/test
---
# DiffDrive — System Design

**Owner:** Eric Busboom · **Last reviewed:** 2026-08-24 · **Status:** in-flux (as-built through sprint 010, closed and merged — sprints 004, 006, 007, 008 and 010 all closed and merged: radio speaks full v6 with a `thdr`/`t` telemetry frame and now carries the wire grammar's full 240-byte line capacity on both RX and TX; motion correctness (goTo geometry, cross-fiber stop delivery, continuous-mode odometry, OTOS heading wrap, encoder-reset rebaseline, encoder `PoseSource` fallback for GO_TO_W); student API (stall-latch clear and readback, the `driveTick()` contract, the wire `cruise == 0` sentinel, simulator parity, a `rotationalSlip` setter); wire hardening with a standing per-sprint build-checkpoint convention; and port-layer robustness (radio line capacity reconciled with the wire's own ceiling, STATUS gains a `cyc` field so "never ticked" is distinguishable from "brick unreachable," and a GET-path float-formatting overflow fixed across every configured field). Sprints 005 and 009 roadmapped, not yet detail-planned)

## What the system is

DiffDrive is a MakeCode/PXT extension for the micro:bit that gives the
ElecFreaks Nezha brick's two-wheel differential drive closed-loop
control: an encoder-servoed wheel-speed kernel stepped at a 24 ms
cadence, a motion engine that reduces every move to constant-ratio
wheel segments, dead-reckoned pose plus an optional OTOS optical world
sensor, student-facing blocks in cm/deg, and a protocol-v6 ASCII wire
interface over both USB serial and radio (sprint 004; a legacy
cleartext `RUN:` carve-out survives on both transports) for bench
hosts. Around the extension sit a Python bench-tool suite (`tools/`), a
native host test harness that compiles the firmware C++ for the
desktop and drives it from pytest (`tests/host/`), and on-robot PXT
test programs (`test/`).

## Subsystem map

- [`src/DESIGN.md`](../../src/DESIGN.md) — the extension itself:
  C++ kernel, motion engine, v6 wire stack, transports, hardware
  ports, and the TypeScript block API. `src/` is flat, so that one doc
  carries the logical subsystem breakdown as sections.
- [`tools/DESIGN.md`](../../tools/DESIGN.md) — host-side Python bench
  and diagnostic tooling: robot/camera links, deploy builds, tour
  runners/recorders/charts, ground-truth and calibration scripts.
- [`tests/DESIGN.md`](../../tests/DESIGN.md) — the Python-run test
  root; its one subsystem is
  [`tests/host/DESIGN.md`](../../tests/host/DESIGN.md), the native
  host harness (firmware C++ under pytest via ctypes).
- [`test/DESIGN.md`](../../test/DESIGN.md) — PXT `testFiles`: on-robot
  test programs (playfield tours, the zeguz OTOS rig). Deliberately
  thin.

Project-level companion docs in this directory: `overview.md`,
`specification.md`, `usecases.md` (stakeholder-facing; the
specification is the authoritative block-API reference).

## Global conventions

Subsystem docs assume everything below without restating it.

### Units ladder

Each layer has one native unit system; conversions happen at layer
boundaries, nowhere else.

| Layer | Units |
|---|---|
| Blocks (`main.ts`, student-facing) | cm, cm/s, degrees, degrees/s |
| TS→C++ shim boundary | **integers only**: mm, mm/s, centidegrees, centidegrees/s |
| Kernel config across the shim boundary | value × 1000 as an integer (the ×1000 fixed-point convention; `setKernelValue`/`getConfigValue` in `shims.cpp`) |
| MotionEngine | mm, mm/s, radians, ms |
| Kernel (`DiffDrive::DifferentialDrive`) | encoder counts and counts/s only — 1 count = 0.1° of shaft rotation; the kernel has **no chassis geometry** |
| v6 wire | integer fields: mm, mm/s, ms; **angles are milliradian integers** (`mradToRad()` in `wire_adapter.cpp` is the single wire→radians conversion point) |

### Coordinate frames and sign convention

- **CCW-positive everywhere.** Positive twist/rotation/yaw turns left
  and increases camera-measured yaw; the left wheel is the slower one
  in a left turn. This convention is pinned by host tests
  (`tests/host/test_motion_engine_primitives.py`) precisely so a
  cable-order "fix" fails a test instead of shipping — that bug has
  shipped before.
- **Robot/body frame:** x forward, y left.
- **Pose frame:** dead-reckoned `(x, y, heading)` in the start frame
  (re-anchored by `resetPose()`; seeded jointly with the OTOS by
  `seedPose()`).
- **World frame:** whatever frame the OTOS was seeded in — on the
  playfield, A1-centred, +x east, +y north.

### Left-motor mirroring

The wheels are mirror-mounted, so one motor's "forward" is the other's
"reverse". `NezhaMotorPort` takes a per-motor `fwdSign` applied to
**both** the commanded duty and the encoder readback — odometry read
through the same flipped sign stays self-consistent under any sign
choice, which means a sign error is invisible to odometry and only a
camera can catch it. Current (vevov) wiring in `shims.cpp`:
left = M1 with `fwdSign -1`, right = M2 with `+1`. Which port is
called "left" is the free variable that sets physical rotation
direction; the signs themselves set forward. Verified under AprilCam
2026-08-20.

### Geometry doctrine

`trackWidth` is the caliper-measured wheel separation and is **never
adjusted to make a turn land**. All rotational scrub correction lives
in `rotationalSlip`, measured separately against camera truth.
`effectiveTrackWidth() = trackWidth / rotationalSlip` is always
computed fresh, never cached, so a config read-back can never report a
derived number as though it had been measured.

### Protocol versioning

The wire protocol is **v6**: an ASCII line grammar (UPPERCASE
commands, lowercase replies, mandatory trailing `#<id>` sequence
numbers on sequenced verbs, ack/nack/err reliability layer). The
canonical spec is `radio-robot-lib/docs/design/protocol.md` and
`motion-api.md` — this project conforms to that grammar; it does not
vendor that library's C++. The entire binary v5 stack (COBS codec,
CRC-16, binary verbs) was deleted in sprint 003, not merely disused.
One legacy carve-out survives on both transports: the old cleartext
`RUN:<name>[:<arg>…]` form is detected by literal prefix ahead of the
v6 parser and bridged to TypeScript handlers via MessageBus. Sprint
004 closed the asymmetry this section used to describe: radio's
receive side now speaks the full v6 grammar too, through its own
`Wire::WireHandler` over the same shared adapter serial uses, with the
old `RUN:` prefix preserved as a fallback on both transports rather
than a radio-only ceiling (see `src/DESIGN.md` §8). **Sprint 010**
closed radio's remaining capacity gap: `RadioTransport`'s RX and TX
buffers now match the wire grammar's own 240-byte line ceiling exactly
(`Wire::WireHandler::kMaxLineBytes`, `SerialTransport::kMaxLineBytes`),
not the previous, arbitrary 64-byte RX / 200-byte TX limits — no
multi-fragment reassembly protocol was needed, because this project's
own fleet radio configuration (`microbit_radio_max_packet_size: 250`)
already carries a full 240-byte line in one physical fragment on both
transports. A single-fragment line whose declared length exceeds 240
bytes is now dropped outright rather than truncated to a parseable
(and executable) prefix — see `src/DESIGN.md` §6. v6 now **does**
carry a data-bearing telemetry frame — `thdr`/`t`, built in sprint 004
— replacing the old cleartext `TLM:` stream the same way the rest of
v5 was replaced, though the bench tooling in `tools/` that used to
parse `TLM:` has not yet been retrofit onto the new frame (sprint
005).

### Execution model (tick model, sprint 002)

The kernel's own background fiber is deliberately unwired. Every
control cycle runs on whichever fiber calls `tickDrive()` (a student's
`driveTick()` loop, a blocking move, or the protocol fiber while a
wire motion obligation is live), which self-paces to an absolute 24 ms
deadline. Exactly two background fibers exist: the protocol loop and a
starvation watchdog that port-level-stops the motors ~100–150 ms after
the last tick if something still looks like it is driving. "The robot
only moves while something ticks" is a system invariant.

### Sensor doctrine

The OTOS world sensor is consulted at **move boundaries only** — a
move runs entirely on encoder odometry and is never steered in flight.
The overhead camera is a diagnostic, never a control input. All OTOS
I2C traffic must run on the same fiber that ticks the kernel (shared
bus with the Nezha encoder; see `src/DESIGN.md`).

### Host-vs-target language standard

`tests/host/` compiles this project's portable C++ at `-std=c++20`;
both real embedded targets compile at `-std=c++11`, a target-toolchain
ceiling this project's own `pxt.json` cannot override. A green host
suite is therefore not evidence that a change actually compiles for
the robot — see `src/DESIGN.md` §11 for the confirmed instance (a
struct with default member initializers is not a C++11 aggregate),
the narrow syntax gate sprint 004 added to catch that class of defect,
and what that gate does not cover.

**Standing convention (sprint 008).** The `-std=c++11` syntax gate
closes one defect class (language-standard mismatches in the four
portable translation units and their extracted-header siblings) but
provably not the others: a `uint8_t`-truncated buffer size the real
compiler's `-Woverflow` catches and the gate's plain `-fsyntax-only`
does not (sprint 004 ticket 005), and a `pxt.json` manifest omission
that blocks every hex while the gate — which never reads `pxt.json` —
stays green (sprint 006, found by sprint 007 ticket 001). Both were
found only because a ticket happened to run a real build. Rather than
attempt a hard, automated gate on this — the two documented benign
build-abort shapes (the legacy V1 `bbc-microbit-classic-gcc` hex-merge
failure, and the nondeterministic packaging abort surfaced as
`TS9283`/`TS9043`/`TS9200`, always retriable) make a naive pass/fail
gate unreliable, and `close_sprint` itself is CLASI-server code this
project's own tickets cannot change — every sprint that touches
build-eligible source now includes a **mandatory, always-last
build-checkpoint ticket** that runs `tools/make_deploy.py` (triage-aware
as of sprint 008: it distinguishes a real `.cpp` compile failure from
the two benign abort shapes and retries the latter once automatically)
and confirms a flashable hex results from the sprint's own final state.
Sprint 004 ticket 005 and sprint 007 ticket 008 already did this
informally; sprint 008 is where it became a named, standing practice —
see `src/DESIGN.md` §11/§14 for the full detail and the tooling change.

### Provenance

`diffdrive.h/.cpp` is a vendored, byte-stable copy of the
radio-robot firmware's control kernel — bugs are fixed in both repos
until the firmware consumes this package. Everything else under `src/`
is owned here.
