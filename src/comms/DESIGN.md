# src/comms — wire protocol, transports, and protocol composition

**Owner:** Eric Busboom · **Last reviewed:** 2026-09-07 · **Status:** stable

The v6 ASCII wire stack and everything that gets it onto the wire:
`wire_handler.h/.cpp` (`Wire::WireHandler`, grammar/decode),
`wire_adapter.h/.cpp` (`diffDrive::WireAdapter`, verb dispatch and
motion-completion resolution), `config_fields.h` (the wire's config
name/ordinal/unit table — one list, read by `wire_adapter.cpp` and by
the `ConfigField` generator, with the matching behaviour in
`shims.cpp` — sprint 040 ticket 004 appends `onboard_pid` (43) and
`onboard_floor` (44), the hybrid-actuation policy's mode and floor;
the rows exist on the wire for every board, since the table is
append-only, but their `shims.cpp` accessor is a documented no-op/
refusal on a Nezha-composed build and only does something on a
Cutebot-composed one — see `src/DESIGN.md` §5/§7), `serial_transport.*` /
`radio_transport.*` (byte framing over uBit.serial and the fleet
radio relay — the radio owns its own opt-in gate, `enable()`/
`enabled()`, and its RX accept/drop decision plus the four counters
recording it are host-portable free functions in the header,
`radioRxLineFits()`/`radioRxClassify()`/`RadioRxCounters`, host-tested
by `tests/host/test_radio_transport_rx_capacity.py`),
`transport_sink.h` (`diffDrive::TransportSink`, the one
`Wire::Sink` all three transports are reached through, plus the
terminator decision it makes — host-portable, no `pxt.h`, host-tested
by `tests/host/test_transport_sink.py`), `run_queue.h` /
`run_bridge.h/.cpp`
(`diffDrive::RunBridge`, the `RUN` bridge's sanitize/dedupe/
park rules over that ring — host-portable, no `pxt.h`, host-tested by
`tests/host/test_run_bridge.py`), `run_registry.h/.cpp`
(`diffDrive::RunRegistry`, the C++ mirror of the names a block program
bound with `onRun()`, which the `FUNCS` verb enumerates — written from
`shims.cpp` as each handler binds, read back through the Adapter's
`runCount()`/`runName()`/`runSignature()` seam; host-portable, no
`pxt.h`, host-tested by `tests/host/test_run_registry.py`), and
`protocol.h/.cpp`
(`diffDrive::Protocol`, the CODAL fiber that plumbs transports into the
wire stack, and the only thing here that calls TypeScript or arbitrates
the drivetrain).

Detail lives in [`src/DESIGN.md`](../DESIGN.md) §4 (wire grammar), §5
(wire adapter, including the config surface and its generator), §6
(transports), and §8 (protocol composition, including the RUN bridge).
This
file does not duplicate that content — it exists so `ls src/comms/`
points somewhere.

## Position-move routing and config

`config_fields.h` gains `position_mode` (0 kernel, 1 built-in for
straights and pivots, 2 built-in for arcs too; default 1, arcs stay
on the kernel) and
`speed_path` (0 `0x60`, 1 `0x77`+`0x70` mode 3; default 0). `WHEELS_X`,
`MOVE_X`, `GO_TO_R/W` use `PositionMove` when the mode allows and the
composed board's ports `supportsPositionMove()`; `WHEELS_V`, `MOVE_V`
never do. `STATUS` carries a position-move flag naming the path that ran.

## Position-move defaults (sprint 043)

The defaults come from zuvat hardware evidence (captures under
`captures/zuvat-position-2026-10-27/`, all ENCODER truth). `position_mode`
boots at 1: straights and pivots run through the motor's own position
loop (50 cm worst 0.49 mm per wheel against 11.8 mm on the kernel,
`fiftycm/position.csv` vs `fiftycm/kernel.csv`; pivots 0.17 deg against
1.30 deg, `pivots/analysis_output.txt`; square closure mean 1.8 mm against
9.8 mm, `square/closure.csv`). Mode 2 is not the default: its arcs run both
wheels at nearly equal speed (`circle/closure_radial.csv`). The boot value
is one constant, `MotionEngine::kDefaultPositionMode`, which the Rig seeds
`GET position_mode` from, so a fresh engine routes a straight `MOVE_X` to
the position path with no `SET`. `speed_path` stays 0 (`speedpath/wheels_summary.csv`). Per-robot kernel constants are baked in the robot
config files with a capture citation beside each; zuvat bakes `decel` 1000
and `stop_distance_mm` 0.3 (`kdefaults/kd_summary.csv`).
