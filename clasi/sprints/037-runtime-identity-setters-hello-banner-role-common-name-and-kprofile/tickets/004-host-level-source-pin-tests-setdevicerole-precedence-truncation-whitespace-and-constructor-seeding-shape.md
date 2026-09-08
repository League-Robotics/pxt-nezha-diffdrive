---
id: '004'
title: 'Host-level source-pin tests: setDeviceRole() precedence, truncation, whitespace,
  and constructor-seeding shape'
status: open
use-cases:
- SUC-001
- SUC-003
depends-on:
- '001'
github-issue: ''
issue: high/hello-banner-role-and-common-name-are-hardcoded.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Host-level source-pin tests: setDeviceRole() precedence, truncation, whitespace, and constructor-seeding shape

## Description

**Read this before reaching for `compile_shared_lib` or any pattern
from `tests/host/test_wifi_link.py`.** That pattern does NOT apply
here: `tests/host/` cannot compile `protocol.cpp` at all, because it
includes `pxt.h`, directly and transitively (confirmed by
`tests/host/test_protocol_stack_canary_source_pin.py` and
`tests/host/test_dispatched_job_motion_source_pin.py`, both of which
say so explicitly and use SOURCE-TEXT PINNING instead of compiling —
sprint 036 ticket 003 hit and documented this exact same wall for
`setupWifi()`). Follow that established alternative here too: a
**source-pin test**, in the shape of
`tests/host/test_dispatched_job_motion_source_pin.py` (read it first)
and, more directly, whatever sprint 036 ticket 003 produced at
`tests/host/test_setupwifi_precedence_source_pin.py` (read that one
too — it is the closer precedent, same problem, same solution, for the
sibling setter).

Copy its `_strip_comments()` helper (or import it if the codebase has
since consolidated a shared one — check for `test_bus_guard_source_pin.py`
or similar before duplicating again).

### What to pin

Read the actual `Protocol::setDeviceRole()`, `Protocol::Protocol()`
(the new constructor), and `Protocol::buildIdentity()` bodies ticket
001 lands, then write regex/text assertions that the following SHAPES
are present in `protocol.{h,cpp}`:

1. **Null guard exists, structurally before any write.** A conditional
   on `role == nullptr` (or equivalent, covering `commonName` too)
   appears in `setDeviceRole()`'s body before any write to
   `roleBuf_`/`commonNameBuf_`/`deviceRoleTruncated_`.
2. **Whitespace is STRIPPED, not rejected.** Stakeholder decision,
   `stakeholder_approval` gate 2026-09-08: whitespace in `role`/
   `commonName` is removed (leading, trailing, and internal) and the
   call still succeeds — it is never a rejection path. Confirm, by
   reading the actual source, that: (a) an `isspace()` (or equivalent)
   removal pass exists over both `role` and `commonName`, and (b) there
   is NO `DBG:role rejected: whitespace` message anywhere in the file —
   its presence means the reject behavior was (re)implemented instead
   of strip, and the test should FAIL. The only rejection message that
   should exist is `DBG:role rejected: null argument`.
3. **Truncation is computed from the STRIPPED length, before the
   copy, from both fields — strip-then-measure-then-clip.** Both
   `roleBuf_` and `commonNameBuf_` have a length check against their
   `sizeof` prior to the `snprintf`/copy that fills them, and
   `deviceRoleTruncated_` is assigned from that check. Confirm this
   check reads the length AFTER stripping, not the raw argument's
   `strlen()` directly — e.g. by confirming (via source order or a
   named intermediate variable/counter) that the stripping logic
   appears before, and feeds, the length comparison used to set
   `deviceRoleTruncated_`, rather than `strlen(role)`/
   `strlen(commonName)` being compared directly against `sizeof(...)`.
