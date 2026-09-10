---
status: pending
---

# WiFi credentials belong in flash, as a list, settable over the wire

## Description

Stakeholder direction, 2026-09-09, after a session lost to a wrong baked
password (`captures/`-cited in
`nezha-robot-template/docs/wifi.md`; see
[wifi-join-failure-does-not-say-why.md](wifi-join-failure-does-not-say-why.md)).

Today a robot's WiFi credentials are **compile-time**. They reach the
firmware one of two ways -- `tools/make_deploy.py::_inject_wifi_secrets()`
baking `config/wifi_secrets.json` into the fleet's own test program, or a
consumer project calling `diffDrive.setupWifi(ssid, password)` from its
own gitignored source (`nezha-robot-template/test/boot.ts`). Both put the
passphrase **inside the hex**. That has three consequences the
stakeholder wants gone:

1. **A public release cannot carry working credentials.**
   `League-Robotics/nezha-robot-template` is a public repo, so its
   released calibration image ships an EMPTY password on purpose and
   joins nothing. Anyone who wants WiFi must build locally.
2. **Changing a password means rebuilding and reflashing every board.**
3. **A robot can only ever know one network.** Move the fleet between
   the classroom AP and a competition AP and every board needs a new hex.

## What the stakeholder asked for

> There's a status to say, "Do you have a Wi-Fi device?" There's a status
> to say, "What is its SSID?" If it has an SSID, there's a stat that
> says, "Do you have a password?" Then we make it possible to set all
> that stuff.
>
> We're going to need to be able to put this into a flash, however. And
> your flash storage should be able to store multiple combinations of
> SSID and password. It'd be really sweet if you could just walk down the
> list and get one. [...] It'd be even sweeter if we were able to set and
> get that list.

Read as five requirements:

- **R1 Report.** The wire can ask whether a WiFi module is fitted, what
  SSID the robot is on or trying, and whether that entry has a
  passphrase at all -- without ever revealing the passphrase.
- **R2 Set.** The wire can set credentials on a running robot. No
  rebuild, no reflash.
- **R3 Persist.** Credentials survive a power cycle AND a reflash of the
  program, because they live in flash, not in the image.
- **R4 A list.** The store holds several `(ssid, password)` entries, not
  one.
- **R5 Walk it.** On boot the link tries entries in order until one
  joins, so one image works in the classroom and at a competition.
- **R6 Get/set the list.** The whole list is readable and writable over
  the wire, so a host tool can provision a board in one exchange.

## What is already there, and what is not

**`setupWifi()` refuses late calls** (`src/comms/protocol.cpp:272-295`).
Once `wifiBegun_` is true the stored credentials are live -- WifiLink
re-reads `config_.ssid`/`config_.password` on every join attempt and
backoff retry -- so R2 cannot simply reuse this path. Either the setter
writes to flash and takes effect at the next join/reboot, or WifiLink
grows a supported way to be re-pointed mid-flight. That is an
architecture decision, not a detail.

**Flash storage is available but the obvious option does not fit.** This
build has CODAL's `KeyValueStorage` on the `MicroBit` object
(`uBit.storage`, `codal-microbit-v2/model/MicroBit.h:157`), but its
shape is hostile to this use:
`KEY_VALUE_STORAGE_KEY_SIZE 16`, value `48 - 16 = 32` bytes, and
`KEY_VALUE_STORAGE_MAX_PAIRS 5`
(`codal-core/inc/drivers/KeyValueStorage.h:39-46`). An 802.11 SSID is up
to 32 octets and a WPA2 passphrase up to 63 -- so one network does not
fit in one pair, and five pairs total cannot hold a list of any useful
length. The alternatives worth costing in architecture: `MicroBitFile` /
`MicroBitFileSystem`, or a single dedicated flash page written through
`MicroBitFlash`/`NRF52FlashManager` holding fixed-size records. Whatever
is chosen must not collide with whatever PXT itself keeps in flash --
verify, do not assume.

**Walking the list needs a reason to move on.** R5 is only sane if a
failed entry can be told from a slow one. `WifiLink::serviceJoin()`
currently drops the module's `+CWJAP:<code>` on the way into
`enterBackoff()` (`src/comms/wifi_link.cpp:571`), which is exactly the
subject of
[wifi-join-failure-does-not-say-why.md](wifi-join-failure-does-not-say-why.md).
Sequence that issue first, or absorb it; a list-walker built on a plain
timeout will spend `kJoinTimeout` per wrong entry with no idea why.

**A `STATUS` line already exists and is nearly full.** R1's fields need
to go somewhere -- extending `STATUS`, a new verb, or `GET` keys are all
plausible; the wire is versioned and consumed by `tools/`, `rogo`, the
robot-console host, and student code, so the choice has downstream cost.
`DBG:wifi` already reports much of R1 (`state=`, `ip=`, `credsrc=`) but
is a debug line, not a queryable status.

## Constraints

- **Never emit a passphrase on the wire or in a debug line.** R1 asks
  whether a password is SET, not what it is. `scripts/redact-wifi-trace.sh`
  in the template exists because this leaked once already. A `GET` of the
  list returns SSIDs and a has-password flag, never the secret.
- **An unprovisioned board must behave exactly as today**: empty store =
  `kDisabled`, zero cost, no module traffic.
- Identifier naming follows `.claude/rules/no-units-in-identifiers.md`.
- Every measured claim names its artifact
  (`.claude/rules/measurement-citations.md`). The flash-durability
  claims in particular (survives reflash? survives mass erase?) must be
  MEASURED on a board, not reasoned from headers -- a `mbdeploy deploy`
  erases pages, and whether it erases the store's page is the whole
  point of R3.

## Affected code

- `src/comms/wifi_link.{h,cpp}` -- join list walking, `+CWJAP:` code
- `src/comms/protocol.{h,cpp}` -- credential ownership, `setupWifi()`,
  `emitWifiDebug()`, status reporting
- `src/comms/wire_handler.cpp` -- new verbs / STATUS fields
- new: a flash-backed credential store + its host tests
- `src/blocks/run.ts`, `src/blocks/sim.ts`, `src/shims.cpp` -- if the
  TS surface changes
- `tools/` -- a provisioning path (`wifilink.py`/`robotlink.py`/`rogo`)
- `tools/make_deploy.py` -- what baking means once flash wins
- `docs/robot-connections.md`, `nezha-robot-template/docs/wifi.md`
