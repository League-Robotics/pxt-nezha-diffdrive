---
title: 'WiFi credentials: a setupWifi(ssid, password) entry point, called from the
  student project''s own secrets.ts'
status: in-progress
created: 2026-09-07
sprint: '036'
tickets:
- 036-001
- 036-002
- 036-003
- 036-004
- 036-005
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

## A working implementation exists (2026-09-07)

`league-projects/scratch/nezha-robot-template` has been running this
capability since 2026-09-06 as an out-of-tree patch,
`patches/nezha-diffdrive-runtime-wifi-credentials.patch`, re-applied
over `pxt_modules/` on every build by `scripts/patch-extension.sh`.
Cut against `1.20260906.2` (tag `v0.20260906.3`); it applies with
`patch -p1 --fuzz=0` and the template builds and joins the network
with it. That template is carrying the patch only until this lands,
so it is the thing waiting on this issue.

It is PRIOR ART, not the proposal -- it was written before the
decision above and diverges from it in three ways that matter:

- **Name.** It exposes `setWifiCredentials(ssid, password)`. The
  decision says `setupWifi(ssid, password = "")`. Rename when landing;
  the template's `test/boot.ts` is the only caller and moves with it.
- **Precedence.** It only STORES; `enableWifiLink()` still has to be
  called separately, and `""` falls back to the bake rather than
  disabling. The decision has `setupWifi()` store AND enable, with
  `setupWifi("")` disabling. The decision's shape is the better one --
  it removes the two-call ordering trap the patch's own comment has to
  warn about.
- **Truncation is silent.** It uses `snprintf` into `char[33]` /
  `char[64]` and reports nothing. The decision requires truncation be
  visible in the `DBG:wifi` line. Not satisfied; still to write.

What it does confirm, on hardware rather than by source reading, is
the lifetime analysis under "Design points": copying into
Protocol-owned cells before returning is sufficient, and setting
credentials from `on start` before `enableWifiLink()` is read
correctly by the lazy `begin()` inside `serviceWifi()`.

<details>
<summary><code>nezha-diffdrive-runtime-wifi-credentials.patch</code></summary>

