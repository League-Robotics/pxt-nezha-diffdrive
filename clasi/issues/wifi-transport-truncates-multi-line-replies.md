# WiFi truncates every multi-line reply at 7 lines

**Found:** 2026-09-07, gopiv (and vevov) on fw 1.20260907.1.
**Artifact:** `captures/funcs-run-acceptance-20260907/notes.md`.
**Not caused by the FUNCS/RUN change** — bare `GET` predates it and fails
identically.

## Symptom

Any reply longer than about seven lines is cut off over WiFi TCP. The
same command on the farm USB serial daemon returns the whole thing:

| command | USB serial daemon | WiFi TCP |
|---|---|---|
| `FUNCS` (21 registered names) | 21 lines | **7** |
| bare `GET` (31 config fields) | 31 lines | **7** |

Raising the read window does not help — 8 s gives the same 7 lines, so
this is loss, not impatience.

## Mechanism

`DBG:wifi`'s own counter names it. After one `GET` burst gopiv reported:

```
DBG:wifi state=5 ip=192.168.1.215 peer=-:0 tcp=1/1 to=0 restarts=0
         sent=61 rx=11 drop=76 mdns=6/1
```

and the first `FUNCS` read showed `drop=14` — exactly the 21 - 7 lines
missing. `WifiLink::sendLine()` drops (never blocks) when the AT state
machine is mid-command, which is fine for the one-line replies every
other verb emits and lossy for a burst written back-to-back inside a
single `execFuncs()`/`execGet()` loop.

## Why it matters more than it looks

`FUNCS` is an **allowlist**. A host reading 7 of 21 names as the whole
list is precisely the failure `protocol.md`'s FUNCS section rejects the
rest-of-line reply shape for — one long line that silently truncates past
the 240-byte cap. The line-per-entry shape defeats the cap but not a
lossy transport, so over WiFi the same wrong answer comes back by another
route, and nothing in the reply says it is partial.

Bare `GET` has the same shape and the same exposure: a host that reads
the field list to decide what it may `SET` sees a short list.

## Workaround

Use the USB serial daemon or radio for `FUNCS` and bare `GET`. Every
single-line verb (`PING`, `STATUS`, `ID`, `RUN <name>`, the motion verbs)
is unaffected and works normally over WiFi — verified on both boards.

## Fix directions, not yet chosen

- Make `sendLine()` block (or retry with backoff) while the AT command is
  in flight, rather than dropping. Bounded by the emit path already being
  single-producer on the protocol fiber.
- Or pace multi-line emissions: hand them to the existing `EmitQueue` and
  drain one per fiber tick, so a burst becomes a stream.
- Either way `drop` should be surfaced somewhere a host can read
  in-band, so a truncated dump is at least detectable. Today the only
  hint is a `DBG:wifi` line a tool may not be reading.
