---
id: '037'
title: 'Runtime identity setters: HELLO banner role/common_name and kProfile'
status: done
branch: sprint/037-runtime-identity-setters-hello-banner-role-common-name-and-kprofile
use-cases: []
issues:
- high/hello-banner-role-and-common-name-are-hardcoded.md
- high/kprofile-needs-a-runtime-setter.md
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sprint 037: Runtime identity setters: HELLO banner role/common_name and kProfile

## Goals

Give programs a runtime path to set the three identity fields that are
currently baked-only string literals: the HELLO banner's `role`
(`NEZHA2`) and `common_name` (`robot`), and the `ID` reply's `profile`
(`kProfile`). All three are the same shape of problem — a deploy-time
bake with no runtime equivalent — and sprint 036's `setupWifi()` is the
established, already-reviewed precedent both source issues explicitly
point at. Plan them together as "one pattern applied three times" so
the three setters share one Protocol-owned-buffer design, one
truncation/validation convention, and one test shape, rather than
drifting into three ad hoc ones.

Concretely: `Protocol::setDeviceRole(role, commonName)` for the banner's
fields 2-3, and `Protocol::setProfile(name)` for `ID`'s `profile` field,
both with TS/shim/toolbox surface mirroring `setupWifi()`'s arity and
visibility shape (sprint 036 ticket 004 pinned that shape with a test —
match it, don't reinvent it).

## Problem

`WireHandler::sendBanner()` (`src/comms/wire_handler.cpp:1431-1438`)
formats `NEZHA2` and `robot` as string literals baked into the
`snprintf` format string itself — they are not even fields on
`Wire::Identity` (`wire_handler.h:96-102`), so there is no struct member
for a setter to point at yet. Separately, `identity.profile = kProfile`
(`protocol.cpp:576`) is a compile-time constant with the same
no-runtime-path problem, one `Wire::Identity` already anticipated
("the adapter owns the storage (a string literal **or a robot-config
field**)") but never delivered on.

A student who pastes a calibration block at runtime has genuinely
changed which robot's config is loaded, but `ID`'s `profile` field still
reports the baked name (or `unbaked`) — silently wrong. And nothing
today lets a program identify itself as anything other than the fixed
`NEZHA2 robot` pair in the HELLO banner, which blocks any firmware
variant or student experiment that wants a truthful banner.

## Solution

Follow sprint 036's `setupWifi()` pattern
(`src/comms/protocol.cpp:229`), adapted per issue to the fact that
identity fields are simpler than WiFi credentials:

- `WireAdapter::identity()` hands out a struct of **borrowed
  `const char*`** that `sendBanner()` / the `ID` reply's `snprintf`
  dereference at emit time (not at struct-construction time). Point
  `identity.role`, `identity.commonName`, and `identity.profile` at
  Protocol-owned buffers **seeded from the existing `kRole`/`kCommonName`
  (new) and `kProfile` (existing) constants** instead of at literals.
  A runtime setter than just writes into that buffer, and the very next
  banner/`ID` reply picks it up — **no second `setIdentity()` call and
  no ordering trap**, unlike WiFi's `serviceJoin()` re-read hazard which
  is what forces `setupWifi()`'s late-call guard to exist in the first
  place. Neither of these two setters needs a late-call guard, and
  `setProfile()` explicitly must succeed even after the first `ID` reply
  has already gone out (pin that as a test — it is the interesting
  divergence from WiFi's behavior).
- Fixed-size owned buffers with `snprintf`-based clipping close a real
  budget hazard: the 96-byte banner buffer and the 128-byte `id` reply's
  48-char `profile` budget currently have **no code-enforced cap** and
  are safe today only because the values are compile-time literals.
  Runtime input must clip into bounded buffers, same shape as
  `wifiSsid_[33]`.
- The banner's `role`/`common_name` fields carry an extra, non-optional
  constraint the profile setter does not: **internal whitespace must be
  rejected or stripped**, because the banner is space-separated and
  parsed positionally downstream (radio-robot-lib's codec). One embedded
  space turns a 4-field reply into 5 and breaks every consumer. Validate
  at the setter.
- `profile`'s open design question (how to distinguish a baked profile
  from a runtime-set one) is resolved per the issue's recommendation: no
  new positional field in `id` — fields 0-2 are pinned outside this repo
  — instead report provenance on a `DBG:profile` line mirroring the
  existing `DBG:wifi` line (`src=baked|runtime name=<name> trunc=<n>`).

## Success Criteria

- `Protocol::setDeviceRole(role, commonName)` and
  `Protocol::setProfile(name)` exist, are reachable from TS (`run.ts`)
  with a `sim.ts` stub, and are toolbox-visible following
  `setupWifi()`'s exact shape.
- The DEFAULT banner and DEFAULT `ID` reply are byte-identical to
  today's output — this is the load-bearing regression check, proving
  the literal-to-owned-buffer refactor changed nothing when no setter is
  called. Existing pinned tests must keep passing unmodified:
  `tests/host/test_wire_grammar.py:457,470,544,587,631`,
  `tests/tools/test_rogo.py`, `test_robotlink.py`, `test_fieldlink.py`,
  `tests/host/test_wifi_link.py:413`.
- Setter precedence, truncation, and whitespace-rejection are covered by
  new host tests mirroring sprint 036 tickets 003/004's shape.
- `setProfile()` after the first `ID` reply succeeds (unlike WiFi's
  late-call rejection) — pinned by a test, not just asserted in prose.
- On-hardware confirmation (`HELLO` / `ID` before and after calling each
  setter) is run and its result recorded as MEASURED or UNVERIFIED per
  `.claude/rules/measurement-citations.md` — do not write "MEASURED"
  without a capture artifact backing it.

## Scope

### In Scope

- `Wire::Identity` (`wire_handler.h`): add `role`, `commonName` fields
  (defaulted for byte-identical default behavior); `profile` already
  exists as a field, gains a Protocol-owned backing buffer instead of
  pointing at the `kProfile` literal.
- `protocol.cpp`: `kRole = "NEZHA2"` / `kCommonName = "robot"` constants
  beside `kProfile`/`kVersion`; owned buffers seeded from those
  constants plus `kProfile`; `setDeviceRole()` and `setProfile()`
  implementations with clipping and (for the banner fields) whitespace
  validation; the `DBG:profile` provenance line.
- `wire_handler.cpp`: `sendBanner()` reads `role`/`commonName` from
  `identity` instead of literals in the format string.
- TS/shim/toolbox surface: `src/blocks/run.ts`, `src/shims.cpp`,
  `src/blocks/sim.ts` — new blocks for both setters, matching
  `setupWifi()`'s arity and visibility shape exactly.
- Host tests for both setters: default-output byte-identity, precedence
  (setter beats baked constant), truncation, whitespace handling for the
  banner fields, never-called vs called-with-empty distinction, and the
  late-call-succeeds case for `setProfile()`.
- One on-hardware verification pass covering both setters.

### Out of Scope

- **The HELLO banner grammar mismatch is explicitly excluded.**
  `announce.md` specifies a colon-separated `DEVICE:` sentinel with
  `\r\n`; this firmware emits a space-separated lowercase `device` with
  `\n`. That divergence was found while investigating this sprint's
  issues but is a cross-repo, stakeholder-level protocol decision — not
  something this sprint touches. Do not change the separator, sentinel
  case, or line ending. Both source issues flag this explicitly; treat
  any drift toward "fixing" it mid-sprint as scope creep to be stopped,
  not completed work.
- Any change to `make_deploy.py`'s bake-time injection paths
  (`_inject_profile()` etc.) beyond what's needed to keep the baked
  default identical — this sprint adds a runtime path alongside the
  existing bake, it does not replace or restructure the bake mechanism.
- The calibration skill emitting `setProfile()` as the first line of its
  pasted block (`calibration-skill-emits-a-paste-able-makecode-block.md`)
  is a consumer of this sprint's new API, not part of it — a follow-on,
  not a ticket here.

## Test Strategy

Host-side unit/integration tests mirror sprint 036 tickets 003/004's
shape exactly, since both setters exist to solve the same class of
problem `setupWifi()` already solved: default-output regression
(byte-identical banner and `ID` reply with no setter called), explicit
source-precedence tests (setter beats baked constant), truncation tests
against the fixed buffer sizes, whitespace-rejection tests for the
banner's `role`/`common_name`, the never-called-vs-called-with-empty
distinction, and — the one behavioral divergence from WiFi worth its own
test — `setProfile()` succeeding when called after the first `ID` reply
has already gone out. All of `tests/host/test_wire_grammar.py`,
`test_rogo.py`, `test_robotlink.py`, `test_fieldlink.py`, and
`test_wifi_link.py` must continue passing unmodified, since none of them
should observe any behavior change from the default (no-setter-called)
path. On-hardware confirmation is one scripted `HELLO`/`ID`
before-and-after session per setter, run by the team-lead per this
project's hardware-ticket convention, with results recorded as MEASURED
(with capture artifact) or UNVERIFIED.

## Architecture

**Compact** — two new entry points on one existing module (`Protocol` /
`WireAdapter`, `src/comms/protocol.{h,cpp}` and one struct in
`src/comms/wire_handler.h`), reusing the same three boundary seams
sprint 036 established (`shims.cpp`'s free-function pattern, `run.ts` →
`sim.ts`'s hidden-block pattern, and the `DBG:` reporting convention)
unchanged. No new cross-module dependency, no dependency-direction
change, no data-model change — the new fields are firmware bookkeeping
(owned string buffers), not persisted or cross-module state.

### Architecture Overview

**What Changed**

- `Wire::Identity` (`wire_handler.h:96-102`): add `role`, `commonName`
  fields, both defaulted to `""` (matching `profile`'s existing
  default), so `sendBanner()` can read them instead of taking them from
  the format string.
- `protocol.cpp`'s identity block: add `kRole = "NEZHA2"` / `kCommonName
  = "robot"` beside `kDrivetrain`/`kProfile`/`kVersion` — named
  constants for symmetry with that block's existing style, not because
  they are deploy-injected (they are not; only `kProfile` keeps that
  property, unchanged, so `make_deploy.py::_inject_profile()`'s
  single-match regex still finds exactly one `kProfile` declaration).
- Three new Protocol-owned buffers: `roleBuf_[24]`, `commonNameBuf_[24]`,
  `profileBuf_[32]`. `profileBuf_`'s 32-byte cap matches the issue's own
  recommendation against the `id` reply's existing 48-char budget for
  that field. `roleBuf_`/`commonNameBuf_` at 24 each keep the 96-byte
  banner buffer's worst case at `"device "(7) + role(23) + " "(1) +
  commonName(23) + " "(1) + name(5) + " "(1) + serial(10) + "\n"(1) +
  NUL(1) = 74` bytes — computed the same way the `id` reply's own
  comment computes its worst case, 22 bytes of margin.
- `Protocol::setDeviceRole(const char* role, const char* commonName)`:
  rejects — no mutation, one `DBG:role rejected ...` line, nothing else
  — a null pointer or any argument containing whitespace (any byte
  where `isspace()` is true). The rejection is atomic across both
  arguments, not per-field, matching the null-guard's own
  all-or-nothing shape. Otherwise clips both into their buffers
  (truncation computed from the caller's own `strlen()` *before* the
  clip, into a bitmask `deviceRoleTruncated_`: bit0 role, bit1
  commonName) and emits one `DBG:role role=%s commonName=%s trunc=%u`
  line.
- `Protocol::setProfile(const char* name)`: rejects a null pointer OR
  embedded whitespace (see Design Rationale #3 — this extends the
  letter of the sibling issue, which did not raise whitespace for
  `profile`, but the hazard is identical: `profile` sits inside the
  `id` reply's own space-separated line the same way `role`/
  `commonName` sit inside the banner's). No late-call guard, unlike
  `setupWifi()` — identity has no live-read hazard (see Problem/
  Solution above). Clips into `profileBuf_` (truncation from the
  caller's `strlen()` before the clip), sets `profileSetAtRuntime_ =
  true`, and emits `DBG:profile src=%s name=%s trunc=%u` (`src` =
  `baked`|`runtime`).
- `Protocol::buildIdentity()`: `identity.role` / `identity.commonName` /
  `identity.profile` point at the three owned buffers, never at
  `kRole`/`kCommonName`/`kProfile` directly. `buildIdentity()` runs
  exactly once, at fiber start (`protocol.cpp:791`), which can be
  *after* a program's `on start` has already called a setter — so the
  buffers must already hold their default content before
  `buildIdentity()` ever runs. That is what the new constructor (next
  bullet) is for; `buildIdentity()` itself does no seeding.
- New `Protocol::Protocol()` constructor body, `snprintf`-seeding all
  three buffers from `kRole`/`kCommonName`/`kProfile` once, at
  construction — see Design Rationale #1 for why this is the one point
  in this sprint genuinely worth calling a decision.
  `protocol.h`'s existing comment ("NSDMI, not a hand-written
  constructor", near the `wireAdapter_` member) becomes stale and is
  updated in the same ticket.
- `WireHandler::sendBanner()` (`wire_handler.cpp:1431-1438`): format
  string changes from `"device NEZHA2 robot %s %s\n"` (two literals,
  two placeholders) to `"device %s %s %s %s\n"` reading
  `identity.role, identity.commonName, identity.name, identity.serial`
  — all four fields now come from `identity`, none from the format
  string itself.
- `shims.cpp` / `run.ts` / `sim.ts`: two new hidden blocks,
  `setDeviceRole(role, commonName)` and `setProfile(name)`, following
  `setupWifi()`'s exact shape — forward-declared free-function boundary
  entry point, `getUTF8Size()` emptiness guard (not `toCharArray()`'s
  result at size 0), `//% blockHidden=true`, and a `sim.ts` stub that
  records into module-local sim state rather than modeling anything.

**Why** — Both fields answer "who is this board, right now" to a wire
consumer, and both were compile-time-only for the same historical
reason `kWifiSsid`/`kWifiPassword` were: nothing needed a runtime path
until a student calibration workflow started loading a robot's config
at runtime after the bake already happened (kProfile), and separately
until a firmware variant wanted a truthful banner (role/commonName).
`setupWifi()` (sprint 036) proved the pattern; this sprint applies it to
the two identity surfaces the same class of gap was still open on.

**Impact on Existing Components** — `WireHandler::sendBanner()` and
`execId()` change their identity SOURCE (a Protocol-owned buffer instead
of a literal or `kProfile` directly) but not their format, byte count,
or field order; every existing consumer test named in this sprint's
Success Criteria must pass unmodified. `Protocol`'s public surface
grows by two methods; nothing that already calls into `Protocol`
(radio, WiFi, telemetry, RUN dispatch) is touched.

### Design Rationale

**1. Seed the three owned buffers in an explicit `Protocol()`
constructor body, not in `buildIdentity()` and not via NSDMI.**
*Context*: a `char` array cannot be NSDMI'd from a runtime `const
char*` (`kRole`/`kCommonName`/`kProfile` are pointers, not string-
literal tokens), and `buildIdentity()` runs exactly once, at fiber
start — which can be after a program's `on start` has already called a
setter. *Alternatives considered*: (a) seed lazily inside
`buildIdentity()`, guarded by "buffer still empty" — rejected, because
it cannot tell "never called" from "called with a deliberate empty
string" without reintroducing exactly the explicit-flag mechanism
`setupWifi()` needed and this sprint's Solution section explicitly
avoids for identity; (b) give each buffer its own literal NSDMI
initializer (`char roleBuf_[24] = "NEZHA2";`) instead of copying from
the named constant — rejected for `profileBuf_` specifically because
`kProfile` is genuinely substituted at deploy time by
`make_deploy.py::_inject_profile()`'s single-source regex, so
`profileBuf_` must copy `kProfile`'s *compiled* value at runtime, not
carry an independent literal that the deploy substitution would miss.
*Why this choice*: `protocol()`'s lazy-singleton accessor (`new
Protocol()`) already guarantees construction happens before the first
method call reaches the object from any caller — including a setter
invoked as literally the first statement of `on start` — so
constructor-time seeding is race-free regardless of call order, with no
flag needed. *Consequences*: `protocol.h`'s "NSDMI, not a hand-written
constructor" comment is now inaccurate and must be corrected in the
same ticket that adds the constructor, or a future contributor reading
only that comment could "helpfully" move the seed into
`buildIdentity()` and reintroduce the ordering bug.

**2. `setDeviceRole()` rejects whitespace outright rather than
stripping it.** *Context*: the issue phrases it as "rejected or
stripped"; either closes the position-parsing hazard. *Alternatives*:
strip (delete/replace embedded whitespace and proceed) — rejected
because it silently turns what the caller asked for into something
that only looks similar, which is a worse failure mode for a field a
human reads off the wire to identify a physical board than a visible
no-op with a `DBG:` line explaining why. *Why*: matches this codebase's
existing convention — the late-call guard's own comment says the write
"is refused outright rather than merely skipped-but-harmless."
*Consequences*: a caller must retry with a clean string; nothing
partial ever reaches the wire.

**3. `setProfile()` gets the same whitespace rule as `setDeviceRole()`,
even though the kProfile issue never raises it.** *Context*: `profile`
is one field inside the `id` reply's own space-separated, positionally-
parsed line (`wire_handler.cpp:828`) — the identical shape of hazard
`announce.md`'s codec has for the banner. *Alternatives*: leave
`setProfile()` unvalidated, exactly as scoped in the source issue —
rejected, because doing so would ship a known transport-breaking input
class on one of two nearly-identical setters in the same sprint, for no
saved effort (the check is the same three lines). *Why*: consistency
and correctness outrank strictly minimizing diff from the issue text
when the issue's omission looks like an oversight rather than a
decision — flagged back to the stakeholder in this sprint's report
rather than silently assumed.

### Migration Concerns

None: no persisted state, no wire-format change (field count, order,
and separators are unchanged — only two banner fields and one `id`
field switch source from literal to owned buffer), no deploy-tooling
change. The one thing this sprint cannot verify on the host is that
constructor-time seeding actually wins the race against an `on start`
setter call on real hardware — see Success Criteria's on-hardware
verification line, and ticket 007 below.

## Use Cases

Compact sprint — brief use cases, not full narrative treatment.

### SUC-001: A program truthfully labels itself in the HELLO banner
Parent: none (new capability; no existing UC covers banner identity
override)

- **Actor**: firmware `on start` code (a variant build, or a student
  experiment) that is not the stock `NEZHA2 robot` pair.
- **Preconditions**: firmware includes this sprint's `setDeviceRole()`.
- **Main Flow**: `on start` calls
  `diffDrive.setDeviceRole(role, commonName)` with two space-free
  strings. `Protocol` clips them into `roleBuf_`/`commonNameBuf_` and
  emits `DBG:role`. The next `sendBanner()` call reads both from
  `identity`.
- **Postconditions**: every subsequent HELLO banner carries the
  program's own `role`/`commonName`, with no second call needed and no
  ordering trap relative to when the protocol fiber starts.
- **Acceptance Criteria**:
  - [ ] `setDeviceRole(role, commonName)` exists, is `//%
        blockHidden=true`, callable from TS/JS, not present in the
        toolbox.
  - [ ] A build where no program calls `setDeviceRole()` at all emits a
        byte-for-byte identical banner to today's (regression bar).
  - [ ] Calling it before OR after the protocol fiber starts is picked
        up by the next banner either way.

### SUC-002: A program reports which robot's config it actually loaded
Parent: none

- **Actor**: a student program that has just executed a pasted
  calibration block (or any runtime config load).
- **Preconditions**: firmware includes this sprint's `setProfile()`.
- **Main Flow**: `on start` (or any later point) calls
  `diffDrive.setProfile("vevov")`. `Protocol` clips it into
  `profileBuf_`, marks `profileSetAtRuntime_`, and emits `DBG:profile
  src=runtime name=vevov trunc=0`.
- **Postconditions**: the next `id` reply's `profile` field reads
  `vevov` instead of the baked value (or `unbaked`) — including a call
  made after the first `id` reply has already gone out, which must
  succeed (the one deliberate divergence from `setupWifi()`'s late-call
  refusal).
- **Acceptance Criteria**:
  - [ ] `setProfile(name)` exists, is `//% blockHidden=true`, callable
        from TS/JS, not present in the toolbox.
  - [ ] A build where no program calls `setProfile()` at all emits a
        byte-for-byte identical `id` reply to today's (regression bar).
  - [ ] A call made after the first `id` reply has already gone out
        still succeeds and is reflected in the next `id` reply.

### SUC-003: Invalid or oversize input is clipped or refused, never silently
Parent: none

- **Actor**: a bench operator reading `DBG:role`/`DBG:profile` over
  USB, or a student whose typo would otherwise break every downstream
  consumer's field parsing.
- **Preconditions**: a program calls `setDeviceRole()` or
  `setProfile()` with an over-length value, or a value containing
  whitespace.
- **Main Flow**: (a) an over-length value is clipped at the copy and
  the relevant `trunc` bit/flag is set; the emitted `DBG:` line shows
  it. (b) a value containing whitespace is refused outright — the
  stored value is unchanged and a `DBG:` line names the rejection.
- **Postconditions**: a broken banner or `id` line — extra or missing
  fields from an embedded space, or an overflowed buffer from an
  over-length name — cannot happen; both failure classes are visible in
  debug output, not silent.
- **Acceptance Criteria**:
  - [ ] An over-length `role`/`commonName`/`profile` is clipped, never
        overflowed, and the clip is visible via `trunc=`.
  - [ ] A `role`, `commonName`, or `profile` argument containing any
        whitespace character leaves the prior stored value untouched
        and is visible in debug output.

## GitHub Issues

(GitHub issues linked to this sprint's tickets. Format: `owner/repo#N`.)

## Definition of Ready

Before tickets can be created, all of the following must be true:

- [ ] Sprint planning document is complete (sprint.md, including its
      Architecture and Use Cases sections)
- [ ] Architecture review passed (or skipped, for changes with no
      architectural impact)
- [ ] Stakeholder has approved the sprint plan

## Tickets

| # | Title | Depends On |
|---|-------|------------|
| 001 | Protocol core: setDeviceRole() — role/commonName owned buffers, constructor seeding, whitespace rejection, truncation | — |
| 002 | Protocol core: setProfile() — profileBuf_ owned buffer, constructor seeding extension, whitespace rejection, truncation, DBG:profile provenance | 001 |
| 003 | Shim and TS/sim surface: setDeviceRole() and setProfile() entry points | 001, 002 |
| 004 | Host-level source-pin tests: setDeviceRole() precedence, truncation, whitespace, and constructor-seeding shape | 001 |
| 005 | Host-level source-pin tests: setProfile() precedence, truncation, whitespace, and late-call-succeeds behavior | 002 |
| 006 | TS/shim arity and toolbox-visibility pin test for setDeviceRole() and setProfile() | 003 |
| 007 | On-hardware verification: HELLO/ID before and after setDeviceRole() and setProfile() | 004, 005, 006 |

Tickets execute serially in the order listed.