```diff
Let a program set the WiFi credentials at runtime.

The extension only takes credentials from kWifiSsid/kWifiPassword, which
tools/make_deploy.py rewrites in a scratch copy at deploy time from a
gitignored secrets file. This project does not deploy that way -- `npm run
build` plus `mbdeploy deploy --hex` flashes the pxt-built hex verbatim and
injects nothing -- so enableWifiLink() could never come up here: an empty
SSID is WifiLink's own "disabled" sentinel and the link stayed state=0.

Adds diffDrive.setWifiCredentials(ssid, password), copied into Protocol-owned
storage because WifiLink::Config borrows its pointers for the life of the
link. The bake still wins when no program sets them, so a make_deploy build
is byte-for-byte unaffected.

Candidate for upstream: it is a missing capability, not a local workaround.

--- a/src/comms/protocol.h
+++ b/src/comms/protocol.h
@@ -179,6 +179,13 @@
   // serviceWifi(), because the mDNS hostname is the board's friendly
   // name, which is only safe to read there (see buildIdentity()).
   void enableWifi();
+
+  // Set the network to join at RUNTIME, instead of the deploy-time bake
+  // (tools/make_deploy.py's _inject_wifi_secrets()). Copies into this
+  // object's own storage because WifiLink::Config borrows its pointers
+  // for the life of the link. Call BEFORE enableWifi(): serviceWifi()
+  // reads the credentials once, when it begin()s the link.
+  void setWifiCredentials(const char* ssid, const char* password);
 
  private:
   static void fiberEntry(void* self);
@@ -433,6 +440,11 @@
   // on this fiber.
   bool wifiEnabled_ = false;
   bool wifiBegun_ = false;
+  // Runtime credentials. Empty ssid means "fall back to the baked
+  // kWifiSsid/kWifiPassword". Sized to the 802.11 maxima: a 32-char
+  // SSID and a 63-char WPA2 passphrase, plus a NUL each.
+  char wifiSsid_[33] = {0};
+  char wifiPassword_[64] = {0};
   uint32_t lastWifiDbg_ = 0;  // [ms]
 
   // NSDMI, not a hand-written constructor: every member below depends
--- a/src/comms/protocol.cpp
+++ b/src/comms/protocol.cpp
@@ -223,6 +223,19 @@
 void Protocol::enableRadio() { radioTransport_.enable(); }
 
 void Protocol::enableWifi() { wifiEnabled_ = true; }
+
+void Protocol::setWifiCredentials(const char* ssid, const char* password) {
+  if (ssid == nullptr) return;
+  snprintf(wifiSsid_, sizeof(wifiSsid_), "%s", ssid);
+  snprintf(wifiPassword_, sizeof(wifiPassword_), "%s",
+           password == nullptr ? "" : password);
+}
+
+// Free-function entry point for shims.cpp -- the same boundary trick
+// protocolEmitLine() above uses, so shims.cpp never includes protocol.h.
+void protocolSetWifiCredentials(const char* ssid, const char* password) {
+  protocol().setWifiCredentials(ssid, password);
+}
 
 void Protocol::emitWifiDebug() {
   // One line, cleartext `DBG:` prefix (the same convention the TS
@@ -251,8 +264,11 @@
   if (!wifiBegun_) {
     wifiBegun_ = true;
     WifiLink::Config config;
-    config.ssid = kWifiSsid;
-    config.password = kWifiPassword;
+    // Runtime credentials win over the deploy-time bake when a program
+    // has set them; with neither, ssid stays "" -- WifiLink's own
+    // disabled sentinel -- and the link costs nothing.
+    config.ssid = wifiSsid_[0] ? wifiSsid_ : kWifiSsid;
+    config.password = wifiSsid_[0] ? wifiPassword_ : kWifiPassword;
     // The mDNS host label is the board's own silicon-derived name --
     // the same authoritative identity ID's `name` field reports -- so
     // `tovez.local` / "tovez robot link" can never be a stale bake.
--- a/src/shims.cpp
+++ b/src/shims.cpp
@@ -1774,8 +1774,19 @@
 // package and fails the build. Same convention protocol.cpp already
 // uses to reach into this file.
 void protocolEmitLine(const char* text);
+
+void protocolSetWifiCredentials(const char* ssid, const char* password);
 
 //%
+void setWifiCredentials(String ssid, String password) {
+  if (ssid == nullptr) return;
+  ManagedString s = MSTR(ssid);
+  ManagedString p = password == nullptr ? ManagedString("") : MSTR(password);
+  // Copied on the protocol side before these temporaries die.
+  protocolSetWifiCredentials(s.toCharArray(), p.toCharArray());
+}
+
+//%
 void emitLine(String text) {
   if (text == nullptr) return;
   ManagedString ms = MSTR(text);
--- a/src/blocks/sim.ts
+++ b/src/blocks/sim.ts
@@ -590,6 +590,12 @@
     //% shim=diffDrive::enableRadioLink
     export function _enableRadioLink(): void {
         simRadioEnabled = true
+    }
+
+    //% shim=diffDrive::setWifiCredentials
+    export function _setWifiCredentials(ssid: string,
+        password: string): void {
+        // No simulator model of the WiFi module, same as the link itself.
     }
 
     //% shim=diffDrive::enableWifiLink
--- a/src/blocks/run.ts
+++ b/src/blocks/run.ts
@@ -197,7 +197,20 @@
      * called. For the on-robot test program and advanced JavaScript
      * users -- not a block.
      */
+    /**
+     * Set the WiFi network to join from the program, instead of relying
+     * on credentials baked in at deploy time. Call this BEFORE
+     * enableWifiLink() -- the link reads them once, when it starts.
+     * @param ssid network name, eg: "Busboom Mesh"
+     * @param password network password
+     */
     //% blockHidden=true
+    export function setWifiCredentials(ssid: string,
+        password: string): void {
+        _setWifiCredentials(ssid, password)
+    }
+
+    //% blockHidden=true
     export function enableWifiLink(): void {
         _enableWifiLink()
     }
```

</details>
