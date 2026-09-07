---
title: "WiFi credentials: a setupWifi(ssid, password) entry point, called from the student project's own secrets.ts"
status: pending
created: 2026-09-07
---

# WiFi credentials: a `setupWifi(ssid, password)` entry point, called from the student project's own `secrets.ts`

## Description

Today there is exactly one way to give the robot WiFi credentials:
`tools/make_deploy.py::_inject_wifi_secrets()` rewrites `kWifiSsid` /
`kWifiPassword` in a SCRATCH COPY of `src/comms/protocol.cpp` (lines
86-87) from the gitignored `config/wifi_secrets.json`. The checked-in
literals are empty on purpose -- an empty SSID is `WifiLink`'s own
`kDisabled` sentinel (`src/comms/wifi_link.h:89`), so a build made
outside `make_deploy.py` never opens UARTE1.

That covers fleet builds and covers nothing else. A student building
their own program never runs `make_deploy.py`, so `enableWifiLink()`
(`src/blocks/run.ts:203`) is a permanent no-op for them, and the WiFi
carrier -- the DEFAULT carrier per
`.claude/rules/connecting-to-a-robot.md` -- is unreachable from a
student project.

## Decision (stakeholder, 2026-09-07)

Keep the structure we already have, one altitude down. Credentials are
**set in code, in a file that is not the program** -- a `secrets.ts` in
the student's own project, exactly as `config/wifi_secrets.json` is a
file that is not `protocol.cpp`. The extension's job is only to expose
the entry point that file calls.

WiFi is for ADVANCED students, and an advanced student should be moving
off the MakeCode web editor to VS Code -- where a separate, gitignorable
`secrets.ts` is the natural shape and costs them nothing.

## Proposal

- `setupWifi(ssid: string, password: string = "")` in
  `src/blocks/run.ts`, `//% blockHidden=true`.

  Hidden, not a toolbox block. `enableWifiLink()` right above it is
  already hidden for exactly this population ("for the on-robot test
  program and advanced JavaScript users -- not a block"), and a visible
  block would invite a beginner to drag it into a shared project and
  hardcode a passphrase in the tracked program -- the one thing the
  `secrets.ts` split exists to prevent.
- `enableWifiLink()` -- UNCHANGED, still uses the baked constants.
  `test/test.ts` and every fleet deploy keep working.
- `_setupWifi` in `src/blocks/sim.ts` records the values and does
  nothing else, exactly as `_setupRadio` does (there is no WiFi module
  in the browser).
- The consumer-side convention (a `secrets.ts` carrying the call, listed
  in the project's `pxt.json` `files`, gitignored, with a tracked
  `secrets.example.ts` beside it) belongs in the project template --
  `league-projects/scratch/nezha-robot-template` -- and in this repo's
  `docs/robot-connections.md`, not in the extension.

## Design points that are not obvious

**Lifetime.** `WifiLink::Config` borrows every `const char*` "for the
life of the link" (`src/comms/wifi_link.h:99`). A refcounted PXT
`String` cannot satisfy that contract. The shim must COPY into
Protocol-owned fixed cells before returning, the same way
`registerRunName()` copies into the run registry's own storage
(`src/shims.cpp:1818` and its comment). Sizes: 32+1 for the SSID, 63+1
for a WPA passphrase (64+1 if a raw hex PSK is to be allowed).

**Truncation must be visible.** A silently clipped passphrase presents
as "joins nothing, no reason" -- the failure mode this repo's rules
exist to prevent. Report it in the `DBG:wifi` line that
`Protocol::emitWifiDebug()` already emits.

**Ordering.** `begin()` is lazy: it runs on the Protocol fiber inside
`serviceWifi()` on the first pass after `wifiEnabled_` is set
(`src/comms/protocol.cpp:250`), because the mDNS hostname must be read
there. So `setupWifi()` from `on start` is naturally safe -- store, set
the flag, credentials are read on the next service pass. A call made
after the link reaches `kReady` is the UNVERIFIED path (the same caveat
`RadioTransport::setChannel()` documents for the already-up radio).
First cut: latch credentials at `begin()`, and have a late call emit a
`DBG:` line and change nothing, rather than half-restarting the AT
state machine.

**Precedence.** Explicit beats baked and the two never merge:
`setupWifi()` overwrites the cells AND enables; `enableWifiLink()`
enables with whatever is in the cells (i.e. the bake).
`setupWifi("")` disables, consistently with the existing sentinel.

**A gitignored file that the build requires.** PXT compiles a FIXED
file set from `pxt.json`'s `files` array, so a `secrets.ts` that is
listed-but-gitignored breaks the build for anyone who clones the
template without it. The template therefore ships a tracked
`secrets.example.ts` and a one-line setup step (copy it to
`secrets.ts`), which is the same shape `config/wifi_secrets.json`
already has here. Note this is a VS-Code-checkout property only: the
MakeCode web editor has no git, so a web-editor `secrets.ts` buys file
separation but not secrecy.

## Rejected alternatives

- **A `SET wifi_ssid` wire verb.** Chicken-and-egg (you would need USB
  to configure WiFi), and this firmware has no flash persistence, so it
  would not survive the reboot that a join needs anyway.
- **Flash persistence via PXT `settings`** (`libs/settings` IS bundled
  in the micro:bit target, `node_modules/pxt-microbit/pxtarget.json:17`,
  so this was available). Rejected: `settings.initScopes()` scopes the
  store to `control.programName()` and calls `_userClean()` when it
  changes (`node_modules/pxt-common-packages/libs/settings/settings.ts`
  lines 33-49), so credentials saved by one program are ERASED by
  flashing a different one -- defeating the purpose. Beyond that, this
  repo's persistence answer is deliberately bake-at-deploy so the
  fleet's configuration record lives in git rather than in seven boards'
  flash pages where nothing can audit it; a board carrying state nothing
  in git records is the `i2c-wedge-is-stale-state-not-firmware` failure
  mode.
- **AP-mode captive-portal provisioning.** Far more machinery than the
  problem justifies on this part.

## Status of the claims here

All of the above is SOURCE READING (2026-09-07), not measurement. In
particular the late-call behaviour of the AT state machine and the
Ai-WB2's handling of an empty passphrase on an open network are
UNVERIFIED; both would be settled on a board with the module fitted.
