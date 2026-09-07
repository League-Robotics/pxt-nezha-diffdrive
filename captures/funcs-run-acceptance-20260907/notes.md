# FUNCS + RUN hardware acceptance — gopiv and vevov, 2026-09-07

First hardware run of the `FUNCS` verb and the `RUN <name> [arg...] #<id>`
cutover (commit d4d8e4e, fw **1.20260907.1**). Both boards were on the
farm, wheels on the bench: **no motion verb was sent at any point.**
`RUN gap` was chosen precisely because it emits a receipt and drives
nothing.

- **boards**: gopiv (magni, `2175407711`), vevov (hodr, `1198504156`) —
  identity from `HELLO`, read off silicon, not from the probe registry.
- **carriers**: farm USB serial daemon (`mbdeploy connect --remote`) and
  WiFi TCP (`tools/wifilink.py --tcp`, mDNS-resolved).
- **before**: gopiv ran an *unbaked* build (`id diffdrive unbaked unbaked
  gopiv`); vevov ran `1.20260906.2`.

## Results

| check | gopiv | vevov |
|---|---|---|
| flash to 1.20260907.1 | PASS | PASS (after one indeterminate flash, below) |
| WiFi joins, advertises `_robotlink._tcp` | PASS | PASS |
| WiFi TCP `PING`/`STATUS`/`ID` | PASS | PASS |
| `FUNCS` lists all 21 `onRun` names, in registration order | PASS (USB) | PASS (USB) |
| `RUN gap #n` dispatches into TypeScript | PASS both carriers | PASS both carriers |
| unregistered name refused `err 1` | PASS both carriers | PASS both carriers |
| oversize argument refused `err 3` | PASS | not repeated |
| cleartext `RUN:gap` no longer dispatches | PASS | not repeated |
| multi-line reply survives WiFi | **FAIL — see below** | **FAIL** |

## The listing is correct and complete over USB

`FUNCS #1` on gopiv returned `ack 1 0 none` followed by 21 `funcs` lines
— `clearestop abort tour straight cal fix arm probe gap seed seedxy goto
face pivot arc turnrate square diamond circle infinity snake` — exactly
`test/test.ts`'s `onRun()` bindings, in binding order, with the
signature field omitted as designed. vevov returned the identical 21.

`RUN gap #2` -> `ack 2 0 none` then `GAP:0`: the v6 verb reached the
TypeScript handler and produced its receipt. That is the whole cutover
working.

`RUN nosuchthing #3` -> `ack 3 0 none` then `err 1 #3`. The registry
check refuses an unlisted name at the wire, so the listing and the
allowlist cannot disagree.

`RUN turnrate 0123...49 #5` (50-char argument) -> `err 3 #5`: arguments
cross the seam and the joined text is length-checked against
`RunBridge::kTextBytes` before anything is queued.

`RUN:gap` (the old cleartext spelling) drew **no reply at all** and left
the sequence untouched — an unknown verb with no id is deliberately
silent. The carve-out is genuinely gone.

## BUG FOUND AND FIXED: junk bytes in every signature field

The FIRST gopiv flash of 1.20260907.1 returned every line as
`funcs <name> \xef\xbf\xbdc` — two junk bytes where the omitted
signature belongs. Cause: `run.ts` publishes `_registerRunName(name, "")`,
and `shims.cpp` decided emptiness by inspecting the `ManagedString`
`MSTR()` builds. `MSTR(s)` is `ManagedString(s->getUTF8Data(),
s->getUTF8Size())`, and at size 0 its `toCharArray()` is not a clean
`""`, so `signature[0] != '\0'` was true and the separator plus garbage
were emitted.

Fixed two ways: `registerRunName` now asks the PXT String its own
`getUTF8Size()`, and `RunRegistry::copyInto` drops non-printable bytes
outright, so no caller can put a control byte on the wire. Re-flashed
gopiv and re-ran: 21 clean `funcs <name>` lines, no signature field.
Pinned by `tests/host/test_run_registry.py::test_non_printable_bytes_*`
and `::test_a_signature_of_only_junk_*`.

## PRE-EXISTING BUG, NOT THIS CHANGE: WiFi truncates multi-line replies

A multi-line reply is cut off at **7 lines** over WiFi TCP. Attributed
by running the same command on both carriers, and by testing a verb this
change did not touch:

| command | USB serial daemon | WiFi TCP |
|---|---|---|
| `FUNCS` (21 registered names) | 21 lines | 7 lines |
| bare `GET` (31 config fields) | 31 lines | 7 lines |

Bare `GET` predates this work entirely, so this is the **WiFi transport**,
not `FUNCS`. And it is not the network: the carrier is TCP, which does
not lose data. The firmware throws the lines away itself.

MECHANISM, proven rather than inferred. `WifiLink::enqueueSend()`
(`wifi_link.cpp:775`) drops the NEWEST datagram once `txCount_ >=
kTxSlots`, and `kTxSlots = 8` (`wifi_link.h:121`). The AT engine sends
one CIPSEND per datagram over several fiber ticks while `execFuncs()`
writes all 22 lines (1 ack + 21 funcs) into the ring in one synchronous
loop, so lines 9..22 find it full.

Bracketing ONE `FUNCS` between two `DBG:wifi` reads on gopiv:

```
drop before : 0
drop after  : 14
delivered   : 1 ack + 7 funcs = 8
```

8 delivered is exactly `kTxSlots`; 22 - 8 = 14 dropped, matching the
counter to the unit.

Serial made the opposite choice and serial is right:
`SerialTransport::writeLine()` uses `SYNC_SLEEP`, which BLOCKS when
CODAL's TX ring fills and then continues, losing nothing. "Drop, never
block" is correct for a telemetry frame (a stale pose is worthless, and
`purgeTelemetry()` exists for it) and wrong for a command reply, which
is the answer to a question a host just asked.

Note the naive fix DEADLOCKS: the protocol fiber both fills the ring
(inside `execFuncs`) and drains it (`serviceWifi()`), so a blocking wait
in the fill path waits on a drain that cannot run until it returns. The
issue writes up the two viable directions.

This matters more than a cosmetic truncation: `FUNCS` is an allowlist,
and a host reading 7 of 21 names as the whole list is the precise failure
`protocol.md`'s FUNCS section refuses for the rest-of-line reply shape.
Over WiFi the same failure arrives through the transport instead.
Filed as `clasi/issues/wifi-transport-truncates-multi-line-replies.md`.
**Use USB (or radio) for `FUNCS` and bare `GET` until it is fixed.**

## Operational note: an indeterminate farm flash

vevov's first flash timed out mid-Programming
(`Timeout reading from probe ... vevov WAS ERASED AND NOW HAS NO
FIRMWARE`). This is the known indeterminate case: not rolled back, cured
by an immediate re-flash, which succeeded on the first retry. gopiv's
flashes were clean. Also: `make_deploy.py --flash` failed for a farm
board and suggested the local DAPLink fallback, which does not apply to a
remote node; `mbdeploy deploy --remote <name> --hex <path>` is the
working path.
