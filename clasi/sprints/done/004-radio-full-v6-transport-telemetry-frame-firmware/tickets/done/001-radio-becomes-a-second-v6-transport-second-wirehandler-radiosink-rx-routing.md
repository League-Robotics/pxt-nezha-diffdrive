---
id: '001'
title: 'Radio becomes a second v6 transport: second WireHandler + RadioSink + RX routing'
status: done
use-cases:
- SUC-001
- SUC-002
depends-on: []
github-issue: ''
issue: radio-speaks-full-v6-and-v6-gets-its-telemetry-frame.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Radio becomes a second v6 transport: second WireHandler + RadioSink + RX routing

## Description

Per `wifi-link.md:373` ("a separate `ProtocolHandler` per transport over
one shared adapter"), give radio its own `Wire::WireHandler` instance so
it can speak the full v6 grammar (ack/nack, `TLM`, `STATUS`, motion
verbs, etc.), not just the legacy `RUN:` cleartext bridge. This closes
sprint 003's own "Open Question 4," whose stated rationale was
circular: radio stayed RUN-only because nothing could reach the v6
stack over radio, which was true only because radio RX stayed RUN-only.

Two independent handlers over ONE shared `WireAdapter` is a structural
requirement, not an optimization: a single shared handler would let a
sequence gap on one transport nack the OTHER transport's next command,
corrupting a host that did nothing wrong. This ticket's whole
justification is proving that isolation holds, then relying on it.

This ticket does NOT touch telemetry (`emitTelemetry()` keeps its
current no-argument, ack/nack-only signature here — Phase B's split
lands in ticket 003) and does NOT touch `RadioTransport`'s send-path
concurrency (ticket 002). Scope is strictly: a second handler exists,
radio RX routes into it (with the `RUN:` carve-out preserved, unchanged,
exactly mirroring serial's existing dual-path logic), and each handler
gets its own periodic emission call on the existing 50 ms cadence.

## Acceptance Criteria

- [x] `src/protocol.h` gains a `RadioSink : Wire::Sink` (mirroring the
      existing `SerialSink` exactly: strips the trailing `'\n'`
      `WireHandler::writeLine()` always supplies, since
      `RadioTransport::sendLine()` appends its own) and a second
      `Wire::WireHandler wireHandlerRadio_` member, composed over the
      SAME `wireAdapter_` instance the serial handler already uses (NOT
      a second `WireAdapter`).
- [x] `Protocol::run()`'s radio RX branch is extended to mirror the
      serial branch's existing dual-path logic exactly: a line whose
      first `kOldRunPrefixLen` (4) bytes equal the literal `"RUN:"`
      still goes to `handleRun()` unchanged; every other line
      (including the v6 grammar's own `RUN <name> ... #<id>` verb) goes
      to `wireHandlerRadio_.feed()`. The existing serial branch is
      unchanged.
- [x] The periodic-emission block in `run()` calls
      `wireHandlerRadio_.emitTelemetry()` (today's no-arg,
      ack/nack-only signature — unchanged this ticket) alongside the
      existing `wireHandler_.emitTelemetry()` call, on the same 50 ms
      cadence.
- [x] A host test proves per-transport reliability isolation: two
      independent `Wire::WireHandler` instances (constructible today via
      `wire_grammar_shim.cpp`'s existing `wgCreate()` — no shim change
      needed for this specific property, since `expectedNext_`/
      `gapOutstanding_` are already plain instance members), fed a
      sequence gap on ONE, leave the OTHER's `expectedNext_`/ack stream
      and `malformedCount()` completely unaffected.
- [x] A `RUN:pivot:180`-style line fed to `wireHandlerRadio_`'s
      composition path (via `Protocol::run()`, or a targeted unit-level
      check of the prefix branch) still dispatches through the
      unchanged `handleRun()`/MessageBus bridge, not the v6 grammar.
- [x] `test.ts`'s existing bench tooling (which speaks the old
      colon-separated `RUN:` form) is unaffected — no `test/test.ts`
      changes required by this ticket.

## Implementation Plan

**Approach**: Mirror the existing serial-side structure in
`src/protocol.h`/`.cpp` exactly, generalizing the radio RX branch from
"only recognize `RUN:`" to "recognize `RUN:`, else feed the v6 stack" —
the same branch shape `run()` already has for serial (lines ~227-248 as
of this sprint's planning). No new `WireAdapter` is constructed; both
handlers share the existing `wireAdapter_` NSDMI member.

**Files to modify**:
- `src/protocol.h`: add `RadioSink` (nested class, mirrors `SerialSink`),
  add `wireHandlerRadio_` member (NSDMI, composed over `wireAdapter_` and
  a new `radioSink_` member — order matters: `radioSink_` must be
  declared before `wireHandlerRadio_` since NSDMI evaluates in
  declaration order, same convention the existing `serialSink_`/
  `wireAdapter_`/`wireHandler_` trio already uses).
- `src/protocol.cpp`: extend `run()`'s radio-RX poll block to add the
  `RUN:`-prefix-vs-v6 branch (copy the serial branch's shape); add the
  second `emitTelemetry()` call to the periodic-emission block.

**Testing plan**:
- New pytest test (add to `tests/host/test_wire_reliability.py`, or a
  new `tests/host/test_wire_per_transport_isolation.py` if that file's
  existing scope reads as fully occupied — programmer's judgment):
  create two handles via the existing `wgCreate()`/`wgFeed()`/
  `wgSinkRead()` ctypes API, drive a sequence gap into handle A (e.g.
  feed `STATUS #5` first with no prior traffic, expecting a nack for
  `#1`), then drive handle B through a normal in-order sequence and
  assert its acks are exactly what a fresh, ungapped handler would
  produce — proving handle A's gap left no trace on handle B.
- No new host test is possible for the `Protocol::run()` RX-routing
  change itself or the periodic dual-emission call — `protocol.cpp`
  `#include`s `pxt.h`/CODAL types and has no host shim. Verify this
  slice by code review (the radio branch is a direct structural mirror
  of the already-tested serial branch) and by Phase C's bench
  checkpoint (ticket 005).
- **Verification command**: `uv run pytest tests/host/test_wire_reliability.py tests/host/test_wire_grammar.py` (scoped to the modules this ticket touches, per this project's per-ticket test-scoping rule — the full suite runs once at `close_sprint`).

**Documentation updates**: none required beyond this ticket's own file
and the code comments `protocol.h`/`.cpp` already carry describing the
old Open-Question-4 carve-out (update that comment's framing from "radio
stays RUN-only" to "radio speaks full v6, `RUN:` preserved as a
fallback" so it does not read as stale once this ticket lands).

**PXT trap to watch**: do not add the substring "radio." (the word
"radio" followed by a period, even inside a comment) anywhere in the
new/edited comments — PXT's dependency scanner reads that as a request
for a package this project does not use. `src/protocol.h` already has
one such literal that is empirically harmless (do not add a second).
