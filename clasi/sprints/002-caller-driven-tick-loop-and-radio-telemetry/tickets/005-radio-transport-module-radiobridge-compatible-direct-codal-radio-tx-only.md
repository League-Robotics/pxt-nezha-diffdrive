---
id: '005'
title: Radio transport module (RADIOBRIDGE-compatible, direct CODAL radio, TX-only)
status: done
use-cases:
- SUC-004
depends-on: []
github-issue: ''
issue: radio-telemetry-plane-for-field-runs.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Radio transport module (RADIOBRIDGE-compatible, direct CODAL radio, TX-only)

## Description

Adds a new, TX-only radio transport module, independent of the tick
loop work (tickets 001-004) and independent of `protocol.cpp` — ticket
006 wires it in. Per sprint.md's Architecture ("Radio transport"
module) and Design Rationale, this must be wire-compatible with the
fleet's existing RADIOBRIDGE relay hardware, and must not add the
MakeCode `radio` block package given this project's known-tight flash
budget (sprint 001: an icon table alone overran the deploy budget by
876 bytes).

New files (e.g. `radio_transport.h`/`radio_transport.cpp`, naming
mirrors `serial_transport.{h,cpp}`):

- Talk directly to CODAL's `uBit.radio` object (the same
  direct-CODAL-object pattern `serial_transport.cpp` uses for
  `uBit.serial` and `nezha_port.cpp` uses for `uBit.i2c`) — do **not**
  add the MakeCode `radio` namespace/package as a `pxt.json` dependency.
