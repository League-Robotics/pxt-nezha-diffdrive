---
id: '004'
title: TS/shim arity and toolbox-visibility pin test for setupWifi()
status: done
use-cases:
- SUC-001
depends-on:
- '002'
github-issue: ''
issue: wifi-credentials-are-set-in-code-from-the-project-s-own-secrets-ts.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# TS/shim arity and toolbox-visibility pin test for setupWifi()

## Description

Two regression surfaces for ticket 002's TS/shim work, both pinned by
existing precedent in this repo:

1. **Toolbox visibility.** `setupWifi()` is `//% blockHidden=true` and
   must never join the visible toolbox count/order —
   `tests/host/test_block_toolbox_order.py` already pins the visible
   block count and per-group order (see its own history comment for
   how `enableRadioLink`/`enableWifiLink` were kept out as hidden
   blocks). Run it after ticket 002 lands and confirm it still passes
   with NO changes needed — if it needs a baseline update, that itself
   is a signal `setupWifi()` leaked into the visible toolbox and
   ticket 002's `blockHidden=true` placement should be checked before
   touching the baseline.
2. **`run.ts` ↔ `sim.ts` shim arity/adjacency.** This repo has been
   bitten before by a `run.ts` export and its `sim.ts` `shim=`-
   annotated counterpart drifting apart in argument count or order —
   this is called out explicitly as a known trap (see
   `docs/design/DESIGN.md` or sibling notes on shim arity if present,
   and the general pattern other `_foo`/`foo` pairs in this repo
   follow: `setupRadio`/`_setupRadio`, `enableRadioLink`/
   `_enableRadioLink`, `enableWifiLink`/`_enableWifiLink`). There is no
   existing dedicated automated pin for this pairing (checked:
   `grep -rl arity tests/host/*.py` finds wire-protocol arity tests,
   not TS/shim arity). Add one.

### What to write

A new host-level test, e.g.
`tests/host/test_setupwifi_shim_arity_source_pin.py`, that:

- Reads `src/blocks/run.ts` and extracts `setupWifi`'s exported
  signature (parameter names, types, and the `password: string = ""`
  default) via a regex anchored on `export function setupWifi(`.
- Reads `src/blocks/sim.ts` and extracts `_setupWifi`'s `shim=`-
  annotated signature the same way, anchored on
  `//% shim=diffDrive::setupWifi` followed by
  `export function _setupWifi(`.
- Asserts both have exactly 2 parameters, both `string`-typed, in the
  same order (ssid, password) — this is the actual arity/adjacency
  check; it does not need to re-verify the default value, since PXT
  shims don't carry defaults across the `shim=` boundary the way the
  wrapping `run.ts` export does (confirm this against how
  `setupRadio`'s `channel`/`group: number = 10` default is NOT
  repeated in `_setupRadio`'s signature, `sim.ts:543`, as the existing
  precedent for "the default lives on the `run.ts` wrapper only").
- Asserts `run.ts`'s `setupWifi` body calls `_setupWifi(ssid,
  password)` (or `_setupWifi(ssid, password ?? "")`/equivalent) with
  arguments in the same order as declared — a reordering here would
  compile fine (both are `string`) and silently swap SSID and
  password at runtime, which is exactly the class of bug an arity
  check alone would miss.

Keep it a source-pin/regex test (no TS compiler invoked), matching how
every other TS-surface check in `tests/host/` already works — do not
introduce a new TS-parsing dependency for one test.

## Acceptance Criteria

- [x] `tests/host/test_block_toolbox_order.py` passes unmodified after
      ticket 002 lands (or, if it genuinely needs a baseline change,
      that change is justified in the ticket's own notes as
      intentional, not just "test failed so I updated the baseline").
      Confirmed: 3 passed, no baseline edit needed -- `setupWifi` has
      no `block=` caption, so that file's existing scan already
      excludes it (same as `enableRadioLink`/`runArg`).
- [x] New arity/adjacency pin test exists, asserts parameter count,
      type, and order match between `run.ts`'s `setupWifi` and
      `sim.ts`'s `_setupWifi`, and asserts the call site passes
      arguments in the declared order.
      `tests/host/test_setupwifi_shim_arity_source_pin.py`; also
      extended to the third layer (`src/shims.cpp`'s native
      `setupWifi`), plus pins for the `//%` adjacency rule, `//%
      blockHidden=true`, the `getUTF8Size()` emptiness guard, and
      `sim.ts`'s `_setupWifi` recording its arguments -- the fuller
      set the dispatch brief asked this ticket to catch.
- [x] The new test fails if `_setupWifi`'s parameters are reordered to
      `(password, ssid)` while `setupWifi`'s call site is not updated
      to match (the actual bug class this ticket exists to catch).
      Verified by temporarily breaking each of the 6 source shapes
      this file pins (param reorder, call-site swap, `//%` adjacency,
      missing `blockHidden`, reverted `toCharArray()` emptiness guard,
      bare no-op `_setupWifi`), confirming each fails the matching
      test, then `git checkout --` and a clean `git status` on `src/`.

## Testing

- **Existing tests to run**: `tests/host/test_block_toolbox_order.py`.
- **New tests to write**:
  `tests/host/test_setupwifi_shim_arity_source_pin.py` as described
  above.
- **Verification command**: `uv run pytest
  tests/host/test_block_toolbox_order.py
  tests/host/test_setupwifi_shim_arity_source_pin.py`. The full suite
  runs once, inside `close_sprint`.
