---
id: '001'
title: 'Protocol core: setupWifi() storage, precedence flag, late-call guard, truncation,
  DBG:wifi field'
status: done
use-cases:
- SUC-001
- SUC-002
- SUC-003
depends-on: []
github-issue: ''
issue: wifi-credentials-are-set-in-code-from-the-project-s-own-secrets-ts.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Protocol core: setupWifi() storage, precedence flag, late-call guard, truncation, DBG:wifi field

## Description

Add the C++ core of `Protocol::setupWifi(const char* ssid, const char*
password)` per `sprint.md`'s Architecture section — this ticket does
NOT touch `shims.cpp`, `run.ts`, or `sim.ts`; those are ticket 002.
This ticket is pure `src/comms/protocol.{h,cpp}`, plus a free-function
boundary entry point for the shim ticket to call.

The prior-art patch inlined in
`clasi/issues/wifi-credentials-are-set-in-code-from-the-project-s-own-secrets-ts.md`
is PRIOR ART, not the spec — its `wifiSsid_[0] ? wifiSsid_ :
kWifiSsid` ternary and separate-enable design are explicitly rejected
by the stakeholder decision (2026-09-07) recorded in that same issue.
Follow `sprint.md`'s Architecture section, not the patch.

### What to add to `protocol.h`

- `char wifiSsid_[33] = {0};` — 32-char SSID + NUL.
- `char wifiPassword_[64] = {0};` — 63-char WPA2 passphrase + NUL.
- `bool wifiCredsExplicit_ = false;` — true once `setupWifi()` has been
  called at all, independent of whether the SSID passed was empty.
  This is the fix for the patch's ternary bug: an empty explicit call
  must be distinguishable from "never called", and this flag is that
  distinction.
- `uint8_t wifiCredsTruncated_ = 0;` — bitmask, bit0 = SSID clipped,
  bit1 = password clipped. Set once at the `setupWifi()` store, never
  cleared elsewhere, so `DBG:wifi` keeps reporting it.