- On `begin()`: `uBit.radio.enable()`, `uBit.radio.setGroup(10)` (fixed,
  matches the fleet's RADIOBRIDGE relay convention —
  `radio-robot-elite`'s `microbit_radio_link.cpp`), a default channel
  of `0` (frequency band; no per-robot channel-selection surface this
  sprint, per sprint.md's Design Rationale/Open Question 2), and a
  transmit power matching the reference (`setTransmitPower(7)`).
- On-air framing: replicate `radio-robot-elite`'s RadioRelay §5 fragment
  format exactly — `[SEQ:1][FLAGS:1][LEN:1][payload]` per fragment,
  `FLAGS` bits `START=0x01`/`MORE=0x02`/`END=0x04` (this module never
  needs to interpret an incoming `ACK=0x10`, since it never receives —
  see below), fragmented at whatever `MICROBIT_RADIO_MAX_PACKET_SIZE`
  actually resolves to for this build (CODAL's own default is 32 bytes;
  do not assume a raised value — see sprint.md Open Question 1). A
  trailing `'\n'` (0x0A) terminates every outbound line as the final
  payload byte, exactly as the reference does (safe because COBS in
  this project is keyed on 0x0A, so a binary line's own bytes never
  contain a literal 0x0A — same reasoning `protocol.h` already
  documents for the serial transport).
- TX-only: **no** RX registration (`_bus.listen(...)` for
  `MICROBIT_RADIO_EVT_DATAGRAM)`, no reassembly buffer, no ACK handling
  — this sprint's scope is telemetry-out only (sprint.md Scope/Out of
  Scope). A single small public send entry point (e.g. `sendLine(const
  uint8_t* data, size_t len)`) is enough; fragment internally as needed
  for lines that exceed one packet's payload.
- Update `pxt.json`'s `files` list to include the new source files
  (this is the first ticket in this sprint to add new source files —
  same convention sprint 001 ticket 001 established).

## Acceptance Criteria

- [x] New module uses `uBit.radio`/`.datagram` directly; `pxt.json`
      gains no new package dependency (no `"radio"` entry). Verified:
      `radio_transport.cpp` calls `uBit.radio.enable()`/
      `.setFrequencyBand()`/`.setGroup()`/`.setTransmitPower()`/
      `.datagram.send()` directly; `pxt.json`'s `dependencies` block is
      unchanged (`core` only).
- [x] Group is fixed at 10; channel defaults to 0; transmit power
      matches the reference relay-compatible convention. Verified:
      `RadioTransport::kGroup = 10`, `kChannel = 0`, `kTransmitPower = 7`
      (matches `microbit_radio_link.cpp`'s own `setTransmitPower(7)`),
      applied lazily in `ensureRadioReady()`.
- [x] On-air fragment framing matches `radio-robot-elite`'s
      `microbit_radio_link.{h,cpp}` (RadioRelay §5): `[SEQ][FLAGS][LEN]`
      header per fragment, `START`/`MORE`/`END` flags set correctly for
      single- and multi-fragment messages, trailing `'\n'` as the final
      payload byte. Verified by code + desk-trace (see ticket-close notes
      below); provenance comments in `radio_transport.h`/`.cpp` cite the
      reference file and section directly.
- [x] The module fragments correctly for a line longer than one packet's
      payload at whatever `MICROBIT_RADIO_MAX_PACKET_SIZE` this build
      actually compiles with — verified against a worst-case-length
      `TLM`/`DEVICE` line, not just a short one. Verified: this build's
      `codal.json` carries no override, so
      `MICROBIT_RADIO_MAX_PACKET_SIZE` resolves to codal-microbit-v2's
      default (32, `MicroBitConfig.h`), giving a 29-byte-per-fragment MTU.
      Desk-traced `sendFragmented()` against the worst-case `DEVICE` line
      (`protocol.cpp`'s `buf[64]`, up to 63 content bytes + `'\n'` = 64
      payload bytes) — correctly emits `START|MORE` (29B) → `MORE` (29B)
      → `END` (6B). The worst-case `TLM` line (`buf[48]`, up to ~39
      bytes + `'\n'`) also exceeds one fragment and correctly emits
      `START|MORE` → `END`.
- [x] No RX path exists: no datagram-event listener is registered, no
      reassembly buffer, no ACK interpretation. Verified: no
      `_bus.listen`/`MICROBIT_RADIO_EVT_DATAGRAM` call anywhere in the
      module; no reassembly buffer field; `FLAG_ACK` (0x10) is not even
      declared.
- [x] `pxt.json`'s `files` list includes the new source files. Verified:
      `radio_transport.h`/`radio_transport.cpp` added to `files`,
      positioned alongside `serial_transport.{h,cpp}`.
- [x] The compiled extension's flash footprint is checked (build size
      before/after this ticket) and any budget concern is surfaced
      explicitly, per sprint.md's flagged flash-budget risk — not
      silently shipped. Checked: `pxt build` in the scratch toolchain
      env, zero errors, both the codal-microbit-v2 and classic
      microbit-dal flavors. Exact Intel-HEX data-byte comparison
      (before vs. after adding the two new files to `pxt.json`, isolating
      just this ticket's change): **+0 bytes**, both flavors. This is a
      real, verified result, not a rounding artifact — the build's own
      `-ffunction-sections -fdata-sections` compile flags (confirmed in
      the actual `arm-none-eabi-g++` invocation) let the linker fully
      strip `RadioTransport`, since nothing in this ticket's scope calls
      into it yet (no call site exists in `protocol.cpp`/`shims.cpp`/
      `main.ts` — that wiring is ticket 006's job). **Flagged, not
      silently shipped**: the real flash cost of this feature is
      deferred to ticket 006, which must re-run this same before/after
      check once `RadioTransport::sendLine()` is actually reachable from
      `protocol.cpp`'s call graph — sprint.md's flash-budget risk remains
      open until then, not closed by this ticket.

## Testing

- **Existing tests to run**: none automated. Confirm the MakeCode
  simulator/hardware build still compiles with the new files added to
  `pxt.json`.
- **New tests to write**: none automated. This module's on-air
  correctness (an actual RADIOBRIDGE relay receiving and reassembling
  its packets) is not testable without hardware — covered by ticket
  006's mirrored `TLM`/`DEVICE` and sprint.md's deferred hardware pass.
  Desk-review this ticket's framing byte-for-byte against
  `radio-robot-elite`'s `microbit_radio_link.cpp` as the primary
  verification here.
- **Verification command**: none (no test runner). Verify by code
  review against the reference implementation and a compiled-size
  check.
