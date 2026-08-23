---
id: '005'
title: 'Hardware transport-seam cutover: retire v5 protocol.cpp, wire WireHandler
  onto Serial/Radio transports'
status: done
use-cases:
- SUC-001
- SUC-004
depends-on:
- '004'
github-issue: ''
issue: implement-protocol-v6-wire-grammar-and-reliability.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Hardware transport-seam cutover: retire v5 protocol.cpp, wire WireHandler onto Serial/Radio transports

## Description

Retire the v5 wire format entirely from `src/protocol.h`/`.cpp`: remove
the COBS codec, the CRC-16, the binary verb payload shapes
(`MOVE`/`WHEELS`/`CONFIG`/`GET_CONFIG`/`SET_FIELD`/`CALIBRATE`/`CFG`),
and their handlers. What remains under these filenames becomes the
hardware transport-seam/fiber-loop composition module: it owns the
CODAL fiber (`Protocol::start()`/`run()`), feeds raw bytes from
`SerialTransport` and `RadioTransport` into `WireHandler::feed()`
byte-by-byte or in whatever chunks the transport delivers (not
pre-split into lines — `feed()` owns its own line reassembly, per
ticket 002/003's tested contract), and keeps the existing `RUN`
MessageBus bridge (`handleRun`/`runText`/the `runSlots_` ring) since
`main.ts`'s `onRun`/`onRunCommand` block API is unchanged this sprint.
`STOP`/`ESTOP`/`GET`/`SET`/`TLM`/`ID`/`VER`/`STATUS`/`HELP`/`RUN` all
work for real on hardware after this ticket; the five not-yet-wired
motion verbs still answer `kUnknown` (tickets 011/012 replace that).

## Acceptance Criteria

- [x] `src/protocol.h`/`.cpp` no longer contain any COBS/CRC/binary
      verb code — `cobsEncode`/`cobsDecode`/`crcCompute`/
      `encodeBinaryBody`/`decodeBinaryBody`/`kVerbRegistry` and their
      binary handlers are deleted, not merely unused.
- [x] `Protocol::run()`'s fiber loop feeds bytes from
      `SerialTransport`/`RadioTransport` into a `WireHandler` instance
      composed with a `WireAdapter`, and writes `WireHandler`'s reply
      bytes back out via a `Sink` implementation over those same
      transports.
- [x] `HELLO`'s boot banner still goes out unsolicited at fiber start
      (SUC-001 of the existing `docs/design/usecases.md`, preserved).
- [x] The `RUN` MessageBus bridge (event source, slot ring, dedupe
      window) is preserved unchanged — `test/test.ts`'s `RUN:tour:...`
      commands still work.
- [x] The radio RX command plane stays `RUN`-only (existing carve-out;
      not extended to motion verbs this sprint — sprint.md Open
      Question 4).
- [x] The extension compiles for the `microbit` target with no new PXT
      build errors (verified via whatever local PXT build check this
      repo uses — see ticket 013 for the FULL build validation; this
      ticket's own criterion is "compiles," not "flashed and driven").
- [x] Every touched/removed file's `pxt.json` `files` entry is correct
      (no now-nonexistent binary-codec source referenced; `wire_handler`/
      `wire_adapter` already added in tickets 002/004).

## Implementation Notes (as built)

- `WireHandler`/`WireAdapter` composed as members of `Protocol` via
  in-class initializers (no hand-written constructor needed); a nested
  `Protocol::SerialSink : Wire::Sink` writes replies to
  `SerialTransport` only (strips the trailing `\n` `WireHandler` always
  supplies, since `SerialTransport::writeLine()` appends its own).
  Deliberately **not** mirrored onto radio — unlike the old v5 code's
  `DEVICE`/`TLM` mirror, nothing can reach the v6 stack over radio to
  begin with (RX stays `RUN`-only per this ticket's own carve-out), so
  there is no host on that side to address. `emitLine()` (test-result
  reporting) is unchanged and still mirrors to both transports.
- The old-style cleartext `RUN:<name>[:<arg>...]` line is now detected
  by a direct `"RUN:"` prefix check in `run()` (the general v5 verb
  registry that used to recognize it is gone); everything else,
  including the v6 grammar's own space-separated `RUN <name> ... #<id>`
  verb, is fed to `wireHandler_`. Same carve-out applied to the radio
  RX path.
- **`DIAG` has no v6 equivalent and was dropped** (it is not in
  `wire_handler.cpp`'s `kCommandTable`, and this ticket's own acceptance
  criteria list every verb that must "work for real" without mentioning
  it). `STATUS` is the v6 verb that now covers the same ready/estop/
  stall/lease/conn/wedge surface. Flagging this for the stakeholder /
  ticket 013 in case bench tooling still expects a `DIAG` reply.
- **Identity is assembled at fiber-body time, not at `Protocol`
  construction time**: `wireAdapter_` is constructed with a harmless
  placeholder `Wire::Identity()`; `run()` calls
  `wireAdapter_.setIdentity(buildIdentity())` as its first statement,
  matching the exact timing the old `sendDeviceBanner()` proved safe
  for `microbit_friendly_name()`/`microbit_serial_number()` (both are
  CODAL calls that must not happen before `uBit.init()`, and `Protocol`
  is constructed earlier — at `_startProtocol()`'s top-level call —
  than that fiber-body call site).
- **A real clock is now wired into `WireAdapter`** (`NowMsFn`, a plain
  function pointer defaulting to `nullptr`, per the ticket 004 handoff)
  via `Protocol::wireNowMs()`, which reuses `clock_` through the
  `protocol()` singleton accessor. This was necessary, not cosmetic:
  with the kernel's own background fiber long gone, a wire-issued
  `WHEELS_V` is never actually stepped unless something keeps calling
  `tickDrive()` while it's outstanding (sprint 002's original problem
  for the retired binary `WHEELS` verb). `WireAdapter` now tracks that
  obligation itself (`hasLiveMotionObligation()`, set in `onWheelsV()`,
  cleared in `onStop()`/`onEstop()`) since it is the one place that
  sees every accepted call with its real duration; `protocol.cpp`'s
  `run()` polls it each iteration and still owns the actual
  `tickDrive()` call. This is new, small, WireAdapter-side logic beyond
  "just carries the bytes" — outside what this ticket's own testing
  plan anticipated ("no new host tests"), but omitting it would have
  left `WHEELS_V` silently inert on real hardware, the one motion verb
  this ticket is supposed to make "work for real." No new host test was
  added for it (host tests never drive a tick loop); verified only by
  the PXT build and code inspection.
- **Two real bugs fixed outside `protocol.h`/`.cpp`, discovered while
  verifying the PXT build** (this is the first ticket to actually
  compile `wire_handler.cpp`/`wire_adapter.cpp` for the `microbit`
  target rather than host-only):
  - `src/wire_handler.cpp` used `std::snprintf`/`std::strtof`, which do
    not exist in namespace `std` on this project's ARM cross compiler's
    newlib-nano — the exact gotcha the retired v5 code already knew
    about and worked around (`protocol.cpp`'s old `<stdio.h>` comment).
    Changed to plain `snprintf`/`strtof` (12 + 1 call sites).
  - `src/serial_transport.h`'s `kMaxLineBytes` (200) was smaller than
    `Wire::WireHandler::kMaxLineBytes` (240, the actual wire-spec
    ceiling) — a legal 201–239-byte v6 line (e.g. a verbose `RUN` with
    several arguments) would have been silently truncated by
    `SerialTransport` before `WireHandler` ever saw it, undermining that
    class's own tested "discard the whole overlong line, never
    truncate" guarantee. Raised to 240 to match.
- Scoped host tests: `uv run pytest tests/host/` — 144 passed (no
  behavior change to the host-tested wire grammar/reliability/motion
  verb decode; `WireAdapter`'s only test-observable-relevant change is
  the two new optional-clock-off defaults, which the existing
  single-argument `WireAdapter(identity)` call sites are unaffected by).
- PXT build: `uv run python tools/make_deploy.py` produced a hex on the
  second attempt (the first hit the documented nondeterministic
  V1-variant packaging failure — `srec_cat: ... contradictory ...
  value` / "BUILD PRODUCED NO HEX" — exactly as this ticket's own
  instructions anticipated; re-running was the fix, not a code change).
  Not flashed — no robot attached, hardware validation deferred to the
  stakeholder per this ticket's own scope.

## Implementation Plan

**Approach**: This is a hardware-only integration ticket — it has no
new host-testable behavior beyond what tickets 002-004 already proved
on the host (that is the point of separating the wire grammar/verbs
from the transport seam, per sprint.md's Design Rationale on why these
are three separate tickets). Replace `protocol.cpp`'s dispatch loop
body with byte-feeding into `WireHandler`; delete the old binary-verb
machinery; keep the fiber/RUN-bridge/telemetry-cadence structure that
has nothing to do with the wire format itself.

**Files to modify**: `src/protocol.h`/`.cpp` (large deletion + rewire),
`pxt.json` if any file is removed.

**Files to create**: none (wire_handler/wire_adapter already exist).

**Testing plan**: No new host tests — this ticket's correctness is
already covered by tickets 002-004's host suite (the wire behavior
itself does not change here, only what carries the bytes). Verification
here is a successful PXT compile; full on-microbit build/behavior
validation is deferred to ticket 013 once every verb is wired.

**Documentation updates**: Update `src/protocol.h`'s own top-of-file
comment (it currently describes the retired v5 COBS/CRC/registry
design in detail) to describe the new transport-seam-only role.

**Testing**

- **Existing tests to run**: `uv run pytest tests/host/` (confirms this
  ticket did not touch anything the host suite covers — it shouldn't,
  since `protocol.cpp` is CODAL-only and outside the host harness's
  compile set).
- **New tests to write**: none (host-untestable; hardware-only change).
- **Verification command**: `uv run pytest tests/host/` plus a PXT
  compile check (see `pxt.json`/build tooling for this repo's exact
  local build command).
