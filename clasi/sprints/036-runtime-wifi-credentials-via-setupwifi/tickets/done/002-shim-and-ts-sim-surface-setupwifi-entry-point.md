---
id: '002'
title: 'Shim and TS/sim surface: setupWifi() entry point'
status: done
use-cases:
- SUC-001
depends-on:
- '001'
github-issue: ''
issue: wifi-credentials-are-set-in-code-from-the-project-s-own-secrets-ts.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Shim and TS/sim surface: setupWifi() entry point

## Description

Wire the C++ `Protocol::setupWifi()` core from ticket 001 up through
`shims.cpp` to a hidden TypeScript entry point, and give the simulator
a matching no-op-but-recording stub. This is the interface contract
the already-written consumer needs:
`league-projects/scratch/nezha-robot-template/test/boot.ts` has the
restore commented out as exactly one line —
`diffDrive.setupWifi(WIFI_SSID, WIFI_PASSWORD)` — so the exported
name, arity, and default-parameter shape here are fixed, not a matter
of taste.

Two established patterns to copy exactly, not invent new variations
of:

### `src/shims.cpp` — copy `registerRunName()`'s idioms

`registerRunName()` (`src/shims.cpp:1818` onward) is the model for
copying a PXT `String` into callee-owned storage. Its doc comment
calls out two traps that apply directly here:

1. **`//%` must sit IMMEDIATELY above the declaration.** An
   intervening comment between the annotation and the function fails
   the PXT shim scanner's build with a misleading "declaration not
   understood" that names the comment line, not the real problem. Put
   any explanatory comment ABOVE the `//%` line, not between it and
   the function.
2. **Emptiness must be tested with the PXT String's own
   `getUTF8Size()`, not by inspecting `MSTR()`'s `toCharArray()`
   result.** At size 0, `toCharArray()` returns junk, not a clean
   `""` — measured gopiv 2026-09-07, fw 1.20260907.1 (every line read
   `funcs <name> \xef\xbf\xbdc` where an omitted signature was
   expected to be empty). `setupWifi("")` is a REQUIRED code path in
   this sprint (SUC-002, the disable case) — getting emptiness
   detection wrong here is a live bug, not a corner case the way it
   might be elsewhere.

Add, following that exact shape:
```cpp
void protocolSetupWifi(const char* ssid, const char* password);

//%
void setupWifi(String ssid, String password) {
  if (ssid == nullptr) return;
  const char* ssidStr =
      ssid->getUTF8Size() == 0 ? "" : MSTR(ssid).toCharArray();
  const char* passwordStr = (password == nullptr ||
                              password->getUTF8Size() == 0)
                                 ? ""
                                 : MSTR(password).toCharArray();
  protocolSetupWifi(ssidStr, passwordStr);
}
```
(Adjust to keep each `ManagedString` temporary alive across the
`protocolSetupWifi()` call, the same lifetime concern
`registerRunName()`'s comment documents — `protocolSetupWifi()` must
copy before returning, which it does per ticket 001's
`Protocol::setupWifi()`, but the `ManagedString` here must not be
destructed before that copy happens. Write it so the `ManagedString`
locals stay in scope across the call, not as temporaries evaluated
inline.)

### `src/blocks/run.ts` — copy `enableWifiLink()`'s placement and hiding

Add directly above `enableWifiLink()` (`src/blocks/run.ts:203`,
`//% blockHidden=true`), matching its doc-comment style (audience
statement: "for the on-robot test program and advanced JavaScript
users -- not a block"):

```ts
/**
 * Set the WiFi network to join from the program, instead of relying
 * on credentials baked in at deploy time. Stores the credentials AND
 * brings the link up in one call -- call it once, from `on start`,
 * before anything else needs the network. An empty ssid disables the
 * link (equivalent to no module fitted). A call made after the link
 * has already started is ignored (see DBG:wifi for a late-call
 * notice).
 * @param ssid network name, eg: "Busboom Mesh"
 * @param password network password
 */
//% blockHidden=true
export function setupWifi(ssid: string, password: string = ""): void {
    _setupWifi(ssid, password)
}
```

Name and signature (`setupWifi(ssid, password = "")`) are fixed by
the stakeholder decision and the template's existing call site — do
not rename or reorder parameters.

### `src/blocks/sim.ts` — `_setupWifi`, `_setupRadio`'s pattern

Not `_enableWifiLink`'s bare no-op — record into module-local sim
state the way `_setupRadio` does (`src/blocks/sim.ts:543-547`), so a
future sim-side test or console can observe what a program called it
with, even though there is no WiFi module to simulate:

```ts
//% shim=diffDrive::setupWifi
export function _setupWifi(ssid: string, password: string): void {
    simWifiSsid = ssid
    simWifiPassword = password
    // No simulator model of the WiFi module, same as the link itself.
}
```
with matching `let simWifiSsid = ""` / `let simWifiPassword = ""`
module-locals declared alongside the existing `simRadioChannel` /
`simRadioGroup` / `simRadioEnabled` locals (`src/blocks/sim.ts:535-537`).

## Acceptance Criteria

- [x] `diffDrive.setupWifi(ssid, password = "")` is callable from
      TypeScript/JavaScript, matches the template's existing call
      site exactly (`setupWifi(WIFI_SSID, WIFI_PASSWORD)`), and does
      NOT appear in the toolbox (`blockHidden=true`).
- [x] `setupWifi("")` (single argument, relying on the default) type-
      checks and compiles — the default parameter must actually work,
      not just be documented.
- [x] The shim correctly treats an empty PXT `String` as `""` via
      `getUTF8Size()`, not via `toCharArray()`'s result at size 0.
- [x] `_setupWifi` in `sim.ts` records into sim-local variables and
      performs no other action, matching `_setupRadio`'s shape.
- [x] `//%` annotations sit immediately above their declarations in
      `shims.cpp`, with no intervening comment line.
- [x] Existing shim/toolbox pin tests (`tests/host/test_block_toolbox_order.py`
      and neighbors) still pass, or are updated in ticket 004 to
      account for the new hidden block — check whether this ticket's
      change alone breaks anything before assuming ticket 004 covers
      it.

## Testing

- **Existing tests to run**: whatever `tests/host/` targets exercise
  `shims.cpp`/toolbox ordering today (`grep -rl "blockHidden\|shim="
  tests/host/`); a local `pxt build` or the project's existing build
  check if one exists, to confirm the shim scanner accepts the `//%`
  placement (a misplaced comment fails the build, not a test).
- **New tests to write**: none in this ticket — the arity/adjacency
  pin test is ticket 004.
- **Verification command**: scope to the shim/toolbox tests found
  above, plus a build check for the shim-scanner requirement. The
  full suite runs once, inside `close_sprint`.
