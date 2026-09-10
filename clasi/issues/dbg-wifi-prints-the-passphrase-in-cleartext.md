---
status: pending
---

# `DBG:wifi` prints the WiFi passphrase in cleartext, on every carrier

## Description

MEASURED gopiv 2026-09-09,
`captures/wifi-join-codes-20260909/` (the `cmd=` field is redacted in
that capture; it was not redacted on the wire):

```
DBG:wifi state=6 ... cmd=AT+CWJAP="Busboom Mesh","<PASSPHRASE VERBATIM>"
    reply=+CWJAP:2....ERROR credsrc=0 trunc=0 join=2
```

`Protocol::emitWifiDebug()` (`src/comms/protocol.cpp:396`) reports
`WifiLink::lastCommand()` verbatim. The last command during a join
attempt is `AT+CWJAP="<ssid>","<password>"`
(`src/comms/wifi_link.cpp:559-561`), so the passphrase goes out in
cleartext -- and `emitLine()` fans out to **serial, the radio link, and
the WiFi link itself**, so it reaches anyone within radio range or on
the LAN, not just someone holding the USB cable.

This is not a hypothetical: it is how the string above was obtained,
from a routine `DBG:wifi` line on a board on the playfield.

## Scope: which builds leak

| build path | leaks? |
|---|---|
| `tools/make_deploy.py` (the FLEET path -- every robot) | **yes** |
| `nezha-robot-template` (the calibration image) | no -- `scripts/redact-wifi-trace.sh` patches `pxt_modules/` on EVERY build, fatally on failure, precisely because this leaked once before |

So the consumer project already knows about this defect and works
around it in its own build script. The extension itself -- the thing
every other consumer depends on -- still has it, and the fleet's own
deploy path has no equivalent patch. A workaround living in one
downstream project is not a fix.

## Why it matters beyond the obvious

Sprint 038 is adding a credential store whose whole premise is that a
passphrase never leaves the robot. Every ticket in it carries an
acceptance criterion that no passphrase appears in a reply, a `DBG:`
line, or a telemetry frame. That criterion is already violated by
existing code, on a line the sprint is actively extending. Fix it in
the sprint rather than shipping a store that guards the front door
while this is open.

## Proposed resolution

Redact at the source rather than at the sink: `WifiLink` should never
store the passphrase in the buffer `lastCommand()` returns.

1. In `WifiLink::serviceJoin()`, where `AT+CWJAP=` is composed, record
   a redacted form for tracing -- e.g. `AT+CWJAP="<ssid>",***` -- while
   the real command goes to the UART. The SSID is not a secret and is
   diagnostically valuable; the passphrase is and is not.
2. Audit every other `startCommand()` call site for the same shape.
   `AT+CWJAP` is the only one that carries a secret today; a test
   should pin that.
3. Host test: drive a join, assert the passphrase string appears
   nowhere in what `lastCommand()` returns, and that the SSID still
   does.
4. Once the extension redacts, `nezha-robot-template`'s
   `scripts/redact-wifi-trace.sh` becomes dead weight -- remove it
   there in a follow-up, but only after the extension pin moves.

## Operational note

Any passphrase that has been baked into a fleet robot up to
2026-09-09 should be considered exposed: those boards have been
emitting it on `DBG:wifi` over radio and WiFi for as long as they have
had credentials. Rotating it is a stakeholder decision, recorded here
so the decision is at least a conscious one.

## Affected code

- `src/comms/wifi_link.cpp` -- `serviceJoin()`, `startCommand()`
- `src/comms/wifi_link.h` -- `lastCommand()`'s contract
- `src/comms/protocol.cpp` -- `emitWifiDebug()` (no change needed if
  the source is redacted, but its comment should say why it is safe)
- host tests for the WiFi link
- `nezha-robot-template/scripts/redact-wifi-trace.sh` (follow-up removal)
