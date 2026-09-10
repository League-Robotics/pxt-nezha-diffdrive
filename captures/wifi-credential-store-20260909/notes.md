# WIFICRED on hardware — gopiv, 2026-09-09/10

Ticket 038-004's hardware run, plus the two defects it exposed. Board
gopiv, reached over the Pi `null` serial daemon and over its own WiFi
link. Builds are `tools/make_deploy.py --robot gopiv` at successive
sprint-038 commits.

## What the run found

| # | attempt | result |
|---|---|---|
| 1 | `WIFICRED SET 0 TestNet038 secretpw038 #2` on the first sprint-HEAD build | `err 3` — rejected, and `WIFICRED` enumerated nothing (`wificred-hw.log`) |
| 2 | same, after the `flash_write` sense fix | `ack 2`, but enumeration printed `wificred zu 0` (`wificred-hw3.log`) |
| 3 | same, after the `%zu` fix | `ack`, and enumeration printed `wificred 0 TestNet038 1` (`wificred-hw5.log`) |

### Defect 1 — the vendored header's `@return` is wrong

`MicroBitFlash.h:61` documents `flash_write()` as *"non-zero on sucess,
zero on error"*. `MicroBitFlash.cpp`'s implementation ends
`return MICROBIT_OK;`, and `MICROBIT_OK` is **0**; its guard failures
return `MICROBIT_INVALID_PARAMETER`, which is non-zero. The doc is
inverted with respect to the code. `WifiFlashPortCodal::write()` had
followed the doc, so every successful write reported failure — the
`err 3` above. Fixed to compare against `MICROBIT_OK`.

This is the rule about reading source not being measuring, in its
sharpest form: the *comment* was read, the *code* was not, and only the
board could tell them apart.

### Defect 2 — this target's printf has no `%zu`

`execWifiCred()`'s enumeration used `%zu` for the slot index. newlib-nano
emits `zu` literally and shifts the remaining arguments, so a correct
store printed `wificred zu 0` — no SSID, no flag. The host suite passed
throughout, because the host's printf does support `%zu`. Fixed with an
explicit `unsigned` cast, and pinned repo-wide by
`tests/host/test_no_percent_z_format_specifier_source_pin.py`.

## Flash survival: a deploy MASS-ERASES, so credentials do NOT survive it

After `mbdeploy deploy --remote gopiv`, a `WIFICRED` enumeration of a
store that had been written before the flash came back **empty**
(`wificred-hw4.log` sequence). The programmed range (105 sectors,
0x68000 bytes) does not reach the store's page at `0x0007D000`, so this
is not overwrite — it is pyOCD's chip mass-erase, which is also what
`a-remote-farm-flash-can-fail-after-mass-erase` describes.

**Operational consequence: provision AFTER flashing, never before.**
That is not a defect; it is the correct order for a credential store
that must not travel inside a public hex.

## Left UNVERIFIED, and why

**Boot-time pickup of a stored credential (`credsrc=2`) has not been
confirmed on hardware.** Confirming it needs a reboot that is *not* a
reflash, and this session could not produce one remotely: the wire
vocabulary has no reset/reboot verb, gopiv's Nezha brick is switched off
so its power cannot be cycled through it, and the `null` Pi's serial
daemon holds the port open continuously, so the
open-the-port-resets-the-target behaviour never fires. The precedence
logic is source-pinned only (`tests/host/test_setupwifi_precedence_source_pin.py`);
`protocol.cpp` transitively includes `pxt.h` and cannot be host-compiled.

The first person to flash a board, run `WIFICRED SET`, and power-cycle
it settles this. Expect `DBG:wifi ... credsrc=2` and a join on the
stored SSID.

A `REBOOT` wire verb would close this hole and make the whole
provision-then-restart loop testable without touching the hardware.
Worth filing.

## Grammar as measured

```
HELLO
WIFICRED SET <slot> <ssid> <password> #<id>    -> ack <id> ...
WIFICRED #<id>                                 -> wificred <slot> <ssid> <haspw>
WIFICRED CLEAR <slot> #<id>                    -> ack <id> ...
```

Every form is sequenced — a bare `WIFICRED` without `#<id>` is nacked
and enumerates nothing. `<password>` is mandatory on `SET`:
`WIFICRED SET 1 SecondNet #3` came back `err 2` (`wificred-hw5.log`).
`haspw` is `0`/`1`; no passphrase appears in any reply.
