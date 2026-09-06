# src/comms — wire protocol, transports, and protocol composition

**Owner:** Eric Busboom · **Last reviewed:** 2026-08-26 · **Status:** stable

The v6 ASCII wire stack and everything that gets it onto the wire:
`wire_handler.h/.cpp` (`Wire::WireHandler`, grammar/decode),
`wire_adapter.h/.cpp` (`diffDrive::WireAdapter`, verb dispatch and
motion-completion resolution), `serial_transport.*` /
`radio_transport.*` (byte framing over uBit.serial and the fleet
radio relay), and `protocol.h/.cpp` (`diffDrive::Protocol`, the CODAL
fiber that plumbs transports into the wire stack).

Detail lives in [`src/DESIGN.md`](../DESIGN.md) §4 (wire grammar), §5
(wire adapter), §6 (transports), and §8 (protocol composition). This
file does not duplicate that content — it exists so `ls src/comms/`
points somewhere.
