---
id: '036'
title: Runtime WiFi credentials via setupWifi()
status: executing
branch: sprint/036-runtime-wifi-credentials-via-setupwifi
use-cases: []
issues:
- wifi-credentials-are-set-in-code-from-the-project-s-own-secrets-ts.md
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sprint 036: Runtime WiFi credentials via setupWifi()

## Goals

Ship `diffDrive.setupWifi(ssid, password)` in the extension so a
student project can set WiFi credentials from its own gitignored
`secrets.ts` file, and cut a release tag that
`league-projects/scratch/nezha-robot-template` can pin. This lands the
capability the template has been carrying as an out-of-tree patch
since 2026-09-06, with the three divergences from the stakeholder
decision fixed (see Problem).

## Problem

Today the only way to give the robot WiFi credentials is
`tools/make_deploy.py::_inject_wifi_secrets()` rewriting
`kWifiSsid`/`kWifiPassword` in a scratch copy of `protocol.cpp` at
deploy time from a gitignored `config/wifi_secrets.json`. That covers
fleet builds only. A student building their own program never runs
`make_deploy.py`, so `enableWifiLink()` is a permanent no-op for them
and the WiFi carrier — the default carrier per
`.claude/rules/connecting-to-a-robot.md` — is unreachable from a
student project.

`clasi/issues/wifi-credentials-are-set-in-code-from-the-project-s-own-secrets-ts.md`
carries the full stakeholder decision (2026-09-07) and a working
out-of-tree patch already proven on hardware
(`league-projects/scratch/nezha-robot-template`,
`patches/nezha-diffdrive-runtime-wifi-credentials.patch`). That patch
is prior art, not the spec — it diverges from the decision in three
ways the detail sprint must fix: it names the entry point
`setWifiCredentials` (decision: `setupWifi`); it only stores
credentials and requires a separate `enableWifiLink()` call, with `""`
falling back to the bake (decision: `setupWifi()` stores AND enables,
`setupWifi("")` disables — no two-call ordering trap); and it
truncates a too-long SSID/password silently (decision: truncation must
show up in the existing `DBG:wifi` line).

The template's `test/boot.ts` has the restore commented out as one
line — `diffDrive.setupWifi(WIFI_SSID, WIFI_PASSWORD)` — and the
template currently has WiFi entirely off, blocked on this sprint
landing under a tagged release.

## Solution

Add a hidden (`//% blockHidden=true`) `setupWifi(ssid, password = "")`
entry point to `src/blocks/run.ts`, backed by a Protocol-owned copy of
the credentials (the same lifetime pattern `registerRunName()` already
uses, since `WifiLink::Config` borrows its `const char*` pointers for
the life of the link). `enableWifiLink()` and the deploy-time bake are
unchanged — a build with no program calling `setupWifi()` stays
byte-for-byte identical. A `_setupWifi` shim in `src/blocks/sim.ts`
records and no-ops, matching `_setupRadio`. `docs/robot-connections.md`
gets the consumer-side `secrets.ts`/`secrets.example.ts` convention.
The sprint ends with a `pxt.json` version bump; the stakeholder tags
the release themselves (`v1.YYYYMMDD.n`, not CLASI's default
`0.YYYYMMDD.n` — this repo needs release tags to outrank `v1.0.0` for
MakeCode's extension resolution).

Design questions the detail sprint must settle (flagged, not
pre-answered here):

1. **Precedence bookkeeping.** An empty SSID cannot double as both "no
   credentials passed" and "explicitly disable" using the patch's
   `wifiSsid_[0] ? ... : kWifiSsid` ternary — that conflates "never
   called" with `setupWifi("")`. Needs an explicit "credentials were
   set by a program" flag or equivalent, so `setupWifi("")` reliably
   disables rather than silently falling back to the bake.
2. **What "disables" means concretely** when `setupWifi("")` is
   followed by `enableWifiLink()`.
3. **How truncation reaches the `DBG:wifi` line** — a field in the
   existing single line, budgeted against `wifiDbgBuf_`'s size (already
   long).
4. **The late-call path** — first cut per the issue: latch credentials
   at `begin()`; a call after the link is already up emits a `DBG:`
   line and changes nothing.

## Success Criteria

- `diffDrive.setupWifi(ssid, password)` exists, hidden from the
  toolbox, callable from TypeScript/JavaScript.
