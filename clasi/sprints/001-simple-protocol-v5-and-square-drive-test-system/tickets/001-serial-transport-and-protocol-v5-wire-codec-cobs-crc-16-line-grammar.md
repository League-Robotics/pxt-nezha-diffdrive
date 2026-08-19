---
id: '001'
title: Serial transport and Protocol v5 wire codec (COBS+CRC-16, line grammar)
status: done
use-cases:
- SUC-001
- SUC-002
- SUC-003
- SUC-004
- SUC-005
depends-on: []
github-issue: ''
issue: implement-simple-protocol-v5.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Serial transport and Protocol v5 wire codec (COBS+CRC-16, line grammar)

## Description

Foundational ticket: build the Transport module (USB serial line I/O)
and the Protocol/Comms codec layer (COBS 0x0A-keyed encode/decode,
CRC-16/CCITT-FALSE, and the v5 line-grammar parser) that every later
verb-handling ticket (002-005) builds on. This ticket does **not**
implement any command verb dispatch — only the foundation: line
read/write, framing, and a small closed verb-registry data structure
ready for later tickets to register handlers into. See sprint.md's
Architecture section (Substantial tier) for the full module boundary
rationale, including why the protocol loop runs in its own CODAL fiber
rather than the kernel's.

Reference: `/Volumes/Proj/proj/RobotProjects/radio-robot-elite/docs/protocol-v5.md`
§2.1 (line grammar) and §2.2 (COBS+CRC framing).

## Acceptance Criteria

- [x] New Transport module owns USB-serial line-delimited I/O
      (read-until-`0x0A`, write-line); it has no knowledge of COBS,
      CRC, or verb semantics.
- [x] New Protocol/Comms module implements COBS encode/decode keyed on
      `0x0A` (not `0x00`), matching spec §2.2.
- [x] CRC-16/CCITT-FALSE is implemented and verified against the
      spec's known-answer vector: `crcCompute("123456789", 9) == 0x29B1`.
- [x] CRC scope covers `COMMAND ':' payload` (the parsed command name,
      then the separator, then the payload) — not payload alone — per
      spec §2.2.
- [x] Line-grammar parsing is implemented per spec §2.1: the first
      `':'` ends the command name; every later byte (including further
      `':'` bytes) is data; a colon-less line is only a candidate for a
      no-data cleartext verb; a single trailing `\r` is stripped before
      lookup.
- [x] A small closed verb-registry data structure exists (verb name →
      cleartext/binary flag), ready for tickets 002-005 to register
      handlers into. No verb handlers are registered in this ticket.
- [x] The protocol loop runs in its own CODAL fiber, launched via the
      existing `CodalFiberLauncher` pattern (see `platform_ports.h`),
      independent of the kernel's 24 ms fiber. Code comments document
      that handlers registered against this loop must stay short and
      non-blocking (sprint.md Design Rationale: fiber-scheduling risk).
- [x] `pxt.json`'s `files` list includes every new source file this
      ticket adds.
- [x] No changes to `diffdrive.h`/`diffdrive.cpp` (vendored kernel).
- [x] A COBS encode-then-decode round trip is desk-verified for at
      least one payload containing an embedded `0x00` byte (legal
      under `0x0A`-keyed COBS) and reproduces the original bytes
      exactly.

## Implementation Plan

**Approach**: Add new C++ source files implementing Transport and the
codec/grammar layer, composed the same way `platform_ports.h` composes
with `shims.cpp` — a thin CODAL-facing port plus a codec module above
it. Reuse the existing `CodalFiberLauncher` for the protocol loop's own
fiber; do not add a second `Clock`/`Sleeper` implementation — reuse
`platform_ports.h`'s existing `CodalClock`/`CodalSleeper` where a clock
or sleep primitive is needed. File/class naming is the implementer's
call, consistent with this repo's existing naming style
(`nezha_port.h`, `platform_ports.h`).

**Files to create/modify**:
- New `.h`/`.cpp` file(s) for Transport (serial line I/O).
- New `.h`/`.cpp` file(s) for the Protocol/Comms codec + line grammar +
  verb registry scaffold.
- `pxt.json` (`files` list) — add every new file.

**Testing plan**: This repo has no on-device automated test harness
(see sprint.md's Test Strategy — `test.ts` is a smoke program, not an
assertion suite). Verification here is desk-checking the COBS
round-trip and the CRC-16 known-answer vector above, plus code review.
Hardware bench verification of real framing over the USB serial link
is deferred to the stakeholder after sprint close, per
`test-on-microbit-zetuv-via-mbdeploy.md`: resolve the test device via
`mbdeploy` by name ("zetuv"), never a hard-coded port, whenever that
hardware pass happens.

**Documentation updates**: Brief header comments on each new file
describing its purpose, matching this repo's existing convention (see
the header comments in `nezha_port.h`/`shims.cpp`). No `docs/design/`
changes required by this ticket.