- Declaration of `void setupWifi(const char* ssid, const char*
  password);`, placed near `enableWifi()` with a doc comment in the
  same style (see `enableWifi()`'s existing comment at
  `protocol.h:188-195` for the pattern — OPT-IN framing, what this
  does and doesn't touch).

Grow `wifiDbgBuf_` from `char wifiDbgBuf_[320]` to `char
wifiDbgBuf_[384]` (`protocol.h:465`).

### What to add to `protocol.cpp`

`Protocol::setupWifi(const char* ssid, const char* password)`:

1. If `ssid == nullptr`, return without doing anything (same null
   guard as `emitLine()`/the patch's `setWifiCredentials`).
2. **Late-call guard.** If `wifiBegun_` is already `true`, do NOT
   touch `wifiSsid_`/`wifiPassword_`/`wifiCredsExplicit_`/
   `wifiCredsTruncated_` at all. `WifiLink::Config`'s `ssid`/`password`
   are pointers into this exact storage that `WifiLink::serviceJoin()`
   re-reads on every join attempt and every backoff retry
   (`src/comms/wifi_link.cpp:538`, `:560-561`) — NOT a value
   snapshotted once at `begin()`. Mutating the storage post-`wifiBegun_`
   would reach into a live join attempt, so refusing the write is what
   makes "changes nothing" true, not an incidental choice. Instead,
   call `emitLine()` with a fixed string:
   `"DBG:wifi late setupWifi() ignored"`, then return. This path is
   UNVERIFIED on hardware — say so in the comment, per
   `.claude/rules/measurement-citations.md` (source-reasoned from
   `wifi_link.cpp`, not measured).
3. Otherwise: compute truncation BEFORE copying — `strlen(ssid) >=
   sizeof(wifiSsid_)` sets bit0, same check for `password` against
   `sizeof(wifiPassword_)` sets bit1 (treat a null `password` as
   length 0, not truncated) — store the bitmask into
   `wifiCredsTruncated_`. Then `snprintf` both into their cells (clips
   safely regardless). Set `wifiCredsExplicit_ = true`. Call the
   existing `enableWifi()` unconditionally (sets `wifiEnabled_ =
   true`) — one call does both "store" and "enable", per the decision.
4. Add the free-function boundary entry point beside
   `protocolEmitLine()`'s (same file, same reasoning: keeps
   `shims.cpp` from needing `protocol.h`):
   `void protocolSetupWifi(const char* ssid, const char* password) {
   protocol().setupWifi(ssid, password); }`. Declare it in
   `protocol.h` or wherever `protocolEmitLine`'s declaration lives for
   `shims.cpp` to pick up in ticket 002 — check the existing pattern's
   declaration location before deciding.

`serviceWifi()`'s lazy-begin branch (`protocol.cpp:244-259`) changes
from:
```cpp
config.ssid = kWifiSsid;
config.password = kWifiPassword;
```
to:
```cpp
if (wifiCredsExplicit_) {
  config.ssid = wifiSsid_;
  config.password = wifiPassword_;
} else {
  config.ssid = kWifiSsid;
  config.password = kWifiPassword;
}
```
This is the actual fix that makes `setupWifi("")` disable rather than
fall back to the bake: `WifiLink::begin()` sees an empty
`config.ssid`, enters `kDisabled`, and returns before touching
`uart_.begin()` (`wifi_link.cpp:217-222`) — confirmed by reading
`begin()` and `service()` (`service()` returns immediately when
`state_ == kDisabled`, `wifi_link.cpp:745-746`). This is a source
reading of existing, unmodified code, not new behavior to build.

`emitWifiDebug()` (`protocol.cpp:221-242`): add ` credsrc=%d trunc=%u`
to the existing `snprintf` format string and argument list — `credsrc`
0 = baked, 1 = explicit-program (read `wifiCredsExplicit_`); `trunc` =
`wifiCredsTruncated_`. Do not reorder or remove any existing field —
downstream tooling may already parse this line by field name.

## Acceptance Criteria

- [x] `Protocol::setupWifi(ssid, password)` exists with the null
      guard, late-call guard, truncation detection, copy, and
      unconditional `enableWifi()` call described above.
- [x] `serviceWifi()`'s lazy-begin branches on `wifiCredsExplicit_`,
      not the ternary. With no `setupWifi()` call ever made, the
      branch behaves identically to today (uses `kWifiSsid`/
      `kWifiPassword`) — this is the byte-for-byte regression bar.
- [x] `setupWifi("real-ssid", "real-pw")` before the link begins
      results in `serviceWifi()`'s next pass using the stored,
      explicit credentials.
- [x] `setupWifi("")` before the link begins results in
      `WifiLink::begin()` receiving an empty SSID and entering
      `kDisabled` — same as "no module fitted", reached deliberately.
- [x] `setupWifi()` called after `wifiBegun_` is `true` leaves
      `wifiSsid_`/`wifiPassword_`/`wifiCredsExplicit_`/
      `wifiCredsTruncated_` unchanged and emits the fixed late-call
      `DBG:` line.
- [x] An SSID longer than 32 chars or a password longer than 63 chars
      is clipped (never overflows the cell) and sets the corresponding
      `wifiCredsTruncated_` bit; the next `DBG:wifi` line shows it via
      `trunc=`.
- [x] `wifiDbgBuf_` is 384 bytes; the extended `DBG:wifi` line does
      not truncate under `snprintf`'s own return-value check (verify
      by computing worst-case field widths, as `sprint.md`'s
      Architecture section does — no field silently dropped).
- [x] `tests/tools/test_make_deploy_wifi.py` still passes untouched —
      this ticket does not touch `tools/make_deploy.py` or the
      `kWifiSsid`/`kWifiPassword` literals/their DO-NOT-REFORMAT
      comment (`protocol.cpp:75-87`).

## Testing

- **Existing tests to run**: `tests/tools/test_make_deploy_wifi.py`
  (must still pass, untouched); any existing `tests/host/` suite that
  compiles `protocol.cpp` (check for build breakage from the new
  fields/method — grep `tests/host/` for what already links
  `protocol.cpp` or stubs it).
- **New tests to write**: none in this ticket — the host-level
  precedence/truncation/late-call test is ticket 003, once this
  ticket's C++ surface exists for it to link against.
- **Verification command**: scope to the modules this ticket touches,
  e.g. `uv run pytest tests/tools/test_make_deploy_wifi.py` plus
  whatever `tests/host/` target(s) build `protocol.cpp` today (find
  with `grep -rl protocol.cpp tests/host/`). The full suite runs once,
  inside `close_sprint`.