- `setupWifi()` stores AND enables in one call; `setupWifi("")`
  disables. `enableWifiLink()` behavior and the deploy-time bake are
  unchanged (fleet builds and `test/test.ts` byte-for-byte unaffected
  when no program calls `setupWifi()`).
- Truncation of an over-length SSID or password is visible in the
  `DBG:wifi` line, not silent.
- A late `setupWifi()` call (after the link is up) is a documented,
  visible no-op rather than an undefined half-restart.
- `docs/robot-connections.md` documents the consumer-side `secrets.ts`
  / `secrets.example.ts` convention.
- `tests/tools/test_make_deploy_wifi.py` still passes untouched.
- `pxt.json` is bumped (or the sprint plan explicitly notes the
  stakeholder must do it) so a release can be tagged
  `v1.YYYYMMDD.n` after close.

## Scope

### In Scope

- `setupWifi(ssid, password = "")` in `src/blocks/run.ts`
  (`//% blockHidden=true`), renamed from the patch's
  `setWifiCredentials`.
- Protocol-side storage and precedence/enable logic in
  `src/comms/protocol.{h,cpp}` (`enableWifi()`,
  `emitWifiDebug()`, `serviceWifi()`'s lazy `begin()`).
- Shim boundary in `src/shims.cpp` (PXT `String` → owned `char[]`
  copy, correct empty-string handling via `getUTF8Size()`, `//%`
  placement immediately above the declaration).
- `_setupWifi` shim in `src/blocks/sim.ts` (record-and-no-op, per
  `_setupRadio`).
- Truncation visibility in the `DBG:wifi` line.
- `docs/robot-connections.md` consumer-side `secrets.ts` convention.
- A `tests/host/` source-pin test for `Protocol::setupWifi()`'s
  precedence/truncation/late-call logic (pattern per
  `tests/host/test_dispatched_job_motion_source_pin.py` — see the Test
  Strategy section below for why the roadmap's original
  `test_wifi_link.py`-style compiled test does not apply here) and a
  pin test for the TS/shim arity and toolbox visibility (pattern per
  `tests/host/test_block_toolbox_order.py`).
- `pxt.json` version bump at sprint close.

### Out of Scope

- Any `runtext-use-after-release` work — `Protocol::runText()` was
  removed in c4ed4c3 ("028/003: executor inversion"); that bug is
  superseded, not outstanding.
- GitHub issues #3 and #4 on this repo — both filed by mistake, both
  closed. This repo tracks issues as files under `clasi/issues/`.
- Any change to `enableWifiLink()`'s existing behavior or to the
  deploy-time bake (`tools/make_deploy.py::_inject_wifi_secrets()`).
- Cutting the actual release tag — the stakeholder does that after
  sprint close.
- AP-mode captive-portal provisioning and flash-persisted credentials
  (both explicitly rejected in the issue).
- A `SET wifi_ssid` wire verb (explicitly rejected in the issue).

## Test Strategy

**Correction found during detail planning**: the roadmap's own
"host-level test... pattern per `tests/host/test_wifi_link.py`" does
not apply. `test_wifi_link.py` compiles `src/comms/wifi_link.cpp` via
`compile_shared_lib` — a file this sprint does not modify. All the new
logic lives in `src/comms/protocol.{h,cpp}`, and `tests/host/` cannot
compile `protocol.cpp` at all (it includes `pxt.h`, directly and
transitively — confirmed by the existing
`test_protocol_stack_canary_source_pin.py` and
`test_dispatched_job_motion_source_pin.py`, both of which document
this and use source-text pinning instead). Ticket 003 therefore
follows `test_dispatched_job_motion_source_pin.py`'s source-pin
pattern, not `compile_shared_lib`.

Three surfaces, three tickets:

- **Ticket 003** — source-pin test for `Protocol::setupWifi()`'s
  precedence/late-call/truncation logic in `protocol.cpp`.
- **Ticket 004** — new arity/adjacency pin test for `run.ts`'s
  `setupWifi` vs. `sim.ts`'s `_setupWifi` shim, plus confirming
  `test_block_toolbox_order.py` stays green (the hidden block must
  never join the visible toolbox baseline).
- **Regression gate** — `tests/tools/test_make_deploy_wifi.py` must
  keep passing untouched throughout (checked in tickets 001, 003, and
  005); this is the byte-for-byte "no program calls `setupWifi()`"
  bar from the roadmap.

## Architecture

**Compact** — confirmed against the actual precedence-flag design
below. One existing module (`Protocol`, `src/comms/protocol.{h,cpp}`)
gains one new entry point and two small pieces of bookkeeping; its two
existing boundary seams (`shims.cpp`'s free-function pattern into
`Protocol`, and `run.ts` → `sim.ts`'s shim pattern) are reused
unchanged, not extended with a new kind of coupling. No new
cross-module dependency, no dependency-direction change, no data-model
change (the new fields are firmware bookkeeping, not persisted or
cross-module state).

### Architecture Overview

**What Changed** — `Protocol` gains:

- `char wifiSsid_[33]`, `char wifiPassword_[64]` — Protocol-owned
  storage a program's credentials are copied into, sized to the 802.11
  maxima (32-char SSID, 63-char WPA2 passphrase) plus a NUL each. Same
  shape as the patch's `wifiSsid_`/`wifiPassword_`, same lifetime
  rationale as `registerRunName()`'s copy into the run registry
  (`src/shims.cpp:1818`): `WifiLink::Config` borrows every `const
  char*` "for the life of the link" (`wifi_link.h:99`), so a refcounted
  PXT `String` cannot satisfy it and the shim must copy before
  returning.
- `bool wifiCredsExplicit_ = false` — **the fix for design question 1.**
  The patch's precedence used a ternary,
  `wifiSsid_[0] ? wifiSsid_ : kWifiSsid`, which cannot distinguish "a
  program called `setupWifi("")`" from "no program ever called
  `setupWifi()`" — both leave `wifiSsid_[0]` as `'\0'`. This flag is
  the explicit third state: `setupWifi()` sets it `true` unconditionally
  (whatever the SSID), so an empty explicit call and "never called"
  read differently in `serviceWifi()`'s begin() branch (below), even
  though the stored SSID is `""` in both.
- `uint8_t wifiCredsTruncated_ = 0` — bitmask (bit0 SSID clipped, bit1
  password clipped), set once at the `setupWifi()` store and read by
  `emitWifiDebug()`. Persists (not cleared elsewhere) so the `DBG:wifi`
  line keeps reporting it for as long as the truncated credentials are
  the ones in effect.

New method `Protocol::setupWifi(const char* ssid, const char* password)`:

- **Late-call guard (design question 4, sharpened).** If `wifiBegun_`
  is already `true`, the store is skipped entirely — not merely
  "no-op'd by convention" but REQUIRED, because `WifiLink::Config`'s
  `ssid`/`password` are pointers into this exact storage that
  `serviceJoin()` re-reads on every join attempt and every backoff
  retry (`wifi_link.cpp:538`, `:560-561`), not a value snapshotted once
  at `begin()`. Mutating `wifiSsid_`/`wifiPassword_` after `wifiBegun_`
  would therefore reach into a live join attempt, not sit inertly
  unused — so "changes nothing" has to be enforced by refusing the
  write, not by relying on `WifiLink` having already copied the
  strings. A late call instead emits one `DBG:wifi late setupWifi()
  ignored` line and returns. This path is UNVERIFIED on hardware (the
  issue's own caveat) — it is reasoned from `WifiLink`'s source, not
  measured.
- Otherwise: `snprintf`-copies `ssid`/`password` into the owned cells,
  computing `wifiCredsTruncated_` from `strlen()` against
  `sizeof(cell) - 1` before the copy (a plain C-string source has no
  embedded NUL, so `strlen` is exact), sets `wifiCredsExplicit_ = true`,
  and calls the existing `enableWifi()` unconditionally — "stores AND
  enables" per the decision, satisfied by one call doing both, not two
  ordered calls.

`serviceWifi()`'s existing lazy-begin branch changes from the
ternary to:

```
if (wifiCredsExplicit_) {
  config.ssid = wifiSsid_;
  config.password = wifiPassword_;
} else {
  config.ssid = kWifiSsid;
  config.password = kWifiPassword;
}
```

**Design question 2, settled concretely**: `setupWifi("")` sets
`wifiCredsExplicit_ = true` with an empty stored SSID, then calls
`enableWifi()` same as any other call. `WifiLink::begin()` sees an
empty `config.ssid`, enters `kDisabled`, and returns before touching
`uart_.begin()` at all (`wifi_link.cpp:217-222`) — confirmed by
reading `begin()` and `service()` (`service()` returns immediately
when `state_ == kDisabled`, `wifi_link.cpp:745-746`). So "disables"
means the link never leaves `kDisabled` and never opens UARTE1, at the
same zero cost the pre-existing sentinel comment already promises for
"no module fitted" — `setupWifi("")` and "never called" now differ
only in `wifiCredsExplicit_`, not in outward behavior when nothing
else changes.

`enableWifiLink()` and the deploy-time bake are **unchanged**: with no
program ever calling `setupWifi()`, `wifiCredsExplicit_` stays `false`,
so `serviceWifi()` takes the same `kWifiSsid`/`kWifiPassword` branch it
always has. A `make_deploy.py` fleet build and `test/test.ts` are
byte-for-byte unaffected.

**Design question 3, settled**: extend `emitWifiDebug()`'s one
`DBG:wifi` line with `credsrc=%d trunc=%u` (`credsrc`: 0=baked,
1=explicit-program; `trunc`: the bitmask above). Budget check against
`wifiDbgBuf_[320]` (`protocol.h:465`): walking the existing format
string's literal text plus each field's worst-case width (`ip`/`peer`
up to 15 chars each, the four `%lu` counters up to 10 digits each,
`cmd`/`reply` up to `kTraceCommand`-1/`kTraceReply`-1 = 47/71 chars,
`wifi_link.h:406-407`) comes to roughly 294 of 320 bytes already used,
~26 bytes of headroom — too tight to add a ~19-byte field and still
have margin for the next thing someone appends. `wifiDbgBuf_` grows to
384 bytes alongside the new field, restoring comfortable headroom
(~90 bytes).

**Shim and TS surface** (mechanical, following two established
patterns exactly — no new pattern):
`src/shims.cpp` gets a `setupWifi(String ssid, String password)` shim
using `registerRunName()`'s exact idioms: `//%` immediately above the
declaration (an intervening comment fails the PXT shim scanner with a
misleading "declaration not understood"), and emptiness tested via the
PXT String's own `getUTF8Size()` rather than the `MSTR()`/
`toCharArray()` result, because at size 0 that path returns junk, not
a clean `""` (measured gopiv 2026-09-07, fw 1.20260907.1 — the same
trap `registerRunName()`'s comment documents). `src/blocks/run.ts`
exports `setupWifi(ssid: string, password: string = "")` with
`//% blockHidden=true`, placed the same way `enableWifiLink()` is,
directly above it. `src/blocks/sim.ts` gets `_setupWifi`, recording
into module-local sim variables and doing nothing else — the
`_setupRadio` pattern, not the `_enableWifiLink` no-op pattern,
because a test might reasonably want to assert what the sim program
called it with even though there is no WiFi module to simulate.

### Design Rationale

**Decision**: an explicit `wifiCredsExplicit_` bool, not a sentinel
encoded in the stored SSID itself.
**Context**: the prior-art patch's ternary
(`wifiSsid_[0] ? wifiSsid_ : kWifiSsid`) cannot express "explicitly
disabled" separately from "never called" — both present as an empty
stored SSID — which is exactly what the stakeholder decision requires
`setupWifi("")` to do differently from an unconfigured build.
**Alternatives considered**: (a) keep the ternary and accept that
`setupWifi("")` falls back to the bake — rejected, it is the literal
opposite of the decision; (b) a magic first byte distinguishing "cell
never written" from "cell written empty" — rejected as more fragile
(an off-by-one in the sentinel byte silently reintroduces the same
bug) for no size or clarity win over a bool.
**Why this choice**: the bool is the smallest state that makes the
three cases (never called / called with real credentials / called
with `""`) mutually distinguishable, and it reads directly in
`serviceWifi()`'s branch instead of through an indirect sentinel.
**Consequences**: one extra byte of `Protocol` state; the lazy-begin
branch is an explicit if/else instead of a ternary, which is also
slightly more readable at the point that matters.

### Migration Concerns

None — additive. `wifiCredsExplicit_` defaults `false`, so any build
with no program calling `setupWifi()` takes the exact same code path
it does today. No flash layout, wire protocol, or persisted-state
change.

## Use Cases

Compact sprint — brief use cases, not full narrative treatment.

### SUC-001: A student program sets WiFi credentials and joins
Parent: none (new capability; no existing UC covers WiFi bring-up from
a student program)

- **Actor**: A student's `on start` code (or, concretely, the
  `nezha-robot-template`'s `test/boot.ts` reading its own gitignored
  `secrets.ts`).
- **Preconditions**: Ai-WB2 module fitted; firmware includes this
  sprint's `setupWifi()`.
- **Main Flow**: `on start` calls `diffDrive.setupWifi(WIFI_SSID,
  WIFI_PASSWORD)`. `Protocol` copies and stores the credentials, marks
  them explicit, and enables the link in one call. The next
  `serviceWifi()` pass begins `WifiLink` with the stored, explicit
  credentials rather than the (empty) deploy-time bake.
- **Postconditions**: the link proceeds through `WifiLink`'s normal
  state machine toward `kReady` using the program's own network,
  independent of whether `make_deploy.py` baked anything.
- **Acceptance Criteria**:
  - [ ] `setupWifi(ssid, password)` exists, is `//% blockHidden=true`,
        callable from TS/JS, not present in the toolbox.
  - [ ] Calling it before the link begins results in `WifiLink`
        receiving the program's credentials, not the (empty) bake.

### SUC-002: A student program disables WiFi explicitly
Parent: none

- **Actor**: student `on start` code.
- **Preconditions**: same as SUC-001.
- **Main Flow**: `on start` calls `diffDrive.setupWifi("")`.
- **Postconditions**: `wifiCredsExplicit_` is `true` with an empty
  stored SSID; `WifiLink::begin()` sees an empty SSID, enters
  `kDisabled`, and never opens UARTE1 — the same zero-cost outcome as
  a robot with no module fitted, reached deliberately rather than by
  omission.
- **Acceptance Criteria**:
  - [ ] `setupWifi("")` results in the link staying `kDisabled`
        forever, distinguishably from "never called" only in
        `wifiCredsExplicit_`, never in observable link behavior.
  - [ ] A build where no program calls `setupWifi()` at all is
        byte-for-byte unaffected (regression bar from the roadmap).

### SUC-003: Truncation and a late call are both diagnosable from one line
Parent: none

- **Actor**: a bench operator reading `DBG:wifi` over USB.
- **Preconditions**: a program calls `setupWifi()` with a SSID or
  password longer than the owned cells, or calls it again after the
  link has already begun.
- **Main Flow**: (a) an over-length credential is clipped at the copy
  and `wifiCredsTruncated_` records which field; the next `DBG:wifi`
  line's `credsrc=`/`trunc=` fields show it. (b) a call arriving after
  `wifiBegun_` is set is refused (storage untouched) and emits its own
  `DBG:wifi late setupWifi() ignored` line.
- **Postconditions**: "joins nothing, no reason" cannot happen for
  either cause — both are visible in serial/radio/WiFi-mirrored debug
  output, not silent.
- **Acceptance Criteria**:
  - [ ] An over-length SSID or password is clipped, not overflowed,
        and the clip is visible in `DBG:wifi`.
  - [ ] A late `setupWifi()` call changes no stored credential and is
        visible in debug output.

## GitHub Issues

(GitHub issues linked to this sprint's tickets. Format: `owner/repo#N`.)

## Definition of Ready

Before tickets can be created, all of the following must be true:

- [x] Sprint planning document is complete (sprint.md, including its
      Architecture and Use Cases sections)
- [x] Architecture review passed (or skipped, for changes with no
      architectural impact) — passed, compact-tier scoped review
- [ ] Stakeholder has approved the sprint plan

## Tickets

| # | Title | Depends On |
|---|-------|------------|
| 001 | Protocol core: `setupWifi()` storage, precedence flag, late-call guard, truncation, `DBG:wifi` field | — |
| 002 | Shim and TS/sim surface: `setupWifi()` entry point | 001 |
| 003 | Host-level test: `setupWifi()` precedence, truncation, and late-call behavior (source-pin) | 001 |
| 004 | TS/shim arity and toolbox-visibility pin test for `setupWifi()` | 002 |
| 005 | Docs: consumer-side `secrets.ts` convention, and `pxt.json` version bump | 001, 002, 003, 004 |

Tickets execute serially in the order listed.
