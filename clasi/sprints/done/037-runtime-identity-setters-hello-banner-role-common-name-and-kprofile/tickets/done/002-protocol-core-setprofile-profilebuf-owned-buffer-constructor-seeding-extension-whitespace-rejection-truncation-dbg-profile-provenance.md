---
id: '002'
title: "Protocol core: setProfile() \u2014 profileBuf_ owned buffer, constructor seeding\
  \ extension, whitespace stripping, truncation, DBG:profile provenance"
status: done
use-cases:
- SUC-002
- SUC-003
depends-on:
- '001'
github-issue: ''
issue: high/kprofile-needs-a-runtime-setter.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Protocol core: setProfile() — profileBuf_ owned buffer, constructor seeding extension, whitespace stripping, truncation, DBG:profile provenance

## Description

Add `Protocol::setProfile(const char* name)`, extending the same
constructor and identity-block conventions ticket 001 introduced for
`role`/`commonName`. Depends on ticket 001 because both edit the same
`protocol.cpp` identity block and the same `Protocol::Protocol()`
constructor body — land 001 first, then extend it here rather than
introducing a second constructor.

**Stakeholder decision, recorded on the sprint's `stakeholder_approval`
gate 2026-09-08: whitespace is STRIPPED AND ACCEPTED, not rejected —
and this covers `setProfile()` too.** The source issue
(`kprofile-needs-a-runtime-setter.md`) does not ask for ANY whitespace
handling on `setProfile()` at all. `sprint.md`'s Architecture section
(Design Rationale #3) makes a deliberate sprint-planning decision to add
it anyway: `profile` sits inside the `id` reply's own space-separated,
positionally-parsed line (`wire_handler.cpp:828`) — the identical shape
of hazard the sibling issue raises for the banner. That extension
stands; only the "reject" half changed. Implement the same
strip-then-accept rule here that ticket 001 implements for
`role`/`commonName`: `setProfile("the bot")` succeeds and stores
`thebot`. Do not skip whitespace handling because the issue text
doesn't mention it, and do not make it reject — strip, same as ticket
001.

### What to add to `protocol.h`'s private section

Near `roleBuf_`/`commonNameBuf_` (ticket 001):

```cpp
char profileBuf_[32];              // seeded from kProfile, overwritten by setProfile()
bool profileTruncated_ = false;    // set once at the setProfile() store
bool profileSetAtRuntime_ = false; // true once setProfile() has been called at all;
                                    // read by emitProfileDebug()'s `src=` field
```

`profileBuf_[32]` matches the issue's own recommendation, sized against
the `id` reply's existing 48-char budget for that field
(`wire_handler.cpp:812-826`) — 32 leaves headroom inside that 48-char
budget. Note `profileTruncated_` is a `bool`, not a bitmask like
`deviceRoleTruncated_` — there is only one field here.

Declare `void setProfile(const char* name);` near `setDeviceRole()`'s
declaration (ticket 001), doc comment explaining: no late-call guard,
unlike `setupWifi()` — `execId()`'s `snprintf` dereferences
`identity.profile` at reply time, so a call at any point, including
after the first `id` reply has already gone out, is picked up by the
next one. This is the one deliberate, tested divergence from
`setupWifi()`'s late-call refusal.

### Extend the constructor from ticket 001

```cpp
Protocol::Protocol() {
  snprintf(roleBuf_, sizeof(roleBuf_), "%s", kRole);
  snprintf(commonNameBuf_, sizeof(commonNameBuf_), "%s", kCommonName);
  snprintf(profileBuf_, sizeof(profileBuf_), "%s", kProfile);
}
```

Same race-free reasoning as ticket 001: `protocol()`'s lazy-singleton
accessor constructs (and now seeds `profileBuf_`) before the first
method call reaches the object from any caller, including a
`setProfile()` call made as literally the first statement of `on
start`.

### `Protocol::setProfile(const char* name)`

1. If `name == nullptr`, reject: `emitLine("DBG:profile rejected: null
   argument")`, return without touching `profileBuf_`/
   `profileTruncated_`/`profileSetAtRuntime_`. This is the ONLY
   rejection path left in this function. There is no `DBG:profile
   rejected: whitespace` message anymore; do not add one.
2. Strip whitespace from `name` (see Description above — this extends
   beyond the source issue's literal text, deliberately, and follows
   ticket 001's strip-not-reject rule): remove EVERY `isspace()` byte —
   leading, trailing, and internal — from `name`. A whitespace byte
   never causes the call to fail.
3. **Ordering: strip first, then measure, then clip.**
   `profileTruncated_ = stripped_name_len >= sizeof(profileBuf_);`
   computed from the STRIPPED length — NOT the raw argument's
   `strlen()` — BEFORE the copy, same pattern as ticket 001. A raw
   length that only exceeds `sizeof(profileBuf_)` because of whitespace
   about to be removed must NOT be flagged truncated. `snprintf` the
   stripped value into `profileBuf_`, clipped safely to fit. Set
   `profileSetAtRuntime_ = true`.
4. Emit `DBG:profile src=%s name=%s trunc=%u` via `emitLine()`, where
   `src` is `"runtime"` if `profileSetAtRuntime_` else `"baked"` (always
   `"runtime"` at this point in the function, since step 3 just set it —
   the `src=` branch matters for a FUTURE read of the flag, e.g. if a
   status/debug command later reports current provenance outside the
   setter call itself; for this ticket's scope, the DBG line emitted
   from inside `setProfile()` will always say `src=runtime`).
5. Add the free-function boundary entry point beside
   `protocolSetDeviceRole()`'s (ticket 001) / `protocolSetupWifi()`'s:
   `void protocolSetProfile(const char* name) { protocol().setProfile(name); }`.

### `Protocol::buildIdentity()`

Change (ticket 001 left this line as `identity.profile = kProfile;`):
```cpp
identity.profile = kProfile;
```
to:
```cpp
identity.profile = profileBuf_;
```

No change needed to `WireHandler::execId()` (`wire_handler.cpp:800-826`)
— it already reads `identity.profile` via `snprintf`; only the pointer
`buildIdentity()` assigns changes, not the consumer.

## Acceptance Criteria

- [x] `profileBuf_[32]`, `profileTruncated_`, `profileSetAtRuntime_`
      exist on `Protocol`, and `Protocol::Protocol()` (from ticket 001)
      is extended to seed `profileBuf_` from `kProfile`.
- [x] `Protocol::setProfile(name)` exists with: null rejection (the only
      rejection path), whitespace STRIPPING (every `isspace()` byte
      removed from `name` — leading, trailing, and internal; the call
      still succeeds — same rule as ticket 001's `setDeviceRole()`,
      applied here even though the source issue doesn't ask for it —
      see Description), truncation computed from the STRIPPED length
      before the clip (strip-then-measure-then-clip; a raw length that
      only overflows because of whitespace about to be removed must NOT
      be flagged truncated), and a `DBG:profile` emission on both the
      null-rejection and success paths.
- [x] `setProfile("the bot")` succeeds and stores `thebot` — no
      rejection, no unset field.
- [x] A `name` value whose RAW length (before stripping) is `>=
      sizeof(profileBuf_)`, but whose STRIPPED length is `<` that
      `sizeof`, is stored IN FULL, untruncated — the "whitespace-only
      overflow" case — and `profileTruncated_` is NOT set.
- [x] `buildIdentity()` points `identity.profile` at `profileBuf_`, not
      at `kProfile` directly.
- [x] With no program ever calling `setProfile()`, the emitted `id`
      reply is byte-for-byte identical to today's output — this is the
      regression bar. Verify by hand against
      `tests/host/test_wire_grammar.py`'s existing `id`-reply
      assertions (ticket 005 adds the dedicated pin test).
- [x] `setProfile()` called AFTER the first `id` reply has already gone
      out still succeeds and is reflected in the next `id` reply — no
      late-call guard exists on this path (the deliberate divergence
      from `setupWifi()`). This is a source-level design property
      pinned by ticket 005's test, not something this ticket needs its
      own test for.
- [x] `tests/tools/test_make_deploy_wifi.py` and any existing
      `make_deploy.py` profile-injection test still pass untouched —
      this ticket does not touch `make_deploy.py`'s `_inject_profile()`
      or the `kProfile` declaration's exact text (confirm
      `_inject_profile()`'s regex — `tools/make_deploy.py:621` —
      still matches exactly one `kProfile` declaration after this
      ticket's edits).

## Testing

- **Existing tests to run**: whatever `tests/host/` target(s) build
  `protocol.cpp` today (same discovery command as ticket 001);
  `tests/tools/test_make_deploy_wifi.py` and any `make_deploy.py`
  profile-injection test (`grep -rl _inject_profile tests/`).
- **New tests to write**: none in this ticket — the host-level
  precedence/truncation/whitespace/late-call-succeeds test is ticket
  005, once this ticket's C++ surface exists for it to pin against.
- **Verification command**: scope to the modules this ticket touches.
  The full suite runs once, inside `close_sprint`.
