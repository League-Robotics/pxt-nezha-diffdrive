---
status: pending
---

# After `setupWifi("", "")`, `wifiSsid_`/`wifiPassword_` hold binary garbage by the time the link joins

## Measured: tigez, 2026-09-25

Captured by robot-console-33 over direct USB serial (hodr, /dev/ttyACM1,
115200, nothing else holding the port), after `ID\n`:

```
id diffdrive calibration-0.20260919.6 1.20260914.1 tigez
DBG:wifi state=1 ... restarts=44 ... cmd=AT+CWJAP=",\x13\x03",*** reply=ERROR.. credsrc=1 trunc=0 join=- haspw=1 ssid=,\x13\x03
```

- **SSID:** 3 bytes, `0x2C 0x13 0x03`, followed by the terminating NUL. Read as a
  little-endian word that is `0x0003132C`, which looks like a flash address,
  not text.
- **`credsrc=1`:** the credential came from `setupWifi()`, not the flash store.
- **`trunc=0`:** `setupWifi()` did not see an over-long string.
- **`haspw=1`:** `wifiPassword_` is non-empty too.
- **`WIFICRED` and `WIFICRED #7`:** both return `nack 1 0 none`. This firmware
  predates the verb being reachable here, so the flash store is not involved.

## What the program actually passed

The program was nezha-robot-template tag `v0.20260919.6`, pinning this
extension at `v1.20260914.1`. Its `test/boot.ts` calls
`diffDrive.setupWifi(WIFI_SSID, WIFI_PASSWORD)`, and CI seeds both constants
as `""`. So the call was `setupWifi("", "")`, and the expected state is
`credsrc=1 haspw=0 ssid=-`.

## What has been ruled out, by reading (none of it measured)

- **The shim (`src/shims.cpp` `setupWifi`):** it guards size 0 with
  `ManagedString("")`. CODAL's empty `StringData` (`REF_COUNTED_DEF_EMPTY(0, 0)`)
  decodes to `len=0, data=""`. Both locals outlive `protocolSetupWifi()`.
- **`Protocol::setupWifi()`:** it `snprintf`s into owned buffers.
  `trunc=0` agrees that the input was short.
- **Neighbouring members:** the members just before `wifiSsid_` in
  `protocol.h` (`wifiEnabled_`, `wifiBegun_`, `lastWifiDbg_`) cannot overflow
  into it.
- **The TS binding:** `_setupWifi` is `//% shim=diffDrive::setupWifi` with a
  matching `(String, String)` signature.

So the buffers were most likely correct after `setupWifi()` and **overwritten
later**, by a stray write or stack overflow into `Protocol`'s storage. The
pointer-shaped value supports that. The calibration program is large.

## Scope

- **Other robots:** tovez and vevov were provisioned the same way and have never
  appeared on the AP or in DHCP. They are probably affected but not yet
  confirmed.
- **What current releases avoid:** the fleet no longer takes this path.
  nezha-robot-template `v0.20260926.1` (commit 60a173e) uses flash-only WiFi
  (`enableStoredWifiLink`, extension `v1.20260925.1`) and never calls
  `setupWifi()`, so `wifiSsid_` is never consulted.
- **What stays open:** if the root cause is a stray write, the flash path's
  buffers (`WifiJoinSequencer::ssidBuf_`) are just as exposed. Keep this issue
  open until it is either reproduced and fixed, or a robot on the flash-only
  build is shown to join cleanly.

## To reproduce

1. Build `v0.20260919.6` of the template.
2. Flash it to a spare Nezha with an ESP module.
3. Read the `DBG:wifi` line right after boot and again later.

If `ssid=` is `-` right after boot and turns to garbage later, the buffers
are being overwritten. To find the writer, put a watchpoint (DWT) on
`&protocol().wifiSsid_`.
