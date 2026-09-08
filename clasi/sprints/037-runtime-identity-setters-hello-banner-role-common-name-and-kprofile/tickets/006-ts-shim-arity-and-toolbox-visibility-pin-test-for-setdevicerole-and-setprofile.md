---
id: '006'
title: TS/shim arity and toolbox-visibility pin test for setDeviceRole() and setProfile()
status: open
use-cases:
- SUC-001
- SUC-002
depends-on:
- '003'
github-issue: ''
issue:
- high/hello-banner-role-and-common-name-are-hardcoded.md
- high/kprofile-needs-a-runtime-setter.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# TS/shim arity and toolbox-visibility pin test for setDeviceRole() and setProfile()

## Description

Two regression surfaces for ticket 003's TS/shim work, mirroring sprint
036 ticket 004 exactly (read it first — same problem, same solution,
for two setters instead of one):

1. **Toolbox visibility.** `setDeviceRole()` and `setProfile()` are
   both `//% blockHidden=true` and must never join the visible toolbox
   count/order — `tests/host/test_block_toolbox_order.py` already pins
   the visible block count and per-group order. Run it after ticket 003
   lands and confirm it still passes with NO baseline changes needed —
   if it needs one, that itself is a signal one of the two new blocks
   leaked into the visible toolbox, and ticket 003's `blockHidden=true`
   placement should be checked before touching the baseline.
2. **`run.ts` ↔ `sim.ts` shim arity/adjacency**, for BOTH new pairs.
   This repo has been bitten before by a `run.ts` export and its
   `sim.ts` `shim=`-annotated counterpart drifting apart in argument
   count or order (sprint 036 ticket 004's own motivation). Extend
   (or write a sibling to) that same test for `setDeviceRole`/
   `_setDeviceRole` and `setProfile`/`_setProfile`.

### What to write

Extend `tests/host/test_setupwifi_shim_arity_source_pin.py` (if its
structure generalizes cleanly to a second/third pair) or add a sibling
file, e.g. `tests/host/test_identity_setters_shim_arity_source_pin.py`,
that:

- Reads `src/blocks/run.ts` and extracts `setDeviceRole`'s and
  `setProfile`'s exported signatures (parameter names, types — no
  defaults expected on either, unlike `setupWifi`'s `password = ""`)
  via a regex anchored on `export function setDeviceRole(` /
  `export function setProfile(`.
- Reads `src/blocks/sim.ts` and extracts `_setDeviceRole`'s and
  `_setProfile`'s `shim=`-annotated signatures the same way.
- Asserts `setDeviceRole`/`_setDeviceRole` both have exactly 2
  `string`-typed parameters, in the same order (`role`, `commonName`).
- Asserts `setProfile`/`_setProfile` both have exactly 1 `string`-typed
  parameter (`name`).
- Asserts `run.ts`'s `setDeviceRole` body calls `_setDeviceRole(role,
  commonName)` with arguments in the same declared order (a reordering
  here would compile fine, since both are `string`, and silently swap
  role and commonName at runtime — the same bug class sprint 036 ticket
  004 exists to catch, applied to this setter).
- Asserts `run.ts`'s `setProfile` body calls `_setProfile(name)`.
- Also pins, for both setters in `shims.cpp`: the `//%` immediately-
  above-declaration rule, `//% blockHidden=true` on both `run.ts`
  exports, and the `getUTF8Size()` emptiness guard (not
  `toCharArray()`'s result at size 0) — the fuller set sprint 036
  ticket 004's own dispatch asked its test to catch, extended to two
  more setters here.

Keep it a source-pin/regex test — no TS compiler invoked, matching
every other TS-surface check in `tests/host/`.

## Acceptance Criteria

- [ ] `tests/host/test_block_toolbox_order.py` passes unmodified after
      ticket 003 lands (or, if it genuinely needs a baseline change,
      that change is justified in this ticket's own notes as
      intentional, not just "test failed so I updated the baseline").
- [ ] New arity/adjacency pin test(s) exist for BOTH `setDeviceRole`/
      `_setDeviceRole` and `setProfile`/`_setProfile`, asserting
      parameter count, type, and order match, and that each call site
      passes arguments in the declared order.
- [ ] The new test fails if `_setDeviceRole`'s parameters are reordered
      to `(commonName, role)` while `setDeviceRole`'s call site is not
      updated to match (verify by temporarily breaking it, confirming
      the test catches it, then restoring).
- [ ] The new test fails if either shim's `//%` annotation gains an
      intervening comment line, loses `blockHidden=true`, or reverts
      the `getUTF8Size()` emptiness guard to a bare `toCharArray()`
      check (verify each by temporarily breaking it, confirming the
      test catches it, then restoring — `git status` clean on `src/`
      afterward).

## Testing

- **Existing tests to run**: `tests/host/test_block_toolbox_order.py`,
  `tests/host/test_setupwifi_shim_arity_source_pin.py`.
- **New tests to write**: as described above.
- **Verification command**: `uv run pytest
  tests/host/test_block_toolbox_order.py
  tests/host/test_setupwifi_shim_arity_source_pin.py
  tests/host/test_identity_setters_shim_arity_source_pin.py`. The full
  suite runs once, inside `close_sprint`.
