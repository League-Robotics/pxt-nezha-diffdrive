---
id: '001'
title: 'Single serial/radio producer: Protocol-owned emit queue'
status: open
use-cases:
- SUC-001
depends-on: []
github-issue: ''
issue: concurrent-serial-writers-wedge-the-uarte-in-both-directions.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Single serial/radio producer: Protocol-owned emit queue

## Description

`Protocol::emitLine()` (`src/comms/protocol.cpp`) currently writes
`transport_.writeLine()` and `radioTransport_.sendLine()` directly, and
is called from whatever fiber a `RUN:`-with-payload dispatch runs on —
a fiber other than `Protocol::run()`'s own. That is a second concurrent
producer into codal's `NRF52Serial` UARTE driver, which is not safe
against two producers: `putc()` spins on a non-atomically-set
`is_tx_in_progress_` flag with interrupts enabled and DMAs from a
stack-local buffer, so two near-simultaneous `STARTTX` triggers can
leave the UARTE stopped in both directions, permanently, with no fault
and no self-recovery (only a debugger halt/resume clears it). Measured
on tigez 2026-09-02: `RUN:z` (one payload byte, unbound name) wedges
the port 100% of the time; `RUN:` with zero payload never does. Full
mechanism, bisect, and hardware evidence:
`clasi/issues/concurrent-serial-writers-wedge-the-uarte-in-both-directions.md`.
This is also the confirmed root cause of
`cleartext-run-hangs-the-link-under-active-telemetry.md` (closed by
ticket 002 of this sprint, once this fix is hardware-confirmed).

