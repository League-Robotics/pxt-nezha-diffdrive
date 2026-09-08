---
id: '001'
title: "Protocol core: setDeviceRole() \u2014 role/commonName owned buffers, constructor\
  \ seeding, whitespace stripping, truncation"
status: done
use-cases:
- SUC-001
- SUC-003
depends-on: []
github-issue: ''
issue: high/hello-banner-role-and-common-name-are-hardcoded.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Protocol core: setDeviceRole() — role/commonName owned buffers, constructor seeding, whitespace stripping, truncation

**Stakeholder decision, recorded on the sprint's `stakeholder_approval`
gate 2026-09-08: whitespace is STRIPPED AND ACCEPTED, not rejected.**
The issue's own wording was "rejected or stripped" — genuinely open —
and reject-with-DBG was recommended, but the stakeholder chose
strip-and-accept. `setDeviceRole("my robot", "the bot")` SUCCEEDS and
stores `myrobot`/`thebot`; the call never fails, never keeps the prior
value, and never leaves the field unset because of whitespace. "Strip"
means remove ALL whitespace characters — leading, trailing, AND
internal (not just trim, not collapse) — per that same approval.

## Description

Add the C++ core of `Protocol::setDeviceRole(const char* role, const
char* commonName)` per `sprint.md`'s Architecture section. This ticket
is `src/comms/protocol.{h,cpp}` and `src/comms/wire_handler.{h,cpp}`
only — it does NOT touch `shims.cpp`, `run.ts`, or `sim.ts` (ticket
003), and does NOT touch `profileBuf_`/`setProfile()` (ticket 002,
which depends on this one because it extends the same constructor this
ticket introduces).

### What to add to `wire_handler.h`

In `Wire::Identity` (`wire_handler.h:96-102`), add two fields, both
defaulted to `""` exactly like the existing `profile` field:

```cpp
struct Identity {
  const char* name = "";
  const char* serial = "";
  const char* drivetrain = "";
  const char* role = "";
  const char* commonName = "";
  const char* profile = "";
  const char* version = "";
};
```

Update the struct's doc comment (currently: "the adapter owns the
storage (a string literal or a robot-config field)") to also cover the
new reality: a Protocol-owned buffer seeded from a literal, mutable at
runtime via a setter. Do not remove the existing "`name` ... is THE
authoritative board-identity field, NOT `profile`" sentence — it is
still correct and still important.

### What to add to `protocol.cpp`'s identity block (lines ~40-85)

- `constexpr const char* kRole = "NEZHA2";` and `constexpr const char*
  kCommonName = "robot";`, declared beside `kDrivetrain`/`kProfile`/
  `kVersion`. These are NOT deploy-injected (unlike `kProfile`) — they
  exist for symmetry with that block's existing style and as the single
  named source the new constructor (below) copies from. Do not use a
  name that could collide with `make_deploy.py`'s `_inject_profile()`
  regex (`r'(constexpr const char\* kProfile = ")[^"]*(";)'` — matches
  only `kProfile` by exact name, so `kRole`/`kCommonName` are safe, but
  confirm by re-reading that regex before naming anything else `k*Profile`).

### What to add to `protocol.h`'s private section

Two new owned buffers, placed near `serialBuf_` (the existing identity-
adjacent owned buffer) or near `wifiSsid_`/`wifiPassword_` — pick
whichever location reads better once you see the surrounding code, but
keep them together:

```cpp
char roleBuf_[24];        // seeded from kRole, overwritten by setDeviceRole()
char commonNameBuf_[24];  // seeded from kCommonName, overwritten by setDeviceRole()
```

Also add:

```cpp
uint8_t deviceRoleTruncated_ = 0;  // bit0 role, bit1 commonName
```

Do NOT give `roleBuf_`/`commonNameBuf_` a `= {0}` or any other NSDMI
initializer — they are seeded by the new constructor below, and a
zero-init here would be immediately overwritten anyway, which is
confusing to a future reader wondering why two initializers exist.

Declare `void setDeviceRole(const char* role, const char* commonName);`
near `setupWifi()`'s declaration, with a doc comment in the same style
(OPT-IN framing is not quite right here — there is no enable/disable
concept — instead explain: no late-call guard needed, because unlike
`WifiLink::Config`, `sendBanner()` dereferences the borrowed pointer at
EMIT time, not at some earlier "begin" time, so a call at any point is
picked up by the next banner).

### The new constructor — the one real design decision in this ticket

