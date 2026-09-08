---
id: '003'
title: 'Shim and TS/sim surface: setDeviceRole() and setProfile() entry points'
status: done
use-cases:
- SUC-001
- SUC-002
depends-on:
- '001'
- '002'
github-issue: ''
issue:
- high/hello-banner-role-and-common-name-are-hardcoded.md
- high/kprofile-needs-a-runtime-setter.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Shim and TS/sim surface: setDeviceRole() and setProfile() entry points

## Description

Wire the two C++ cores from tickets 001/002 up through `shims.cpp` to
hidden TypeScript entry points, with matching `sim.ts` recording stubs.
Both follow `setupWifi()`'s exact shape (`src/shims.cpp:1770-1785`,
`src/blocks/run.ts:190-203`, `src/blocks/sim.ts:557-561`) — copy that
shape twice, once per setter, rather than inventing a variant.

Unlike `setupWifi(ssid, password = "")`, NEITHER new setter has a
natural default-valued parameter: `setDeviceRole(role, commonName)`
takes two required strings (both are meaningful; there is no "disable"
case the way an empty WiFi SSID is), and `setProfile(name)` takes one
required string. Do not invent a default value for either — match
`setupWifi()`'s ARITY/VISIBILITY/BOUNDARY shape, not its specific
default-parameter detail.

### `src/shims.cpp` — copy `setupWifi()`'s shim exactly, twice

Two traps `setupWifi()`'s own shim already documents, both apply again
here:

1. **`//%` must sit IMMEDIATELY above the declaration.** No intervening
   comment line.
2. **Emptiness via the PXT String's own `getUTF8Size()`, not
   `toCharArray()`'s result at size 0** — at size 0, `toCharArray()`
   returns junk, not `""` (measured gopiv 2026-09-07, fw
   1.20260907.1 — see `setupWifi()`'s own shim comment for the
   citation). Both new setters take fields that must never be treated
   as accidentally-non-empty due to this trap.

```cpp
void protocolSetDeviceRole(const char* role, const char* commonName);

//%
void setDeviceRole(String role, String commonName) {
  if (role == nullptr || commonName == nullptr) return;
  ManagedString roleStr = role->getUTF8Size() == 0 ? ManagedString("") : MSTR(role);
  ManagedString commonNameStr = commonName->getUTF8Size() == 0 ? ManagedString("") : MSTR(commonName);
  protocolSetDeviceRole(roleStr.toCharArray(), commonNameStr.toCharArray());
}

void protocolSetProfile(const char* name);

//%
void setProfile(String name) {
  if (name == nullptr) return;
  ManagedString nameStr = name->getUTF8Size() == 0 ? ManagedString("") : MSTR(name);
  protocolSetProfile(nameStr.toCharArray());
}
```

