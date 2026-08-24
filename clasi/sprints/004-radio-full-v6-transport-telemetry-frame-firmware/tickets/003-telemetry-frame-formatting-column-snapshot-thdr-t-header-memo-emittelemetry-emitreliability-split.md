---
id: '003'
title: 'Telemetry frame formatting: Column/Snapshot, thdr/t, header memo, emitTelemetry/emitReliability
  split'
status: in-progress
use-cases:
- SUC-001
- SUC-003
- SUC-004
depends-on:
- '001'
github-issue: ''
issue: radio-speaks-full-v6-and-v6-gets-its-telemetry-frame.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Telemetry frame formatting: Column/Snapshot, thdr/t, header memo, emitTelemetry/emitReliability split

## Description

Add the wire-format mechanics for protocol v6's telemetry frame
(`protocol.md` §5.2: `thdr <col>...` then `t <v>...`, space-separated,
lowercase, unsequenced — no `#id`) to `src/wire_handler.{h,cpp}`. This
ticket is PURE FORMATTING: it takes a caller-supplied `Column`/
`Snapshot` (copied from the reference's shape,
`radio-robot-lib/src/protocol/adapter.h:113-139`) and prints it — it has
no opinion on what a column means, needs no real robot state, and is
fully testable against a hand-built `Column[]` array. The adapter-side
projection that actually produces a meaningful `Snapshot` from live
robot state is ticket 004's separate scope, deliberately split out
(different tests, different failure modes: this ticket's bugs are
formatting/ordering bugs; ticket 004's are unit-scale bugs).

Split today's argument-less `emitTelemetry()` into `emitTelemetry(const
Snapshot&)` (thdr-if-due, then `t`, then calls `emitReliability()`
internally — mirroring the reference's own combined
`ProtocolHandler::emitTelemetry(snapshot)`) and `emitReliability()`
(today's ack/nack keepalive, unchanged body, callable standalone so the
keepalive survives `TLM OFF`). Update BOTH of `protocol.cpp`'s handler
instances' call sites (ticket 001 added the second one) to the new
split API — but since `WireAdapter::telemetryEnabled()`/
`buildSnapshot()` do not exist until ticket 004, this ticket's
`protocol.cpp` change is behavior-preserving: always call
`emitReliability()` on both handlers, exactly as today, so telemetry
still emits ZERO `t` frames in production until ticket 004 lands the
real projection. This keeps the sprint bisectable — every ticket leaves
a compiling, behaviorally-sane build.

## Acceptance Criteria

- [x] `src/wire_handler.h` gains `struct Column { const char* name =
      ""; int32_t value = 0; bool hex = false; };` and `struct Snapshot
      { const Column* columns = nullptr; size_t count = 0; };`,
      matching the reference's shape and doc comments.
- [x] `WireHandler::emitTelemetry()` becomes
      `emitTelemetry(const Snapshot& snapshot)`: emits `thdr` (if due),
      then `t`, then calls `emitReliability()` — in that order, as three
      separate `Sink::write()` calls (never concatenated into one).
- [x] `WireHandler::emitReliability()` is a new public method carrying
      today's `emitTelemetry()` body verbatim (the `gapOutstanding_` ?
      nack : ack logic) — callable with no `Snapshot` at all.
- [x] Header memo: `headerChanged()`/`rememberHeader()` compare count,
      names, AND hex-ness (a lazy memo that only compares
      names/count misses a hex-ness-only flip); state is a COPY
      (`kMaxHeaderColumns=40`, `kMaxHeaderNameBytes=16` — column names
      never approach this, existing names are ≤6 chars), not a
      borrowed pointer into the caller's `Snapshot`.
- [x] A 20-frame forced refresh: independent of whether the column set
      changed, a fresh `thdr` goes out at least once every 20 calls to
      `emitTelemetry(snapshot)` — a per-instance frame counter, reset
      whenever `thdr` is emitted for any reason.
- [x] All formatting happens into a `WireHandler` MEMBER buffer, never
      a stack local (this class already has `lineBuf_`; either reuse it
      if its lifetime/size allow, or add a dedicated member — do not
      introduce a stack array in `emitTelemetry`/`emitReliability`'s own
      frames).
- [x] `snprintf` (not `std::snprintf`) is used for all new formatting;
      no `%f`/float printf anywhere — every column value is an already-
      scaled integer; `hex` columns print lowercase hex with no `0x`
      prefix (e.g. `%x`), everything else signed base-10 (e.g. `%ld`).
- [x] `src/protocol.cpp`'s two handler call sites are updated to the
      split API; production behavior is UNCHANGED by this ticket alone
      (both handlers call only `emitReliability()`; zero `t` frames go
      out in production until ticket 004).

## Implementation Plan

**Approach**: Port the reference's `headerChanged()`/`rememberHeader()`/
`emitHeader()`/`emitFrame()`/`emitTelemetry()` shape
(`radio-robot-lib/src/protocol/protocol_handler.cpp:1003-1092`) onto
this project's `WireHandler`, adjusted for the `emitReliability()` split
this project's own `TLM OFF` requirement needs (the reference's version
always emits telemetry+reliability together; this project needs the
reliability half callable alone).

**Files to modify**:
- `src/wire_handler.h`: add `Column`/`Snapshot`; declare
  `emitTelemetry(const Snapshot&)`, `emitReliability()`,
  `headerChanged()`, `rememberHeader()`; add header-memo state
  (`headerNames_[kMaxHeaderColumns][kMaxHeaderNameBytes]`,
  `headerHex_[kMaxHeaderColumns]`, `headerCount_`,
  `everEmittedHeader_`, a frame counter for the 20-frame refresh).
- `src/wire_handler.cpp`: implement the above; keep the existing
  ack/nack body verbatim inside the new `emitReliability()`.
- `src/protocol.cpp`: change both `wireHandler_.emitTelemetry()` /
  `wireHandlerRadio_.emitTelemetry()` calls to
  `wireHandler_.emitReliability()` / `wireHandlerRadio_.emitReliability()`
  (temporary, behavior-preserving — ticket 004 changes this again to the
  real conditional).

**Testing plan** (fully host-testable, no robot/adapter state needed —
extend `wire_grammar_shim.cpp` with `wgEmitTelemetry`-equivalent
functions taking a hand-built column array, or a small parallel
ctypes surface):
- `thdr` on frame 1, not frame 2 (unchanged columns).
- `thdr` re-emitted on: count change; name change; hex-ness-only change
  (same names/count, one column's `hex` flips) — the lazy-memo trap
  called out explicitly in the issue.
- `thdr` re-emitted at frame 20 with no other change.
- Byte-exact ordering: `thdr` -> `t` -> ack/nack, as three distinct
  `Sink::write()` calls (assert on the `RecordingSink`'s call log, not
  just the concatenated buffer, so this is verifiable independent of
  whether writes get concatenated in a real transport).
- `emitReliability()` alone (no `Snapshot` involved) emits no `t` and no
  `thdr` — only the ack/nack line, matching today's behavior exactly.
- The header memo stores a COPY: mutate the caller's original `Column`
  array's `name` pointer target after a `thdr` emission and confirm the
  NEXT `headerChanged()` check is unaffected (it must compare against
  the remembered copy, not the caller's live array).
- **Verification command**: `uv run pytest tests/host/test_wire_grammar.py tests/host/test_wire_reliability.py` plus whatever new test file this ticket adds (scoped; full suite runs once at `close_sprint`).

**Documentation updates**: `wire_handler.h`'s existing doc comment on
`emitTelemetry()` (currently states it takes no Snapshot/Column payload
and defers that to "a later ticket") should be updated to describe the
now-real split, so the comment does not describe a future ticket that
has already landed.
