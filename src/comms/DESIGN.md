# src/comms — wire protocol, transports, and protocol composition

**Owner:** Eric Busboom · **Last reviewed:** 2026-09-07 · **Status:** stable

The v6 ASCII wire stack and everything that gets it onto the wire:
`wire_handler.h/.cpp` (`Wire::WireHandler`, grammar/decode),
`wire_adapter.h/.cpp` (`diffDrive::WireAdapter`, verb dispatch and
motion-completion resolution), `config_fields.h` (the wire's config
name/ordinal/unit table — one list, read by `wire_adapter.cpp` and by
the `ConfigField` generator, with the matching behaviour in
`shims.cpp`), `serial_transport.*` /
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
