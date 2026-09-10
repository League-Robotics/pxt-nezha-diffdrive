---
id: '003'
title: 'WIFICRED wire verb: enumerate, set, and clear credential slots'
status: done
use-cases:
- SUC-001
- SUC-005
depends-on:
- '002'
github-issue: ''
issue: wifi-credentials-live-in-flash-not-in-the-hex.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# WIFICRED wire verb: enumerate, set, and clear credential slots

## Description

Give the wire access to ticket 002's store (R2, R6). Per sprint
architecture Design Rationale #4, this is a NEW verb, `WIFICRED`, not
an extension of `GET`/`SET`'s existing scalar ×1000-fixed-point config
table (`src/comms/config_fields.h`) — that table has no shape for two
variable-length strings per record.

Follow `execFuncs()`'s existing shape exactly
(`src/comms/wire_handler.cpp:970-1021`) — it is the established
precedent for a variable-length, adapter-disclosed, one-line-per-entry
enumeration:

- Bare `WIFICRED` → one `wificred <slot> <ssid> <haspw>` line per
  OCCUPIED slot (never a password value), terminated by the reply's own
  ack, same as `FUNCS`.
- `WIFICRED SET <slot> <ssid> <password> #<id>` → write one slot.
  Sequenced (mutates what a concurrent enumeration/read could see —
  the same reasoning `config_fields.h`'s own comment gives for why
  `GET` is sequenced despite being read-only).
- `WIFICRED CLEAR <slot> #<id>` → erase one slot. Sequenced.

`WireAdapter` grows four new methods delegating to `Protocol` →
`WifiCredentialStore`, mirroring the `runCount()`/`runName()`/
`runSignature()` seam `RunRegistry` already established for `FUNCS`:
`wifiCredCount()`, `wifiCredSlot(i, ssidOut, ssidCap, hasPwOut)`,
`wifiCredSet(slot, ssid, password)`, `wifiCredClear(slot)`.

`kCommandTable`'s row count and its compile-time `static_assert`
(`src/comms/wire_handler.cpp:299`, currently asserting 19) both grow by
one — this is documented as the file's OWN required convention for
adding a verb; do not forget it, the build fails loudly if you do,
which is the point.

## Acceptance Criteria

- [x] `WIFICRED` (bare) enumerates every occupied slot as
      `wificred <slot> <ssid> <haspw>`; an empty store enumerates
      nothing (not an error), matching `FUNCS`'s empty-registry
      behavior.
- [x] `WIFICRED SET <slot> <ssid> <password>` round-trips: a subsequent
      bare `WIFICRED` shows the slot occupied with the correct SSID and
      `haspw=1`.
- [x] `WIFICRED CLEAR <slot>` removes a slot; it no longer appears in
      the enumeration.
- [x] An oversized SSID/password `SET` is rejected with a wire error,
      not silently truncated (same reasoning as ticket 002's store-level
      criterion — this verb must not paper over that with its own
      truncation).
- [x] **No passphrase appears in ANY reply, ack, nack, err, or `DBG:`
      line this verb can produce, under any input** — including a
      malformed `SET` whose error path might otherwise be tempted to
      echo back what it received for debugging. Explicitly tested:
      a host test asserts the wire capture of a `SET` round-trip
      contains the SSID text but never the password text, on both
      the success and the rejection paths.
- [x] `kCommandTable`'s row count and its `static_assert` are both
      updated; the project builds (host + syntax gate) with the new
      count.
- [x] Protocol-level tests exist alongside the existing
      `wire_handler`/`protocol` test suite (per the sprint's own Test
      Strategy), mirroring `FUNCS`'s existing coverage shape
      (`tests/host/test_wire_handler.py` or equivalent).

## Implementation Plan

**Approach**: Add `decodeWifiCred`/`execWifiCred` to
`Wire::WireHandler`, following `decodeGet`/`execGet` and
`execFuncs`'s patterns for the bare/enumeration case and
`decodeSet`/`execSet`'s pattern for the field-parsing shape of `SET`/
`CLEAR`. Add the four-method seam to `WireAdapter`, backed in this
ticket by a Protocol-owned `WifiCredentialStore` reference (Protocol's
OWNERSHIP of the store instance itself lands in ticket 006 alongside
the sequencer — for THIS ticket, it is acceptable for `WireAdapter`'s
new methods to reach a store instance however is simplest to land
first and be re-pointed in ticket 006 without changing this ticket's
own verb-level tests).

**Files to modify**:
- `src/comms/wire_handler.h` / `.cpp` — new verb entry, decode/exec
  pair, `kCommandTable` count + `static_assert`.
- `src/comms/wire_adapter.h` / `.cpp` — new seam methods.
- `src/comms/protocol.h` / `.cpp` — whatever minimal plumbing is needed
  for `WireAdapter` to reach a store instance (finalized in ticket
  006).

**Testing plan**: `tests/host/test_wire_handler.py` (or the project's
equivalent existing protocol test file) — bare enumeration, `SET`
round-trip, `CLEAR`, oversized-input rejection, and the passphrase-
never-echoed check across both success and error paths.

**Documentation updates**: None required by this ticket alone; folded
into ticket 007's docs pass once the feature is end-to-end.
