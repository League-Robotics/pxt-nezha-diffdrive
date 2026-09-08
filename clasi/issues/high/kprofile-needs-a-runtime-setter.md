---
status: pending
sprint: '037'
tickets:
- 037-002
- 037-003
- 037-005
- 037-006
- 037-007
---

# `kProfile` needs a runtime setter — a pasted calibration block IS loading a robot's config

Priority: **High** — it is the other half of what a consumer's `ID`
reply should say, and it is what makes the calibration workflow
self-reporting instead of silent.

Stakeholder, 2026-09-07: "If you've loaded a bunch of configuration in
for a robot at runtime, then shouldn't you be able to reset the
kProfile?"

Yes. `profile` means *which robot's config this image is running*. A
student who pastes the calibration block from
`calibration-skill-emits-a-paste-able-makecode-block.md` — track width,
travel calib, rotational slip, OTOS lever arm — has loaded exactly that,
at runtime. Reporting `profile unbaked` afterwards is no longer true,
and it is true in the one place a person would look to find out which
robot they are debugging.

## Current state

`identity.profile = kProfile` (`src/comms/protocol.cpp:576`), a
compile-time constant substituted into the deploy scratch copy by
`make_deploy.py::_inject_profile()`. There is no runtime path. The
`Wire::Identity` doc comment (`src/comms/wire_handler.h:90-96`) already
anticipated one — "the adapter owns the storage (a string literal **or a
robot-config field**)" — but nothing ever supplied the second case.

## The precedent to follow: sprint 036's `setupWifi()`

This is the *same problem already solved once*, merged 2026-09-07.
`kWifiSsid`/`kWifiPassword` were deploy-time bakes a consumer could not
perform, so `Protocol::setupWifi()` (`protocol.cpp:229`) gave programs a
runtime path, with:

- owned `char` storage, copied not borrowed (`wifiSsid_[33]`)
- `wifiCredsExplicit_` to separate "called with empty" from "never
  called" — the two states a `buf[0] ? buf : kBaked` ternary cannot tell
  apart, which is exactly the bug the prior-art patch had
- truncation computed from the caller's own `strlen` **before** the
  clip, so the flag reports the caller's mistake, not the clip
- a late-call guard, and a `DBG:` line naming which source won

`setProfile()` should mirror all of it. Reviewers should read
`setupWifi()` first and treat divergence from it as needing a reason.

## One thing that makes this EASIER than setupWifi

`setupWifi()` needs its late-call guard because `WifiLink::Config`
borrows into the credential buffers and `serviceJoin()` re-reads them on
every retry, so a late write reaches into a live join.

Identity has no such hazard. `WireAdapter::identity()` copies a struct of
**borrowed `const char*`**, and `wire_handler.cpp:828`'s `snprintf`
dereferences `identity.profile` at reply time. So if `identity.profile`
is pointed at a Protocol-owned buffer *seeded from `kProfile`* — rather
than at the literal — then:

- a `setProfile()` at any time is picked up by the **next** `ID` reply,
- with **no** second `setIdentity()` call and **no** ordering trap,
- and it works whether the program calls it before or after the protocol
  fiber starts.

That is worth doing deliberately: point at the buffer, seed the buffer
from `kProfile`, and the baked path is byte-identical to today.

## It also closes a latent budget hazard

`wire_handler.cpp:815-826` budgets `profile` at 48 chars inside a
128-byte `id` reply and notes it "has no code-enforced length cap" —
safe today only because it is a compile-time literal. A runtime setter
with no cap would hand that budget to student input. A fixed
`profileBuf_[32]` with `snprintf` clipping (stems in
`radio-robot-lib/config/robots/` are 5-11 chars) makes it bounded by
construction.

## Open design question — recommendation, needs a decision

A baked profile and a pasted one are **not** the same state: a bake
compiles in the whole config (radio channel, motor mapping, geometry), a
pasted block sets only what the block sets. `profile` is the provenance
field, so that difference should be visible somewhere.

It must NOT become a new positional field in the middle of `id` —
fields 0-2 are pinned outside this repo by radio-robot-lib.

**Recommended:** keep `id`'s `profile` field as the plain name, and
report the source on a `DBG:profile` line mirroring `DBG:wifi`
(`src=baked|runtime name=vevov trunc=0`). Rejected alternative: a name
suffix like `vevov-rt`, which collides with the existing suffix
convention that `_inject_profile()` already uses for debug variants
(`tovez-faultspin`).

## Consumer surface

`diffDrive.setProfile("vevov")` — TS in `src/blocks/run.ts` with the
`sim.ts` shim, following `setupWifi()`'s arity and toolbox-visibility
shape exactly (sprint 036 ticket 004 pinned those with a test; the same
traps apply).

The calibration skill should emit it as the **first** line of the
pasted block, so the block that loads the config is also the block that
says whose config it is.

## Verification

Host tests mirroring sprint 036 tickets 003/004: source-pin for
precedence (`setProfile` beats `kProfile`), the never-called vs
called-with-empty distinction, truncation, and late-call-after-first-ID
(which should now *succeed*, unlike WiFi — pin that, it is the
interesting difference). On-hardware confirmation is an `ID` reply
before and after a `setProfile()` call — UNVERIFIED until run.
