---
id: '002'
title: RadioTransport re-entrancy guard for the protocol fiber's send path
status: open
use-cases: [SUC-001, SUC-002]
depends-on: ["001"]
github-issue: ''
issue: radio-speaks-full-v6-and-v6-gets-its-telemetry-frame.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# RadioTransport re-entrancy guard for the protocol fiber's send path

## Description

`RadioTransport::payloadBuf_`/`frameBuf_` are documented single-fiber-
only members (`radio_transport.h:128-134`, with a measured hard-fault
history behind why they are members and not stack locals). Today
exactly one fiber calls `sendLine()` — the TS fiber, via
`Protocol::emitLine()`. Ticket 001 makes the protocol fiber a SECOND
caller (via the new `RadioSink::write()` -> `radioTransport_.sendLine()`
path), and `uBit.radio.datagram.send()` can block and yield, so two
fibers now have a real chance to interleave mid-format and corrupt each
other's write into those shared buffers.

Add a `sending_` guard: the second caller (whichever call arrives while
`sending_` is already true) returns immediately without touching the
buffers. `sendLine()` changes from `void` to `bool` (false = dropped due
to contention) so a caller can tell the difference. `emitLine()` (the
one caller whose loss is user-visible — e.g. an `OCAL:` corner-fix
result) gets exactly ONE `fiber_sleep(2)`-and-retry on a false return;
the telemetry path (`RadioSink::write()`, reached by ticket 003's
`emitTelemetry`/`emitReliability`) does NOT retry — a dropped `t` frame
self-heals for free via the next frame's `seq` gap, and retrying there
would just reintroduce the same contention it is trying to avoid.

## Acceptance Criteria

- [ ] `RadioTransport::sendLine()` returns `bool`: `true` on a normal
      send, `false` if a call was already in progress (the guard
      fired) — the caller that fired the guard does NOT touch
      `payloadBuf_`/`frameBuf_` at all before returning.
- [ ] A `sending_` bool member is set true at entry to the guarded body
      and cleared before every return path (normal completion AND the
      guard's own early return leaves it as the OTHER caller's send is
      still in flight — only the caller that actually entered the
      guarded section clears it, on its own way out).
- [ ] `Protocol::emitLine()` checks `radioTransport_.sendLine()`'s
      return value; on `false`, it calls `fiber_sleep(2)` and retries
      the send exactly once (not in a loop) before giving up silently.
- [ ] `RadioSink::write()` (ticket 001/003's radio sink) ignores
      `sendLine()`'s bool return entirely — a dropped telemetry/ack
      line under contention is accepted silently, by design (see
      Description).
- [ ] `SerialTransport`'s own send path is untouched — this guard is
      `RadioTransport`-only; serial has no analogous second-caller
      hazard (`SerialTransport::writeLine()` was already the single
      send path for both the TS fiber and, after ticket 001, the
      serial `WireHandler`'s replies — confirm this ticket does not
      need to touch it, since `SerialTransport` has no documented
      single-fiber-only member buffers the way `RadioTransport` does).

## Implementation Plan

**Approach**: A minimal boolean guard around `sendLine()`'s existing
body (the part that touches `payloadBuf_` and calls
`sendFragmented()`), not a full lock — see `sprint.md`'s own Design
Rationale for why a bounded, asymmetric retry (not a mutex, not a
symmetric retry on every caller) is the right amount of machinery for
exactly two callers with different loss tolerance.

**Files to modify**:
- `src/radio_transport.h`: change `sendLine()`'s declared return type
  to `bool`; add the `sending_` bool member (private, next to the
  existing `radioReady_`/`rxReady_` flags).
- `src/radio_transport.cpp`: guard `sendLine()`'s body; return `false`
  immediately if already sending, `true` after a normal completion.
- `src/protocol.cpp`: update `Protocol::emitLine()` to check the bool
  return and retry once after `fiber_sleep(2)`.
- `src/protocol.h`/`.cpp` (ticket 001's `RadioSink`): confirm/leave
  `write()` discarding the bool return (an explicit `(void)` cast or
  equivalent, so the ignored-return-value intent reads as deliberate,
  not an oversight a future reader "fixes").

**Testing plan**:
- **No host test is possible for this ticket's actual concurrency
  behavior.** `src/radio_transport.cpp` `#include`s `pxt.h` directly
  (`uBit.radio`, `PacketBuffer`, `MicroBitEvent`) and has no host shim
  in `tests/host/` — building one would mean simulating CODAL's radio
  stack, well beyond this ticket's scope. State this explicitly rather
  than fabricating a test that doesn't exercise the real hazard.
  Verify by code review: confirm `sending_` is set/cleared on every
  path, confirm both call sites (`emitLine()`'s retry,
  `RadioSink::write()`'s silent-drop) handle the bool return the way
  the Acceptance Criteria describe.
- Ticket 005's Phase C bench checkpoint is where this guard's real
  behavior gets its first live exercise (radio traffic under load,
  concurrent with an `emitLine()` call) — note in that ticket's handoff
  checklist to watch for unexpected radio silence under contention.
- **Verification command**: `uv run pytest` is not applicable to this
  ticket's own change (no host-testable surface touched); run the
  existing full scoped suite (`uv run pytest tests/host/`) only to
  confirm this ticket introduced no incidental regression elsewhere
  (it should report zero collected changes relevant to this ticket).

**Documentation updates**: update `radio_transport.h`'s own header
comment (currently describes single-fiber-only usage as an invariant)
to describe the new two-caller-with-a-guard reality instead of leaving
the old single-caller claim to go stale.
