---
id: '005'
title: 'Host-level source-pin tests: setProfile() precedence, truncation, whitespace,
  and late-call-succeeds behavior'
status: done
use-cases:
- SUC-002
- SUC-003
depends-on:
- '002'
github-issue: ''
issue: high/kprofile-needs-a-runtime-setter.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Host-level source-pin tests: setProfile() precedence, truncation, whitespace, and late-call-succeeds behavior

## Description

Same source-pin approach as ticket 004 (`tests/host/` cannot compile
`protocol.cpp` — see that ticket's Description for the full explanation
and precedents; do not re-litigate that decision here, just follow it).
This ticket pins `Protocol::setProfile()` and the constructor extension
from ticket 002.

### What to pin

1. **Null guard exists, structurally before any write.** This remains
   the ONLY rejection path — confirm there is NO `DBG:profile rejected:
   whitespace` message anywhere in the file (its presence means reject
   was (re)implemented instead of strip, and this test should FAIL).
2. **Whitespace is STRIPPED, not rejected.** This is the interesting
   one to get right in the test: the source issue for `setProfile()`
   never asked for ANY whitespace rule, but `sprint.md`'s Architecture
   (Design Rationale #3) and ticket 002 both require strip-and-accept
   anyway (stakeholder decision, `stakeholder_approval` gate
   2026-09-08). Pin that stripping actually landed — don't skip this
   check just because the issue text doesn't mention it; that is
   exactly the kind of quietly-dropped requirement a source-pin test is
   for. `setProfile("the bot")` must succeed and store `thebot`, never
   fail.
3. **Truncation computed from the STRIPPED length, before the copy —
   strip-then-measure-then-clip.** `name`'s STRIPPED length (not its raw
   `strlen()`) is compared against `sizeof(profileBuf_)`, assigned to
   `profileTruncated_` before the `snprintf`. Confirm this by source
   order (the stripping logic feeds the length comparison, rather than
   `strlen(name)` being compared directly against `sizeof(profileBuf_)`).
4. **`buildIdentity()` points at `profileBuf_`, not `kProfile`
   directly.** `identity.profile = profileBuf_` — NOT `identity.profile
   = kProfile`. This is the single highest-value assertion in this
   ticket: it is the exact regression that would silently break
   `setProfile()` while every default-output test kept passing (baked
   default is identical either way).
5. **No late-call guard exists on this path.** Confirm by ABSENCE:
   `setProfile()`'s body must NOT contain a conditional gating the
   store on something equivalent to `wifiBegun_`/an "already replied"
   flag. Grep for the actual guard pattern `setupWifi()` uses
   (`if (wifiBegun_)` or whatever the equivalent boundary flag is
   named) and assert `setProfile()`'s body does not contain an
   analogous check. This is the ticket's most important negative
   assertion — the whole point of `setProfile()` diverging from
   `setupWifi()` is the ABSENCE of this guard, and a future
   "consistency" refactor that copies the guard over from
   `setupWifi()` without reading the design rationale would silently
   break SUC-002's late-call-succeeds requirement. Pin the absence
   explicitly so that refactor fails loudly instead.
6. **The constructor seeds `profileBuf_` from `kProfile`, not a
   hardcoded literal.** Same reasoning as ticket 004's constructor
   check.
7. **`make_deploy.py`'s `_inject_profile()` regex still matches exactly
   one `kProfile` declaration** after ticket 002's edits — read
   `tools/make_deploy.py:621`'s regex and confirm `protocol.cpp` still
   has exactly one line of the shape `constexpr const char* kProfile =
   "...";`. This is a cross-file consistency check worth having here
   since ticket 002 edits the same identity block that regex targets.

### `DBG:profile` line format

Pin that `emitLine()` is called with a format string containing
`src=`, `name=`, and `trunc=` tokens (the exact `snprintf` format
string, if one is used, should contain all three) — matching the
issue's own recommended shape (`src=baked|runtime name=vevov trunc=0`).

## Acceptance Criteria

- [x] New file `tests/host/test_setprofile_precedence_source_pin.py`
      (or similar name) exists, following ticket 004's structure and
      `test_setupwifi_precedence_source_pin.py`'s precedent.
- [x] The test fails if whitespace stripping is removed from
      `setProfile()` (a whitespace byte would be stored verbatim
      instead of being stripped), and fails if a `DBG:profile rejected:
      whitespace` message reappears anywhere in the file.
- [x] The test includes an explicit "whitespace-only overflow" case: a
      `name` whose RAW length is `>= sizeof(profileBuf_)` only because
      of whitespace bytes that will be stripped, and whose STRIPPED
      length is `<` that `sizeof`. Assert the test's expectation is that
      `profileTruncated_` is NOT set for that case.
- [x] The test fails if `buildIdentity()` is reverted to
      `identity.profile = kProfile` directly.
- [x] The test fails if a late-call guard (any conditional resembling
      `setupWifi()`'s `wifiBegun_` check) is added to `setProfile()`'s
      body — this is a NEGATIVE assertion; verify it actually fails by
      temporarily adding a fake guard locally, confirming the test
      catches it, then removing the fake guard.
- [x] The test fails if the constructor's `profileBuf_` seed line is
      replaced with a hardcoded literal instead of `kProfile`.
- [x] `make_deploy.py::_inject_profile()`'s regex is confirmed (by this
      test or a companion assertion) to still match exactly one
      `kProfile` declaration in `protocol.cpp`.

## Testing

- **Existing tests to run**:
  `tests/host/test_setdevicerole_precedence_source_pin.py` (ticket
  004), `tests/host/test_setupwifi_precedence_source_pin.py`,
  `tests/tools/test_make_deploy_wifi.py` and any `make_deploy.py`
  profile-injection test.
- **New tests to write**: the source-pin file described above.
- **Verification command**: `uv run pytest
  tests/host/test_setprofile_precedence_source_pin.py
  tests/host/test_setdevicerole_precedence_source_pin.py
  tests/tools/test_make_deploy_wifi.py`. The full suite runs once,
  inside `close_sprint`.
