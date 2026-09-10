---
status: pending
---

# A WiFi join failure does not say why: wrong password and out-of-range AP look identical

## Description

MEASURED gopiv 2026-09-09,
`nezha-robot-template/captures/wifi-calibration-20260909/notes.md`: a
board sat in this state for hours, across a reflash, while nobody could
tell what was wrong with it.

```
DBG:wifi state=2 ip=- peer=-:0 tcp=0/0 to=4 restarts=2783 sent=0 rx=0
    drop=0 mdns=0/0 cmd=AT+CIPDINFO=1 reply=..OK.. credsrc=1 trunc=0
```

Everything in that line is healthy except the outcome. `reply=..OK..`
says the Ai-WB2 module is present, powered and answering AT. `credsrc=1`
says a program supplied credentials. `state=2` is `kJoin` and
`restarts=2783` is the whole configure/join sequence tearing itself down
and starting over, forever.

The actual cause was a **wrong password** -- the consumer project's
`test/secrets.ts` had drifted from the fleet's
`config/wifi_secrets.json`, same SSID and same length, different string.
Nothing in the firmware's output narrowed it down, so the diagnosis came
from fingerprinting two secrets files against each other on the host.

These all present identically today -- `state=1/2` with a climbing
`restarts`:

- wrong password
- SSID not in range (robot parked too far from the AP)
- SSID exists but is 5 GHz-only (the Ai-WB2 is 2.4 GHz)
- AP down

## The module already knows, and the code already sees it

`WifiLink::serviceJoin()` (`src/comms/wifi_link.cpp:565-571`) sends
`AT+CWJAP="ssid","pw"` and waits for `OK`. Anything else falls through
to `enterBackoff()`, whose own comment names the discarded evidence:

```cpp
enterBackoff();  // +CWJAP:<code>/ERROR -- AP not up yet, wrong SSID, ...
```

The `+CWJAP:<code>` line is in the reply buffer at that moment and is
thrown away. Per the ESP-AT / Ai-WB2 vendor documentation the codes are
1 = connection timeout, 2 = wrong password, 3 = cannot find target AP,
4 = connection failed. **UNVERIFIED on this hardware** -- read from the
vendor's AT command set, not measured; a first implementation should log
the raw code and confirm that a deliberately wrong password really does
return 2 on the Ai-WB2-12F before any text is mapped onto the numbers.

## Proposed resolution

1. `WifiLink`: parse the `+CWJAP:` failure code where `serviceJoin()`
   currently falls into `enterBackoff()`, store it (`lastJoinError_`),
   and expose it with a getter. Keep the raw number; do not translate.
2. `Protocol::emitWifiDebug()` (`src/comms/protocol.cpp:396`): add one
   field, e.g. `join=<code>` (`-` when there has been no failure), to
   the existing `DBG:wifi` line. Check the `wifiDbgBuf_` budget -- that
   line is already long.
3. Host tests: extend the `WifiLink` host tests with a scripted join
   that answers `+CWJAP:2` and assert the code is retained across the
   backoff and reported.
4. Only after (1) is confirmed on hardware, consider mapping the code to
   a word in the debug line (`join=2/badpw`). A wrong mapping is worse
   than a bare number.

The point is not prettier logs. It is that one `DBG:wifi` line should
tell a bench operator whether to fix the credentials or move the robot,
which today takes a host-side investigation of files the firmware cannot
see.

## Affected code

- `src/comms/wifi_link.cpp` -- `serviceJoin()`, `enterBackoff()`
- `src/comms/wifi_link.h` -- new stored code + getter
- `src/comms/protocol.cpp` -- `emitWifiDebug()`, `wifiDbgBuf_` sizing
- host tests for the WiFi link state machine

## Related

- `nezha-robot-template/docs/wifi.md` -- the host-side fingerprint
  recipe this issue exists to make unnecessary
- `captures/fleet-flash-20260904/gopiv-wifi-listen.log` -- the *other*
  failure shape (module silent: `reply=` empty), which this line does
  already distinguish
