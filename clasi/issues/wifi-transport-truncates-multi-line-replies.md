# WiFi drops every reply line past the 8th

**Found:** 2026-09-07, gopiv and vevov, fw 1.20260907.1/.2.
**Artifact:** `captures/funcs-run-acceptance-20260907/notes.md`.
**Not caused by the FUNCS/RUN change** — bare `GET` predates it and fails
identically.

## This is not the network

The carrier is TCP. TCP does not lose data. Every missing line is thrown
away by our own firmware, on purpose, before it ever reaches a socket.

`WifiLink::enqueueSend()` (`src/comms/wifi_link.cpp:775`) is the whole
mechanism:

```cpp
if (txCount_ >= kTxSlots) {
  ++dropCount_;
  return false;  // drop NEWEST -- stale data is not worth a stall
}
```

`kTxSlots = 8` (`wifi_link.h:121`). The AT engine sends one `CIPSEND`
per datagram and needs several fiber ticks per round trip, while
`execFuncs()`/`execGet()` write their whole reply into the ring in one
synchronous loop. The 9th line onward finds the ring full and is
discarded.

## Measured, exactly

`FUNCS` on gopiv emits 22 lines (1 `ack` + 21 `funcs`). Bracketing a
single `FUNCS` between two `DBG:wifi` reads:

```
drop before : 0
drop after  : 14
delivered   : 1 ack + 7 funcs = 8
```

8 delivered = `kTxSlots` exactly. 22 - 8 = **14 dropped**, matching the
counter to the unit. Bare `GET` behaves the same way: 31 fields + 1 ack
over USB, 7 `get` lines + 1 ack over WiFi.

| command | USB serial | WiFi TCP |
|---|---|---|
| `FUNCS` (21 names) | 21 | 7 |
| bare `GET` (31 fields) | 31 | 7 |

Raising the read window does not help — 8 s gives the same 7. The lines
were never sent.

## Serial made the opposite choice, and serial is right

`SerialTransport::writeLine()` uses `SYNC_SLEEP`, which **blocks** (yields
the fiber) when CODAL's 255-byte TX ring fills, then carries on. Nothing
is lost; backpressure is applied by waiting. That is why USB returns all
31 lines and WiFi returns 7.

"Drop, never block" is the correct policy for a *telemetry frame* — a
stale pose is worthless, and `purgeTelemetry()` exists for exactly that.
It is the wrong policy for a **command reply**, which is the answer to a
question a host just asked and cannot be re-derived.

## Why it matters more than a cosmetic truncation

`FUNCS` is an **allowlist**. A host reading 7 of 21 names as the whole
list is precisely the failure `protocol.md`'s FUNCS section rejects the
rest-of-line reply shape for — one long line silently cut at the
240-byte cap. The line-per-entry shape defeats the cap but not a lossy
queue, so over WiFi the same wrong answer arrives by another route, and
**nothing in the reply says it is partial**. Bare `GET` has the same
exposure: a host that reads the field list to decide what it may `SET`
sees a short list.

## The naive fix DEADLOCKS — read this before writing one

`sendLine()` cannot simply block until a slot frees. The protocol fiber
both **fills** the ring (inside `execFuncs`, inside `feed()`) and
**drains** it (`serviceWifi()` in its own loop). A blocking wait inside
the fill path waits for a drain that can only run after the fill returns.

So the options are:

1. **Pump while enqueuing** — service the AT state machine from inside
   the full-ring path so the queue drains under the emitter. Correct in
   principle, reentrancy-delicate: it re-enters the WiFi service loop
   from inside a wire command's own execution.
2. **Make multi-line emission yield between lines** — hand a dump to the
   existing `EmitQueue` and let the fiber loop drain one per tick, so a
   burst becomes a stream. Changes when a reply completes, not whether.
3. **Bigger ring** — moves the cliff (22 lines today, more tomorrow) and
   does not fix it. Not a fix.

(1) or (2), and it is a real design decision about reply semantics, not
a constant to bump.

Whatever is chosen, `dropCount_` should also be readable **in band** so a
truncated dump is detectable by the host. Today the only hint is a
`DBG:wifi` line a tool may not be reading, which is how this survived
until a 22-line reply existed to expose it.

## Workaround until then

Use the USB serial daemon or radio for `FUNCS` and bare `GET`. Every
single-line verb — `PING`, `STATUS`, `ID`, `RUN <name>`, the motion verbs
— is unaffected and verified working over WiFi on both boards.
