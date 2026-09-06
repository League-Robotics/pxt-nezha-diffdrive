---
id: '006'
title: RadioTransport enable/enabled, routeLine() + one TransportSink, delete vestigial
  two-writer guards
status: done
use-cases:
- SUC-003
depends-on:
- '005'
github-issue: ''
issue: protocol-diet-runbridge-radio-enable-routeline.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# RadioTransport enable/enabled, routeLine() + one TransportSink, delete vestigial two-writer guards

## Description

**Depends on ticket 005** (`RunBridge` extraction shrinks `protocol.cpp`
first, making this ticket's restructuring of the remaining poll/dispatch
loop easier to read and review — see sprint.md's Design Rationale for
the full reasoning).

**Verified 2026-09-05, all four findings still live:**
`radioEnabled_` is still a `Protocol`-owned field checked at three call
sites the source itself labels "Gate 1/2/3 of 3"
(`protocol.cpp:216,648,707,736`, plus `enableRadio()`); `sending_`
two-writer guards are present verbatim in both
`radio_transport.cpp:170-186` and `serial_transport.cpp:62-96`;
`routeLine()`/`TransportSink` do not exist anywhere in `src/comms/`.

- **Radio enable**: add `RadioTransport::enable()`/`enabled()`;
  `sendLine()`/`tryReceiveLine()` return `false` while disabled. Delete
  `Protocol::radioEnabled_` and all three "Gate N of 3" call sites;
  every caller asks `radioTransport_.enabled()` instead. Preserve the
  existing lazy-enable-on-first-use semantics (`ensureRadioReady()`) —
  this is a relocation of the gate, not a behavior change.
- **routeLine() + one sink**: add `routeLine(handler, buf, len)` and one
  `TransportSink` so both `SerialTransport` and `RadioTransport` hand an
  already-terminated line to the wire handler without the current
  strip-and-re-append round trip (each sink today strips the trailing
  `\n` `WireHandler` supplies, because its own transport appends its
  own). Replace the copy-pair serial/radio poll branches in `run()`
  with calls through this one path. Add one `nowMs()` replacing the
  four `nowMicros()/1000` conversions found in this reading.
- **Delete vestigial guards**: remove `sending_` and its retry logic
  from both `RadioTransport` and `SerialTransport` (the emit ring made
  the protocol fiber the sole producer — see sprint.md's Design
  Rationale for why this is a deletion, not a defensive-assert
  downgrade). Keep the drop counters (diag ordinal 26 for serial, and
  whatever radio's own counter is) — they answer a real, still-open
  question ("did a line ever drop") distinct from the two-writer race.
  Rewrite all four comment blocks currently describing a TS-fiber
  writer to state the single-writer reality (`src/DESIGN.md` §6/§8
  already document this in the present tense — mirror that language).

**Confirmed NO collision with sprint 031's unmerged branch** — this
ticket is confined to `comms/protocol.*`, `comms/radio_transport.*`,
`comms/serial_transport.*`, and the `comms/run_bridge.*` ticket 005
created; none of those are touched by 031's unmerged commits
(`motion_engine.*`, `segment.h`, `wire_adapter.cpp`).

## Acceptance Criteria

- [x] `radioEnabled_` and all three "Gate N of 3" comments/call sites
      are gone from `protocol.cpp`; `RadioTransport::enabled()` is the
      single source of that answer.
- [x] `routeLine()`/one `TransportSink` exist and both transports use
      them; the copy-pair poll branches in `Protocol::run()` are gone.
      (WiFi's identical fourth branch goes through the same two paths —
      see Implementation Notes.)
- [x] One `nowMs()` replaces the four `nowMicros()/1000` conversions.
      Named `Protocol::clockNow()` with a `// [ms]` trailing comment,
      per `.claude/rules/no-units-in-identifiers.md` (which postdates
      this ticket's text).
- [x] `sending_` and its retries are deleted from both transports; the
      drop counters remain; all four comment blocks are rewritten to
      state "single writer: the protocol fiber."
- [x] `RUN:abort`/`RUN:clearestop`'s existing bypass-the-queue,
      act-immediately behavior is unaffected by any of the above.
- [x] No change to `motion_engine.*`, `segment.h`, or `wire_adapter.cpp`.

## Implementation Notes

- **WiFi took the same two paths.** `serviceWifi()`'s inbound loop had
  the identical strip-and-`feed()`-and-re-`feed("\n")` shape with its
  own copy of the `RUN:` carve-out, and `WifiSink` was a third copy of
  the same blind-strip sink, so both went through `routeLine()` and
  `TransportSink` with serial and radio rather than being left as the
  one branch still written out by hand. No identifier in `wifi_link.*`
  was renamed (ticket 008's scope).
- **One behavioural difference, deliberate and documented.** The old
  sinks took the last byte off every written line without checking it
  was the terminator. `wireLineContentLength()` checks first, so a line
  arriving WITHOUT a terminator now keeps its last byte instead of
  losing a real one. Identical for every line that carries its `\n`
  (all of them today); this is the seam ticket 007's telemetry-terminator
  fix builds on, not that fix itself.
- **What is verified, and how.** The new host-portable seam
  (`src/comms/transport_sink.h`) is executed directly by
  `tests/host/test_transport_sink.py` — terminated, unterminated, CRLF,
  empty and maximum-width lines, plus the sink's own dispatch through
  the real `Wire::Sink&`. Everything else in this ticket —
  `RadioTransport`'s enable/enabled state machine, the guard deletion,
  `routeLine()`'s call sites, `clockNow()` — is in `pxt.h`-bound
  translation units that no host test can compile, and is **verified by
  code review only, first exercised live at the next bench session**,
  per `src/DESIGN.md` §6/§8's own standing convention for this layer.
  Nothing here was run on hardware; no MEASURED claim is made anywhere
  in this change. As an extra offline check the exact new NSDMI sink
  composition was compiled at `-std=c++11` against the real (pxt-free)
  transport headers in a scratch translation unit, which the C++11 gate
  cannot reach through `protocol.h`.

## Testing

- **Existing tests to run**: `tests/host/test_radio_transport_rx_capacity.py`
  and its shim (`radio_transport_rx_capacity_shim.cpp`) for whatever
  framing behavior is host-testable.
- **New tests to write**: extend the host-portable framing seam (or add
  one, following `radio_transport_rx_capacity_shim.cpp`'s precedent) to
  cover `routeLine()`'s terminator handling. Note `RadioTransport`/
  `SerialTransport`/`Protocol` themselves are not host-testable
  (`pxt.h`) — the enable/enabled state machine and the guard deletion
  are verified by code review, first exercised live at the next bench
  session, per `src/DESIGN.md` §6/§8's own standing convention. Do not
  claim a host test covers what it structurally cannot.
- **Verification command**: `uv run pytest tests/host/`
