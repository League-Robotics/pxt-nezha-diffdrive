---
status: pending
sprint: '032'
---

# Protocol diet: RunBridge object, radio enable on the transport, one routeLine, one sink, one owner flag; delete vestigial two-writer guards

Priority: **Medium** · Source: [code review 2026-09-02](../../../docs/code-review/2026-09-02/review.md)

Findings: CM-05, CM-11, CM-12, CM-13, CM-14 ([comms](../../../docs/code-review/2026-09-02/raw/comms.md)). Triage #12.

## Description

`Protocol` carries a separable cleartext RUN bridge (dedupe, ring, bypass,
current-text, dispatch), three scattered radio-enable gates that belong
on `RadioTransport` (which self-enables lazily), copy-pair serial/radio
poll branches, two identical sinks that strip a trailing byte blind, four
`nowMicros()/1000` conversions, and `motionOwner_`/`jobOwnsMotion_`
storing one fact twice. Both transports' two-writer guards and retries
are vestigial since the emit ring made the protocol fiber the sole
producer; their comments still describe a TS-fiber writer, and the real
second serial writer (MakeCode's own `serial.writeLine`) bypasses them.

## Remedy

- `RunBridge` (host-portable like `RunQueue`): `offer(text, len, nowMs)`,
  `dispatchOne()`, `currentText()`; dedupe and bypass rules host-tested.
- `RadioTransport::enable()/enabled()`; `sendLine`/`tryReceiveLine` return
  false while disabled; the three gates go.
- `routeLine(handler, buf, len)`; one `TransportSink`; both transports take
  the already-terminated line so the strip-and-re-append round trip goes.
- One `nowMs()`; one owner flag.
- Delete `sending_` and the retries, keep drop counters; rewrite the four
  comment blocks to "single writer: the protocol fiber".

## Acceptance

- `Protocol` is composition plus `run()`; the RUN bridge has its own host
  tests.
