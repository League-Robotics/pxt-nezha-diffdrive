---
status: in-progress
sprint: '004'
tickets:
- 004-006
---

# Serial transport: 128 B RX ring vs 240 B lines; unserialized two-fiber TX

Priority: **Medium**, but **time-sensitive: amends sprint 004 ticket 002**
— code review 2026-08-23, R-19 + R-20 (WIRE-03 + WIRE-04; CONFIRMED).

1. **RX ring is v5-sized (R-19)**: `serial_transport.cpp:24` still
   allocates 128 bytes while v6 lines grew to 240 (`kMaxLineBytes`). During
   wire-driven motion the protocol fiber drains only every ~24 ms
   (`shims.cpp:526-542` self-pacing) ≈ 276 B/window at 115200 baud: a
   near-max line plus anything else in the window drops bytes, and
   reliability-layer resends re-enter the same window. Size the ring ≥ 2×
   max line.
2. **TX unserialized (R-20)**: `emitLine` (TS fiber) and the protocol
   fiber's replies/keepalives write one serial port with no guard, and
   `send()` return codes are ignored — result lines interleave or drop
   silently (drop-vs-block depends on CODAL mode; both are failures).

**Sprint-004 conflict**: ticket 002's acceptance criteria explicitly declare
the serial path needs no concurrency guard — contradicted by R-20. The AC
must be amended before the ticket executes; the radio half of the TX
concern is already ticket 002's scope.

## What to do

- Amend 004-002's AC (serial TX serialization in scope, or a follow-on
  ticket in the same sprint).
- Resize the RX ring; add a host test that replays a max-length line
  mid-motion window if the harness can express it.
- Check `send()` returns on both transports; count drops in a DIAG ordinal.
