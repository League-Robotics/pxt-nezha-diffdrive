---
status: pending
sprint: '024'
tickets:
- 024-001
- 024-003
---

# The reliability line free-runs at 20 Hz on the radio with no host

`ack`/`nack` are responses. The firmware emits them unsolicited every
50 ms on **both** carriers, from power-on, forever, whether or not any
host has ever spoken on that transport. On the radio that means the
robot transmits a packet on its own channel (group 10) twenty times a
second, addressed to nobody.

Sprint 022 makes this worse than it was when the emission was written.
Radio is a broadcast, the channel is now injected per-robot at deploy
time (`radio_transport.h`'s checked-in `kChannel = 4` is only the
un-baked default), and sprint 022's own problem statement records a
command on channel 4 being answered by a robot nobody was looking at.
Every powered robot sharing a channel now contributes its own 20 Hz
beacon to that air.

## The drift

Sprint 003 ticket 003 specified the periodic emission narrowly: a lost
`nack` "self-heals via the next **telemetry-piggybacked** reliability
line (`emitTelemetry` equivalent) **without any new timer**". Piggyback
on a stream a host explicitly subscribed to with `TLM` — that is a
response to something the host sent.

Sprint 004 built the real telemetry frame and split
`emitTelemetry()`/`emitReliability()`. The protocol fiber
([protocol.cpp:346-358](../../src/comms/protocol.cpp)) now reads:

```cpp
if (nowMs - lastEmitMs >= kReliabilityEmitPeriodMs) {   // 50 ms
  if (wireAdapter_.telemetryEnabled()) {
    ... emitTelemetry(snapshot) on both handlers
  } else {
    wireHandler_.emitReliability();        // serial
    wireHandlerRadio_.emitReliability();   // RADIO -- on air
  }
  lastEmitMs = nowMs;
}
```

`telemetryEnabled()` is false at boot, so the `else` branch is the
**normal** case: a free-running beacon, not a piggyback. It is
unconditional — there is no "has a host ever spoken on this transport"
gate, no "has anything changed" gate, and no bound on repeats.

## Why the earlier review cleared it

`docs/code-review/2026-08-23/raw/correctness-wire.md:166` looked right
at this and dismissed it: *"Boot keepalive stream (`ack 0 0 none` every
50 ms from power-on): S8.5 behavior, byte cost negligible at 115200."*
Correct at the time — the same review notes "radio cannot reach the v6
parser". Sprint 004 then put a second `WireHandler` behind `RadioSink`
([protocol.h:219-222](../../src/comms/protocol.h)) and nothing
re-examined the judgement. On radio the cost is not bytes at 115200,
it is **airtime on a shared channel, half-duplex**.

## Suspected feedback loop — needs measuring, not assuming

The nRF radio cannot receive while it transmits, and
`RadioTransport::onDatagram()` drops an inbound frame outright when the
previous line is still unconsumed
([radio_transport.cpp:69](../../src/comms/radio_transport.cpp)).
`RadioTransport::sendLine()` also silently returns false when
`sending_` is already set. A robot beaconing 20×/sec is therefore a
plausible **cause** of the lost inbound command that opens a sequence
gap — and a gap makes it beacon `nack` at the same rate forever, which
is exactly the state observed on 2026-08-26. That is a self-sustaining
failure, and the keepalive is on both sides of it.

Do not treat the loop as established. Measure it: RX success rate for a
fixed command burst with the free-running emission on vs. off.

## The stream has no consumers

Nothing in `tools/` reads it. The **only** reference to an `ack` line
anywhere in the host tooling is `arc_capture.py:161`, and it is a
filter that throws the line away. Its comment states the reason: the
beacon arrives looking like a reply to a command it is not a reply to,
so without the filter the tool's firmware-identity check
false-positives on it.

No tool reads `lastDone`/`lastDoneReason` off the beacon either —
completion is learned from `DBG:` receipts and `t` telemetry frames.
So the beacon's one unique payload has zero readers, and its existence
costs a workaround in a tool that would otherwise not need one.

## Required behaviour (stakeholder, 2026-08-26)

**One reliability line per inbound line, and none otherwise.** An idle
robot nobody has spoken to is silent. This is stricter than "bound the
repeats", and it is the right rule: `ack`/`nack` is a response, so it
needs a request.

1. Emit exactly one `ack`/`nack` in response to a received line. That
   is the whole reliability plane when telemetry is off.
2. Never emit on a transport that has received nothing since boot or
   the last `HELLO`.
3. With telemetry on, piggyback as sprint 003 originally specified —
   that stream is itself a host request (`TLM`), so it is a response.

### What this gives up, and why it is fine

Ticket 003's self-heal case was a **lost `nack`**: the host waits for a
reply that never comes. Under a pure request/response rule the host's
own retransmit draws a fresh nack, so the gap still heals — one round
trip later, driven by the host, which is where retransmit responsibility
belongs. `robotlink.send_until()` already implements exactly that loop.
The only case genuinely lost is a host that sends a command, loses the
reply, and then goes quiet forever without retrying — a host bug, not a
transport failure, and not something the robot should broadcast at 20 Hz
to cover.

Radio and serial may still deserve different tuning; the current code
gives them the same one.

## Related

- [[radio-link-wedges-on-a-sequence-gap-and-reconnect-cannot-heal-it]]
  — the host-side half of the same failure: once wedged, no tool in
  `tools/` can clear it.