Keep each `ManagedString` local in scope across its `protocolSet*()`
call — same lifetime concern `setupWifi()`'s shim documents:
`protocolSetDeviceRole()`/`protocolSetProfile()` copy before returning
(ticket 001/002's `Protocol` methods do this via `snprintf`), but the
`ManagedString` here must not be destructed before that copy happens.

### `src/blocks/run.ts` — copy `setupWifi()`'s placement and hiding

Add both, directly above `enableWifiLink()` (or immediately after
`setupWifi()`, whichever reads better once you see the file), matching
its doc-comment style and `//% blockHidden=true`:

```ts
/**
 * Set the HELLO banner's role and common name, instead of the fixed
 * `NEZHA2 robot` pair baked into this firmware. The banner is
 * space-separated and parsed positionally by every consumer, so any
 * whitespace in either string is stripped (leading, trailing, and
 * internal) before it is stored -- eg. "my robot" becomes "myrobot".
 * The call always succeeds; whitespace never causes rejection (see
 * DBG:role).
 * Picked up by the next banner regardless of whether this is called
 * before or after the protocol fiber starts -- no ordering trap.
 * @param role firmware family, eg: "NEZHA2"
 * @param commonName generic name within that family, eg: "robot"
 */
//% blockHidden=true
export function setDeviceRole(role: string, commonName: string): void {
    _setDeviceRole(role, commonName)
}

/**
 * Report which robot's config this program has actually loaded, in
 * the `id` reply's `profile` field -- eg. after pasting a calibration
 * block at runtime. Unlike setupWifi(), a call made after the first
 * `id` reply has already gone out still succeeds and is reflected in
 * the next one. Any whitespace in `name` is stripped (leading,
 * trailing, and internal) before it is stored; the call always
 * succeeds (see DBG:profile).
 * @param name the robot config name, eg: "vevov"
 */
//% blockHidden=true
export function setProfile(name: string): void {
    _setProfile(name)
}
```

### `src/blocks/sim.ts` — record, don't model, same as `_setupWifi`

```ts
//% shim=diffDrive::setDeviceRole
export function _setDeviceRole(role: string, commonName: string): void {
    simDeviceRole = role
    simCommonName = commonName
}

//% shim=diffDrive::setProfile
export function _setProfile(name: string): void {
    simProfile = name
}
```
with matching `let simDeviceRole = ""`, `let simCommonName = ""`,
`let simProfile = ""` module-locals declared alongside the existing
`simWifiSsid`/`simWifiPassword` locals.

## Acceptance Criteria

- [x] `diffDrive.setDeviceRole(role, commonName)` and
      `diffDrive.setProfile(name)` are callable from TypeScript/
      JavaScript, both `//% blockHidden=true`, neither present in the
      toolbox.
- [x] Both shims treat an empty PXT `String` as `""` via
      `getUTF8Size()`, not via `toCharArray()`'s result at size 0.
- [x] `_setDeviceRole`/`_setProfile` in `sim.ts` record into sim-local
      variables and perform no other action, matching `_setupWifi`'s
      shape.
- [x] `//%` annotations sit immediately above their declarations in
      `shims.cpp`, with no intervening comment line, for both new
      shims.
- [x] `tests/host/test_block_toolbox_order.py` still passes unmodified
      (or, if it genuinely needs a baseline change, that is justified
      as intentional in this ticket's notes, not a reflexive baseline
      update) — check whether this ticket's change alone breaks
      anything before assuming ticket 006 covers it.

## Completion notes

- `test_block_toolbox_order.py` passes UNMODIFIED: both new functions
  carry no `block=` caption (only `blockHidden=true`), so the scanner
  never sees them and the baseline needed no change.
- Verified with a real `pxt build` (not just the tsc-text-scan tests),
  via `projects/blocktest` (OrbStack/Docker `pext/yotta` toolchain):
  `shims.cpp` compiled and linked with the new `setDeviceRole`/
  `setProfile` shims, and a consumer `main.ts` calling
  `diffDrive.setDeviceRole("NEZHA2", "robot")` /
  `diffDrive.setProfile("vevov")` built a hex successfully
  (`projects/blocktest/built/binary.hex`). That scratch project change
  was reverted after the build (`projects/` is git-tracked here despite
  `.gitignore`, so it was checked out back to its prior committed
  state, not left modified).
- Not run: a full Blocks-editor JS<->Blocks decompile/toolbox-render
  check (no live `pxt serve` session opened this turn) — UNVERIFIED,
  consistent with `test_block_toolbox_order.py`'s own source-scan
  proxy method rather than a real toolchain invocation.

## Testing

- **Existing tests to run**: whatever `tests/host/` targets exercise
  `shims.cpp`/toolbox ordering today (`grep -rl "blockHidden\|shim="
  tests/host/`); a local `pxt build` or the project's existing build
  check, to confirm the shim scanner accepts both `//%` placements.
- **New tests to write**: none in this ticket — the arity/adjacency pin
  test is ticket 006.
- **Verification command**: scope to the shim/toolbox tests found
  above, plus a build check. The full suite runs once, inside
  `close_sprint`.
