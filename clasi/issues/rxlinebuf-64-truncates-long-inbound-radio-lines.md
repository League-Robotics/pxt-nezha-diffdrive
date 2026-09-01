---
status: pending
---

# rxLineBuf_[64] silently truncates inbound radio lines over 64 bytes

Found 2026-08-31 during the radio-wedge corruption hunt (source
reading, this repo at b2305e8; full context in
`reports/radio-wedge-analysis-20260831.md`, Addendum).

## The defect

`Protocol` reads inbound radio lines through
`uint8_t rxLineBuf_[64]` (`src/comms/protocol.h:269`), passed to
`RadioTransport::tryReceiveLine(rxLineBuf_, sizeof(rxLineBuf_), ...)`.
`tryReceiveLine()` (`src/comms/radio_transport.cpp:~175`) clamps to the
caller's capacity:

```c
size_t len = rxLen_;
if (len > outCap) len = outCap;   // silent truncation
```

Meanwhile the transport itself accepts and buffers lines up to
`kMaxLineBytes` (~247, sized for the 250-byte fleet packet,
`rxLine_[kMaxLineBytes]` in `radio_transport.h`), and the RX path goes
out of its way to REJECT over-length frames rather than truncate them
(`radioRxLineFits()`'s whole design). That care is then undone one
layer up: any radio line between 65 and ~247 bytes arrives intact at
the transport and is silently cut to 64 bytes before parsing.

This is a memory-SAFE bug (no overflow — the clamp is correct), but a
correctness trap: a truncated command can still parse. A long `SET`
with a value cut mid-digits, a `TLM` spec losing its trailing fields,
or a v6 line losing its `#<id>` suffix (which downgrades it to `#0` and
gets it silently dropped as a stale retransmit — see
`.claude/rules/playfield-testing.md`) all fail in ways that look like
robot or link faults, not like what they are.

USB serial has its own line buffer and is unaffected; this is
radio-path only.

## Fix shape

Either size `rxLineBuf_` to the transport's `kMaxLineBytes` (one
constant, shared), or make `tryReceiveLine()` reject-and-count on
`len > outCap` the same way `radioRxLineFits()` rejects over-length
frames — matching the transport's existing no-truncate philosophy. A
host-side test can pin it: send a >64-byte line over the radio path and
assert it is either handled whole or rejected with the drop counter
incremented, never parsed truncated.
