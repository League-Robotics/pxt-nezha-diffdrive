---
id: '002'
title: startWorldTracking() stops re-typing the OTOS product id
status: done
use-cases: []
depends-on: []
github-issue: ''
issue: wire-and-shim-minor-defects.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# startWorldTracking() stops re-typing the OTOS product id

## Description

`src/platform/otos_port.h:102` defines the single source of truth:

```cpp
static constexpr uint8_t kExpectedProductId = 0x5F;
```

`src/platform/otos_port.cpp:77` gates `initialized_` on it correctly. Two
other places independently restate the same literal instead of deferring to
it:

1. `src/blocks/world.ts:20-22` -- the block-facing entry point:
   ```ts
   export function startWorldTracking(): boolean {
       return otosBegin() == 0x5F
   }
   ```
2. `src/shims.cpp:1081` -- a comment on `otosBegin()`:
   ```cpp
   int otosBegin() {  // -> product id probed (0x5F == present)
   ```

If the expected id ever changes (a chip revision, a second supported sensor),
`otos_port.h` gets updated and `initialized_`/`connected()`/
`worldTrackingReady()` all go true correctly -- but `startWorldTracking()`
still compares against the stale `0x5F` it re-typed, returns **false**, and
every student program gated on it refuses to run against a perfectly healthy
sensor. That is a direct behavioral disagreement between `startWorldTracking()`
and its own sibling readback (`worldTrackingReady()`), not merely a stale
comment.

**Fix** (per the issue and the sprint's success criteria -- `0x5F` appears
once, in `otos_port.h`): `startWorldTracking()` should call `otosBegin()` for
its side effect (probing/initializing the sensor) and then return
`worldTrackingReady()`, exactly as the issue prescribes:

```ts
export function startWorldTracking(): boolean {
    otosBegin()
    return worldTrackingReady()
}
```

The caller (`world.ts`) has no business knowing the product id -- `otosBegin()`'s
integer return is a diagnostic value (already exposed separately via `probe()`/
`diagValue()` for instrumentation), not a contract `startWorldTracking()` should
re-derive readiness from.

Also reword the `shims.cpp:1081` comment so it no longer restates the literal
-- e.g. `// -> product id probed; readiness is OtosPort::initialized_ (see
otos_port.h's kExpectedProductId), not this return value` or similar. The
comment's informational value (telling a human reading `probe()` output what
the number means) can be kept without re-typing the literal that gates
correctness -- point to `otos_port.h` instead of restating `0x5F`.

`src/core/diffdrive.{h,cpp}` is vendored and byte-stable -- not touched by
this ticket.

## What to change

1. `src/blocks/world.ts` -- rewrite `startWorldTracking()` to call
   `otosBegin()` then return `worldTrackingReady()`, removing the `== 0x5F`
   comparison entirely.
2. `src/shims.cpp:1081` -- reword the `otosBegin()` comment to stop restating
   the `0x5F` literal; point to `otos_port.h`'s `kExpectedProductId` instead.
3. Confirm (grep) no other site in `src/` or `blocks/` independently states
   `0x5F` or `95` (decimal) in an OTOS-readiness context after this change --
   `otos_port.h` should be the only remaining literal.

## Acceptance Criteria

- [x] `0x5F` appears exactly once in the codebase's OTOS-readiness logic: in
      `src/platform/otos_port.h`'s `kExpectedProductId`.
- [x] `startWorldTracking()` calls `otosBegin()` then returns
      `worldTrackingReady()` -- no product-id comparison in `world.ts`.
- [x] `shims.cpp:1081`'s comment no longer restates the `0x5F` literal.
- [x] A test demonstrates the fixed behavior: with the expected product id
      changed (simulated via whatever seam the existing OTOS host-test
      fakes/mocks expose -- see `tests/host/` for the existing OTOS port
      test doubles), `startWorldTracking()` and `worldTrackingReady()` agree
      with each other, where before the fix they would disagree (this is the
      "fails against today's code" test -- construct the mismatched-id case
      the current code gets wrong, and show it now resolves correctly).
      **Note**: no OTOS host-test double actually exists in this repo
      (`otos_port.cpp` calls `uBit.i2c` directly with no host-testable
      seam, and grepping `tests/host/` for `otos` today turns up nothing
      -- verified before writing tests). Used the same text-based
      drift-test approach `test_wire_constants_drift.py` already
      established for TS/CODAL-bound files outside the host-compile
      reach instead: `tests/host/test_otos_product_id_single_source.py`
      asserts `0x5F` appears exactly once across `src/` and that
      `startWorldTracking()`'s body delegates to `worldTrackingReady()`
      with no product-id comparison of its own. Verified by temporarily
      reverting `world.ts`/`shims.cpp` to their pre-fix (HEAD) content
      and confirming both new tests fail, then restoring the fix and
      confirming they pass.
- [x] No change to `src/core/diffdrive.{h,cpp}` (vendored, byte-stable).

## Testing

- **Existing tests to run**: `uv run pytest tests/host/` -- especially
  whichever test file(s) already exercise `OtosPort`/`otosBegin`/
  `worldTrackingReady` semantics (grep `tests/host/` for `otos` to locate
  them; this repo's convention is host-portable C++ shims plus pytest
  wrappers, so look for an existing OTOS test double/shim alongside a
  `test_*.py`).
- **New tests to write**: a test that forces the "product id mismatch"
  condition (e.g. by driving the existing OTOS test double/shim to report an
  id other than `kExpectedProductId`) and asserts `startWorldTracking()`'s
  result now tracks `worldTrackingReady()` in both the matching and
  mismatching cases, rather than independently re-deriving readiness from a
  hardcoded comparison. This is meaningful specifically because the current
  `world.ts` code, unchanged, would return `false` on a healthy-but-relabeled
  sensor even though `worldTrackingReady()` reports `true` -- the test should
  make that specific disagreement visible before the fix and show it is gone
  after.
- **Verification command**: `uv run pytest tests/host/`
