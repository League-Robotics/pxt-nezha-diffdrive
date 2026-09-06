# src/comms — wire protocol, transports, and protocol composition

**Owner:** Eric Busboom · **Last reviewed:** 2026-08-26 · **Status:** stable

The v6 ASCII wire stack and everything that gets it onto the wire:
`wire_handler.h/.cpp` (`Wire::WireHandler`, grammar/decode),
`wire_adapter.h/.cpp` (`diffDrive::WireAdapter`, verb dispatch and
motion-completion resolution), `config_fields.h` (the wire's config
name/ordinal/unit table — one list, read by `wire_adapter.cpp` and by
the `ConfigField` generator, with the matching behaviour in
`shims.cpp`), `serial_transport.*` /
`radio_transport.*` (byte framing over uBit.serial and the fleet
radio relay), `run_queue.h` / `run_bridge.h/.cpp`
(`diffDrive::RunBridge`, the cleartext `RUN:` bridge's sanitize/dedupe/
park rules over that ring — host-portable, no `pxt.h`, host-tested by
`tests/host/test_run_bridge.py`), and `protocol.h/.cpp`
(`diffDrive::Protocol`, the CODAL fiber that plumbs transports into the
wire stack, and the only thing here that calls TypeScript or arbitrates
the drivetrain).

Detail lives in [`src/DESIGN.md`](../DESIGN.md) §4 (wire grammar), §5
(wire adapter, including the config surface and its generator), §6
(transports), and §8 (protocol composition, including the RUN bridge).
This
file does not duplicate that content — it exists so `ls src/comms/`
points somewhere.