Fix: make the protocol fiber the single producer for both transports.
`Protocol::emitLine()` stops touching `transport_`/`radioTransport_`
directly — it clips the line to `RadioTransport::kMaxPayloadBytes`
exactly as before, copies it into a new `Protocol`-owned ring
(`comms/emit_queue.h`, a header-only `EmitQueue<Slots, Bytes>` in the
same style as sprint 026 ticket 002's `run_queue.h`/`RunQueue`), and
returns. The old body — serial write, then the radio mirror with its
existing `fiber_sleep(2)`-and-retry-once policy — becomes a private
`emitLineNow()`, called only from a new private `drainEmitQueue()`.
`Protocol::run()`'s fiber loop calls `drainEmitQueue()` once at the top
of every pass, before polling serial/radio RX, draining every
currently-queued line in FIFO order. `SerialSink::write()`/
`RadioSink::write()` (the v6 wire stack's own reply/telemetry path) are
**unchanged** — they already run only on the protocol fiber and were
never part of this race.

This exact restructuring was already implemented ad hoc and
hardware-verified on tigez before this ticket (soak test: 10
alternating commands, 15 reply lines, 0 reboots, port alive
throughout — see the issue's own "Fix — and it is sprint 026 ticket
003" section). This ticket lands it as reviewed, tested, documented
production firmware; it does not re-derive the fix. Hardware
acceptance itself (baseline reproduction, soak test, TLM-subscribed
cleartext RUN check) is ticket 002's job, not this one's — this ticket
is scoped to the restructuring and its host-testable ring.

Also add one `diagValue()` ordinal (29, the next free one after
sprint 026 ticket 002's 28) surfacing the new ring's `dropped()` count,
and one added sentence to `src/blocks/sim.ts`'s existing `emitLine()`
doc comment: student code inside an event handler must call
`diffDrive.emitLine`, never PXT's own `serial.writeLine`/
`serial.writeString` — those reach `uBit.serial` directly from
whatever fiber calls them, a path this extension cannot route through
the new queue from the inside (see the issue's own "Limit of the fix"
section).

## Acceptance Criteria

- [ ] `src/comms/emit_queue.h` — header-only, `<cstdint>`/`<cstring>`
      (or equivalent) only, no `pxt.h`, no CODAL types — a ring
      holding NUL-terminated line text (not a MessageBus slot index),
      with FIFO enqueue/drain and a saturating `dropped` counter that
      increments (never wraps) when `enqueue()` is called on a full
      ring.
- [ ] `Protocol::emitLine()` (`src/comms/protocol.cpp`) clips to
      `RadioTransport::kMaxPayloadBytes` (unchanged clip logic) and
      then only calls `emitQueue_.enqueue(...)` — it no longer calls
      `transport_.writeLine()` or `radioTransport_.sendLine()`
      directly.
- [ ] The old `emitLine()` body (serial write + radio mirror with its
      existing retry-once policy) is preserved verbatim as a new
      private `emitLineNow(const char* text, size_t len)`.
- [ ] A new private `drainEmitQueue()` calls `emitLineNow()` for every
      currently-queued line, in FIFO order, and is called once at the
      top of `Protocol::run()`'s fiber loop, before the serial/radio RX
      polling that follows it.
- [ ] A disassembly or source-level call-site census confirms exactly
      one call site reaches `SerialTransport::writeLine()`'s underlying
      `uBit.serial.send` for the emit path (`emitLineNow()`, called
      only from `drainEmitQueue()`, called only from `Protocol::run()`)
      and exactly one call site reaches `RadioTransport::sendLine()`
      for the same path — i.e. `emitLine()`'s own caller (any
      non-protocol fiber) can no longer reach either transport
      directly.
- [ ] `shims.cpp`'s `diagValue()` switch gains ordinal 29, returning
      the new ring's `dropped()` count (confirm 28 is still the
      highest in use before assigning — do not silently collide with
      an unrelated concurrent change).
- [ ] `src/blocks/sim.ts`'s existing doc comment above `emitLine()`
      gains the `diffDrive.emitLine` vs `serial.writeLine`/
      `serial.writeString` sentence described above.
- [ ] `uv run pytest` (full host suite) passes.
- [ ] No new comment names a sprint, a ticket, an `R-NN` code, or any
      `.md` filename — `test_archaeology_marker_budget.py` has zero
      slack. Describe the ring's mechanism in `emit_queue.h`'s own
      comments; put issue references in the commit message only.
- [ ] `pxt.json`'s `files[]` includes `src/comms/emit_queue.h` if
      `test_pxt_manifest_completeness.py` requires header-only files to
      be listed explicitly (check the actual rule, same as
      `run_queue.h` had to satisfy).
- [ ] Every yield this ticket's new code performs (if any — the ring
      itself should need none) goes through `vfpSafeSleep`/
      `vfpSafeYield`; `test_vfp_guard_source_pin.py` enforces this for
      any new `.cpp` that calls `fiber_sleep`/`schedule` directly.
- [ ] `src/core/diffdrive.{h,cpp}` is not touched (vendored, stays
      byte-identical).

## Implementation Plan

**Approach**: Write `emit_queue.h` first as a pure, host-testable ring
(mirroring `run_queue.h`'s own doc-comment shape: what it replaces, why
it's host-portable, what test exercises it). Prove FIFO order and
drop-counting with a host test before touching `protocol.cpp`. Then
restructure `Protocol::emitLine()`/`Protocol::run()` per the Acceptance
Criteria above, add the `diagValue()` ordinal, and add the `sim.ts` doc
sentence.

**Files to create**: `src/comms/emit_queue.h`,
`tests/host/test_emit_queue.py` (or equivalent), a C++11 syntax-check
translation unit if `test_cxx11_syntax_gate.py` requires one for a new
header-only module (check `run_queue_syntax_check.cpp`'s precedent).

**Files to modify**: `src/comms/protocol.h` (add the `emitQueue_`
member, the `drainEmitQueue()`/`emitLineNow()` private method
declarations), `src/comms/protocol.cpp` (`emitLine()`, `run()`),
`src/shims.cpp` (`diagValue()`'s new ordinal 29),
`src/blocks/sim.ts` (`emitLine()`'s doc comment), `pxt.json` (if
required per the acceptance criterion above).

**Files NOT to modify**: `src/comms/wire_adapter.*`,
`src/comms/wire_handler.*` (the v6 reply/telemetry path was never
racing and needs no change), `src/core/diffdrive.{h,cpp}` (vendored).

## Testing

- **Existing tests to run**: full `uv run pytest`, including any
  existing test that exercises `Protocol::emitLine()`'s clip-to-cap
  behavior today.
- **New tests to write**: `emit_queue.h`'s FIFO-order and
  drop-counting behavior under a host test that never needs CODAL; a
  regression test proving a burst larger than the ring's capacity
  increments `dropped` rather than corrupting a queued line's text.
- **Verification command**: `uv run pytest tests/host/test_emit_queue.py`
  (or wherever the new tests land) plus the full suite,
  `uv run pytest`.