`Protocol` currently has NO hand-written constructor — `protocol.h`'s
comment near the `wireAdapter_` member says so explicitly ("NSDMI, not
a hand-written constructor: every member below depends only on members
declared textually above it"). A `char` array member cannot be NSDMI'd
from a runtime `const char*` (`kRole`/`kCommonName` are pointers, not
string-literal tokens usable as an array initializer), so this ticket
adds:

```cpp
Protocol::Protocol() {
  snprintf(roleBuf_, sizeof(roleBuf_), "%s", kRole);
  snprintf(commonNameBuf_, sizeof(commonNameBuf_), "%s", kCommonName);
}
```

declared in `protocol.h` (`Protocol();` — a normal public or private
constructor declaration, whichever access level the class already
uses for anything comparable; if nothing comparable exists, public) and
defined in `protocol.cpp`. No call site changes: `protocol()`'s lazy-
singleton accessor already does `gProtocol = new Protocol();`
(`protocol.cpp:848`), so it picks up whichever constructor exists.

**Why this has to be a constructor and not a seed-on-first-use inside
`buildIdentity()`**: `buildIdentity()` runs exactly ONCE, at fiber
start (`protocol.cpp:791`, the only call site), which can be AFTER a
program's `on start` has already called `setDeviceRole()`. Seeding
inside `buildIdentity()` — even guarded by "only seed if the buffer is
still empty" — cannot distinguish "never called" from "called with a
deliberate empty string" without reintroducing the exact explicit-flag
mechanism `setupWifi()` needed and this sprint deliberately avoids for
identity fields (see `sprint.md`'s Design Rationale #1). Seeding in the
constructor sidesteps this entirely: `protocol()`'s lazy-singleton
accessor guarantees construction happens before the FIRST method call
reaches the object from ANY caller, including a setter invoked as
literally the first statement of `on start` (that call is
`protocol().setDeviceRole(...)` — the `protocol()` sub-expression
constructs+seeds first, `.setDeviceRole(...)` runs second, unconditionally,
regardless of which caller got there first).

**Update the stale comment.** `protocol.h`'s "NSDMI, not a hand-written
constructor" comment (near `wireAdapter_`) becomes inaccurate once this
constructor exists. Correct it in this same ticket — e.g., "NSDMI for
every member below except `roleBuf_`/`commonNameBuf_` (and, after
ticket 002, `profileBuf_`), which the constructor seeds explicitly
because a `char` array cannot be NSDMI'd from a runtime `const char*`;
see `Protocol::Protocol()`." Do not leave the old claim standing —
a future contributor who trusts it could "helpfully" move the seeding
into `buildIdentity()` and reintroduce the ordering bug described above.

### `Protocol::setDeviceRole(const char* role, const char* commonName)`

1. If `role == nullptr || commonName == nullptr`, reject: call
   `emitLine("DBG:role rejected: null argument")` and return without
   touching `roleBuf_`/`commonNameBuf_`/`deviceRoleTruncated_`. This is
   the ONLY rejection path left in this function — see the stakeholder
   decision at the top of this ticket. There is no `DBG:role rejected:
   whitespace` message anymore; do not add one.
2. Strip whitespace from `role` and, independently, from `commonName`:
   remove EVERY `isspace()` byte (`<cctype>`) — leading, trailing, and
   internal — from each string. This is a strip, not a rejection: a
   whitespace byte in either argument never causes the call to fail.
   The two fields are stripped independently of each other (there is no
   cross-field atomicity concern here the way there was for the old
   reject-both-or-neither behavior — each field's whitespace only
   affects that field's own stripped value).
3. **Ordering: strip first, then measure, then clip.** Compute
   truncation from each STRIPPED string's length — NOT the raw
   argument's `strlen()` — against its buffer's `sizeof`, BEFORE
   copying. `stripped_role_len >= sizeof(roleBuf_)` sets bit0 of
   `deviceRoleTruncated_`, `stripped_commonName_len >=
   sizeof(commonNameBuf_)` sets bit1. A value whose RAW length only
   exceeds the buffer because of whitespace that is about to be removed
   must NOT be reported as truncated — only the post-strip length
   counts. Then copy the stripped value into its buffer, clipped safely
   to fit (e.g. `snprintf`).

   Implementation note: since the raw argument's length is unbounded,
   the natural implementation is a single fused pass per string that
   writes each non-whitespace byte into the destination buffer (while
   the destination still has room) and separately keeps counting the
   total stripped length even past the buffer's capacity, so the
   truncation flag reflects the full stripped length rather than only
   what fit. This avoids needing an intermediate buffer sized to the
   untrimmed input.
4. Emit `DBG:role role=%s commonName=%s trunc=%u` (using the
   now-current, stripped-and-possibly-clipped buffer contents and
   `deviceRoleTruncated_`) via `emitLine()`.
5. Add the free-function boundary entry point beside
   `protocolSetupWifi()`'s (same file, same reasoning — keeps
   `shims.cpp` from needing `protocol.h`):
   `void protocolSetDeviceRole(const char* role, const char* commonName)
   { protocol().setDeviceRole(role, commonName); }`. Declare it wherever
   `protocolSetupWifi`'s declaration lives, for ticket 003 to pick up.

### `Protocol::buildIdentity()`

Change:
```cpp
identity.drivetrain = kDrivetrain;
identity.profile = kProfile;
```
to (profile stays `kProfile` in THIS ticket — ticket 002 changes that
line):
```cpp
identity.drivetrain = kDrivetrain;
identity.role = roleBuf_;
identity.commonName = commonNameBuf_;
identity.profile = kProfile;
```

### `WireHandler::sendBanner()` (`wire_handler.cpp:1431-1438`)

Change:
```cpp
char buf[96];
snprintf(buf, sizeof(buf), "device NEZHA2 robot %s %s\n", identity.name,
              identity.serial);
```
to:
```cpp
char buf[96];
snprintf(buf, sizeof(buf), "device %s %s %s %s\n", identity.role,
              identity.commonName, identity.name, identity.serial);
```
Update the buffer-budget comment (if one exists nearby, or add one
matching the `id` reply's own style at `wire_handler.cpp:812-826`):
worst case `"device "(7) + role(23) + " "(1) + commonName(23) + " "(1)
+ name(5) + " "(1) + serial(10) + "\n"(1) + NUL(1) = 74` bytes against
the 96-byte buffer — 22 bytes of margin, no resize needed.

## Acceptance Criteria

- [x] `Wire::Identity` has `role`/`commonName` fields, both defaulted to
      `""`.
- [x] `Protocol::Protocol()` exists, seeds `roleBuf_`/`commonNameBuf_`
      from `kRole`/`kCommonName`, and is reached (unmodified) by
      `protocol()`'s existing `new Protocol()` call site.
- [x] `protocol.h`'s "NSDMI, not a hand-written constructor" comment is
      corrected to describe the new exception.
- [x] `Protocol::setDeviceRole(role, commonName)` exists with: null
      rejection (the only rejection path), whitespace STRIPPING (every
      `isspace()` byte removed from `role` and, independently, from
      `commonName` — leading, trailing, and internal; the call still
      succeeds), truncation computed from each STRIPPED string's length
      before the clip (strip-then-measure-then-clip; a raw length that
      only overflows because of whitespace about to be removed must NOT
      be flagged truncated), and a `DBG:role` emission on both the
      null-rejection and success paths.
- [x] `setDeviceRole("my robot", "the bot")` succeeds and stores
      `myrobot`/`thebot` — no rejection, no partial application, no
      unset field.
- [x] A role or commonName value whose RAW length (before stripping) is
      `>= sizeof(roleBuf_)`/`sizeof(commonNameBuf_)`, but whose STRIPPED
      length is `<` that `sizeof`, is stored IN FULL, untruncated — the
      "whitespace-only overflow" case — and the corresponding bit of
      `deviceRoleTruncated_` is NOT set.
- [x] `buildIdentity()` points `identity.role`/`identity.commonName` at
      `roleBuf_`/`commonNameBuf_`, not at `kRole`/`kCommonName`
      directly.
- [x] `sendBanner()` reads `role`/`commonName`/`name`/`serial` entirely
      from `identity`; no literal remains in its format string.
- [x] With no program ever calling `setDeviceRole()`, the emitted banner
      is byte-for-byte identical to today's `"device NEZHA2 robot %s
      %s\n"` output — this is the regression bar. Verify by hand
      against `tests/host/test_wire_grammar.py`'s existing banner
      assertions (do not run the full suite yet — ticket 004 adds the
      dedicated pin test; here, just confirm by inspection/local
      compile that nothing in the existing suite's banner assertions
      would observe a difference).
- [x] A call to `setDeviceRole()` made before `buildIdentity()` runs
      (i.e., before the protocol fiber starts) is NOT overwritten later
      — reasoned from the constructor-seeding design above; this is
      UNVERIFIED on real hardware until ticket 007's on-hardware pass
      (see `.claude/rules/measurement-citations.md` — do not claim
      MEASURED without that capture).
- [x] `tests/tools/test_make_deploy_wifi.py` and any existing
      `make_deploy.py` profile-injection tests still pass untouched —
      this ticket does not touch `make_deploy.py`, `kProfile`, or
      `kDrivetrain`/`kVersion`.

## Testing

- **Existing tests to run**: whatever `tests/host/` target(s) build
  `protocol.cpp`/`wire_handler.cpp` today (`grep -rl
  "protocol.cpp\|wire_handler.cpp" tests/host/`); confirm no build
  breakage from the new fields/constructor/method.
- **New tests to write**: none in this ticket — the host-level
  precedence/truncation/whitespace/never-called-vs-empty test is
  ticket 004, once this ticket's C++ surface exists for it to pin
  against.
- **Verification command**: scope to the modules this ticket touches —
  find with `grep -rl protocol.cpp tests/host/` and
  `grep -rl wire_handler.cpp tests/host/`, run those. The full suite
  runs once, inside `close_sprint`.
