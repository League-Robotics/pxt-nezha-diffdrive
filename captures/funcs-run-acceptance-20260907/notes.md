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
not `FUNCS`. `DBG:wifi` names the mechanism directly — after one `GET`
burst gopiv reported `state=5 ip=192.168.1.215 tcp=1/1 to=0 restarts=0
sent=61 rx=11 **drop=76**`. The first FUNCS read showed `drop=14`, and
21 - 7 = 14 exactly.

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
