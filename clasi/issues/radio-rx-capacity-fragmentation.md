---
status: pending
sprint: '010'
---

# Radio RX is one 64-byte fragment, so most of v6 cannot be received over radio

Priority: **High** — code review 2026-08-23, R-27 / DES-01 (CONFIRMED with
nuance). Sprint 004 amended its plan to describe this hazard accurately
and explicitly declared the capacity work **out of scope**; this issue is
that deferred work, filed so it does not vanish with the sprint.

## The gap

`RadioTransport`'s RX path is a single 64-byte slot (`rxLine_[64]`,
`radio_transport.h:139`) with no multi-fragment reassembly, against v6
lines specified up to 240 bytes (`WireHandler`/`SerialTransport`'s
`kMaxLineBytes = 240`). Its TX bound is a third number:
`kMaxPayloadBytes = 200` (`radio_transport.h:126`), never raised when
serial went 200→240 in sprint 003.

So after sprint 004 makes radio speak the full v6 *grammar*, radio still
cannot carry most of it:

- **Inbound**: a command line longer than 64 bytes does not fail cleanly.
  It is clamped to a parseable prefix — which can execute as a
  *different, shorter, legal command* — or is silently dropped. Executing
  a truncation of what the host sent is the dangerous half; a dropped
  line is merely invisible.
- **Outbound**: a legal 201–240-byte emitted line is mirrored intact on
  serial and truncated on radio, so the two transports disagree about
  what the robot said. (Precision from verification: radio's own clip is
  currently unreachable because `emitLine` pre-clips at 200 — see
  `wire-constants-single-source.md`, which fixes the *constants*; this
  issue is about the *capacity*.)

Today's bench `RUN:` lines sit well under 64 bytes, which is why this has
not bitten yet. The v6 telemetry frame, `GET`/`SET` replies, and `HELP`
output are the lines that will.

## What to do

Decide and implement one of:

1. **Multi-fragment RX reassembly** — sequence/continuation framing, a
   partial-line timeout so a lost middle fragment cannot wedge the
   reassembler, and a bounded reassembly buffer. Costs RAM and protocol
   surface; makes radio a real peer of serial.
2. **Explicit, loud rejection** — keep one fragment, but never execute a
   truncated line: detect over-length input at the fragment boundary and
   answer a defined `err` rather than clamping to a parseable prefix.
   Cheap, honest, and leaves long-line verbs serial-only by contract.

Whichever is chosen, the truncate-into-a-different-legal-command hazard
must be closed, and the three capacity numbers (radio RX 64, radio TX
200, wire 240) must end up either equal or documented as deliberately
unequal with the consequence stated at each site.

## Verification

- A host test drives an over-length line into the radio RX path and
  asserts the chosen behavior (reassembled whole, or rejected with the
  defined error) — never "executed as a shorter command".
- A bench check with a real >64-byte v6 line over radio, since this is
  precisely the case no host double has ever exercised.

## Related

- Sprint 004 (`radio-speaks-full-v6-and-v6-gets-its-telemetry-frame.md`)
  makes radio a full v6 transport at the grammar level and documents this
  capacity limit as a known, unaddressed gap — read its Out of Scope
  entry on RX capacity/fragmentation before planning this.
- `wire-constants-single-source.md` (sprint 008) unifies the line-cap
  *constants* and fixes `radio_transport.h`'s false "equals
  SerialTransport's" parity comment. That work and this work touch the
  same lines; sequence them deliberately.
