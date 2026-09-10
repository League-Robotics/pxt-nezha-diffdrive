---
id: '002'
title: 'WifiCredentialStore and WifiFlashPort: flash-backed record store'
status: done
use-cases:
- SUC-002
- SUC-003
- SUC-004
depends-on: []
github-issue: ''
issue: wifi-credentials-live-in-flash-not-in-the-hex.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# WifiCredentialStore and WifiFlashPort: flash-backed record store

## Description

Build the flash-backed list store R3/R4 need. Per the sprint
architecture (Design Rationale #1), this is NOT `uBit.storage`
(`KeyValueStorage`'s 16-byte key / 32-byte value / 5-pair shape cannot
hold even one `(ssid, password)` record) and NOT `MicroBitFileSystem`
(unjustified complexity that competes with the flash driver's own
erase-merge scratch page for no benefit over a handful of fixed-size
records). Instead: a new host-portable `WifiCredentialStore` class
holding K fixed-size slots (default K=8 — see sprint architecture Open
Question 4; confirm/adjust with the stakeholder if the real
classroom-plus-competition use case wants more) in ONE dedicated flash
page, reached through a new thin platform seam, `WifiFlashPort`,
mirroring the `WifiUart`/CODAL split `WifiLink` already uses.

**Candidate page address**: pick a page OUTSIDE both
`MICROBIT_STORAGE_PAGE` (0x0007F000, owned by `uBit.storage`) and
`MICROBIT_DEFAULT_SCRATCH_PAGE` (0x0007E000, the flash driver's own
erase-merge scratch AND `MicroBitFileSystem`'s default scratch AND
`MICROBIT_APP_REGION_END` — where the compiled program's own region is
understood to end), per
`built/dockercodal/libraries/codal-microbit-v2/inc/MicroBitConfig.h`.
A natural first candidate is one page further down
(`MICROBIT_DEFAULT_SCRATCH_PAGE - MICROBIT_CODEPAGESIZE`, i.e.
0x0007D000 on this build), but this is a candidate, NOT a confirmed
answer — whether it actually survives `mbdeploy deploy` and a power
cycle is ticket 004's job, not this one's. Define the address as a
named constant with a comment citing where the two neighboring
reserved pages come from, so a future firmware region shuffle cannot
silently collide with it.

**Record layout**: fixed-size slot — SSID (33 bytes incl. NUL,
matching `Protocol::wifiSsid_`'s existing sizing), password (64 bytes
incl. NUL, matching `Protocol::wifiPassword_`), an occupied/valid flag.
An erased/never-written page reads as all-`0xFF` — the store MUST
treat that as "empty," not corrupted data (Migration Concerns in the
sprint architecture). Follow `.claude/rules/no-units-in-identifiers.md`
for every field/parameter name (e.g. a byte-count parameter is
`length`/`cap`, not `lengthBytes`, with the unit in a trailing comment
if it's ever ambiguous — this codebase's own convention throughout
`wifi_link.h`).

Writes go through `MicroBitFlash::flash_write()` (handles the
erase-merge dance generically) via the `WifiFlashPort` seam, NOT raw
`NRF52FlashManager::write()` calls that assume no erase is needed.

## Acceptance Criteria

- [x] `WifiCredentialStore` is host-portable (no `pxt.h`, no CODAL
      includes) — compiles and runs under `tests/host/` against a fake
      `WifiFlashPort`.
- [x] Round-trip: a written `(slot, ssid, password)` reads back
      identically (host test, fake flash).
- [x] List semantics: multiple slots can be occupied independently;
      clearing one slot does not disturb others.
- [x] Page-boundary / record-size edge cases are host-tested: an
      SSID/password at exactly the max length, one byte over (rejected,
      not silently truncated — silent truncation is what `setupWifi()`
      already does and this store deliberately does NOT inherit that
      behavior without saying so), and the all-`0xFF` erased-page case
      read as "empty," not corrupted.
- [x] `WifiFlashPort`'s real (CODAL-coupled) implementation writes to a
      page address that is a NAMED constant with a comment citing
      `MICROBIT_STORAGE_PAGE`/`MICROBIT_DEFAULT_SCRATCH_PAGE` as the
      two addresses it must not collide with.
- [x] No passphrase value appears in any log line, test fixture name,
      captured artifact, or commit this ticket produces — host test
      fixtures may use an obviously-fake string (e.g. `"testpw123"`)
      but never anything that looks like it was copied from a real
      `config/wifi_secrets.json` or a stakeholder's own network.
- [x] Identifier names carry no units (`.claude/rules/no-units-in-identifiers.md`) —
      reviewed explicitly, since this ticket introduces several
      byte-count-shaped fields (record size, slot count, page size)
      that are exactly the kind of name this rule targets.

## Implementation Plan

**Approach**: `WifiCredentialStore` owns record layout and slot
indexing only; `WifiFlashPort` (abstract interface + one CODAL
implementation, `src/platform/wifi_flash_port.{h,cpp}`) owns the
actual `MicroBitFlash`/`NRF52FlashManager` calls, exactly the division
`WifiUart` already has relative to `WifiLink`. A host test provides a
fake `WifiFlashPort` backed by a plain in-memory byte array that can
simulate "erased" (`0xFF`-filled) state.

**Files to create**:
- `src/comms/wifi_credential_store.h` / `.cpp` — the store, host-portable.
- `src/platform/wifi_flash_port.h` — the seam interface.
- `src/platform/wifi_flash_port.cpp` — CODAL implementation (the one
  non-host-portable translation unit this ticket adds).
- `tests/host/wifi_flash_port_shim.cpp` (or equivalent fake), following
  `tests/host/wifi_link_shim.cpp`'s existing shape.
- `tests/host/test_wifi_credential_store.py`.

**Files to modify**: `pxt.json`'s `files` list (new translation units
must be added, per this project's existing convention — every other
`src/` file is listed there explicitly).

**Testing plan**: New host suite per above. No hardware step in THIS
ticket — the real `WifiFlashPort` implementation is written but its
on-hardware behavior is verified by ticket 004, which depends on this
one.

**Documentation updates**: None required by this ticket alone; the
sprint's `docs/robot-connections.md`/`nezha-robot-template/docs/wifi.md`
updates land in ticket 007 once the whole feature is wired end-to-end.