4. **`buildIdentity()` points at the buffers, not the constants.**
   `identity.role = roleBuf_` and `identity.commonName =
   commonNameBuf_` appear in `buildIdentity()`'s body — NOT
   `identity.role = kRole` or similar direct-literal assignment (this
   is the specific regression this test exists to catch: someone
   "simplifying" `buildIdentity()` back to reading the constants
   directly would silently break every runtime setter while leaving
   the DEFAULT-output tests passing, since the default value is the
   same either way).
5. **The constructor seeds from the named constants, not inline
   literals.** `Protocol::Protocol()`'s body contains `snprintf(roleBuf_,
   ..., kRole)` and `snprintf(commonNameBuf_, ..., kCommonName)` (not,
   e.g., `snprintf(roleBuf_, ..., "NEZHA2")` — a hardcoded literal here
   would silently diverge from `kRole` the moment anyone edits one but
   not the other).
6. **The stale "NSDMI, not a hand-written constructor" comment was
   actually corrected**, not left standing beside a constructor that
   now contradicts it — grep for the OLD phrase near `wireAdapter_`'s
   declaration and assert it is gone or has been amended to mention the
   new exception.

### Default-byte-identity check

Since `tests/host/` cannot compile `protocol.cpp`, this cannot be a
"build it and diff the output" test. Instead, pin the STRUCTURAL
guarantee: `kRole = "NEZHA2"` and `kCommonName = "robot"` are unchanged
literal values (regex-extract and assert exact string), and
`sendBanner()`'s format string is exactly `"device %s %s %s %s\n"` with
exactly four `%s` placeholders reading, in order,
`identity.role, identity.commonName, identity.name, identity.serial` —
this is the closest a source-pin test can get to "the default banner is
byte-identical," short of an actual on-hardware or compiled check
(ticket 007 covers the former; this repo has no path to the latter for
`protocol.cpp`).

## Acceptance Criteria

- [ ] New file
      `tests/host/test_setdevicerole_precedence_source_pin.py` (or
      similar name, consistent with sprint 036's naming) exists,
      following `test_setupwifi_precedence_source_pin.py`'s structure.
- [ ] The test fails if whitespace stripping is removed (a whitespace
      byte in `role`/`commonName` would be stored verbatim instead of
      being stripped), and fails if a `DBG:role rejected: whitespace`
      message reappears anywhere in the file (verify each by
      temporarily breaking it locally, confirming the new test catches
      it, then restoring — do not leave the break in the tree).
- [ ] The test includes an explicit "whitespace-only overflow" case: an
      input whose RAW length is `>= sizeof(roleBuf_)` (or
      `sizeof(commonNameBuf_)`) only because of whitespace bytes that
      will be stripped, and whose STRIPPED length is `<` that `sizeof`.
      Assert the test's expectation is that `deviceRoleTruncated_`'s
      corresponding bit is NOT set for that case — i.e. the pin
      confirms the source measures the length AFTER stripping, not
      before.
- [ ] The test fails if `buildIdentity()` is reverted to
      `identity.role = kRole` / `identity.commonName = kCommonName`
      directly.
- [ ] The test fails if the constructor's seed lines are replaced with
      hardcoded literals instead of `kRole`/`kCommonName`.
- [ ] The test fails if the stale "NSDMI, not a hand-written
      constructor" comment reappears unamended.
- [ ] `sendBanner()`'s format-string pin fails if a literal
      (`"NEZHA2"`/`"robot"`) reappears in it.

## Testing

- **Existing tests to run**:
  `tests/host/test_dispatched_job_motion_source_pin.py`,
  `tests/host/test_setupwifi_precedence_source_pin.py` (confirm the
  pattern still works and nothing here collides with either).
- **New tests to write**: the source-pin file described above.
- **Verification command**: `uv run pytest
  tests/host/test_setdevicerole_precedence_source_pin.py
  tests/host/test_dispatched_job_motion_source_pin.py
  tests/host/test_setupwifi_precedence_source_pin.py`. The full suite
  runs once, inside `close_sprint`.
