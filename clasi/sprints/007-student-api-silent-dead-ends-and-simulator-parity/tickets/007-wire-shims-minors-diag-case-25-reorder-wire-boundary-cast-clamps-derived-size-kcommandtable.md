---
id: '007'
title: 'Wire/shims Minors: DIAG case-25 reorder, wire-boundary cast clamps, derived-size
  kCommandTable'
status: open
use-cases:
- SUC-006
depends-on: []
github-issue: ''
issue: runargcount-guard-and-shim-minors.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Wire/shims Minors: DIAG case-25 reorder, wire-boundary cast clamps, derived-size kCommandTable

## Description

This is the C++/wire half of the batched Minors issue (grouped with
ticket 006's TS-side half by file cluster and testing-evidence
profile — see that ticket's Description for the split rationale).
Three independent fixes, all in `shims.cpp`/`wire_handler.h`/`.cpp`:

1. **DIAG `case 25` spliced into the 23/24 block (BLK-13).**
   `shims.cpp`'s `diagValue()` switch has the comment "// 23/24:
   rejected implausible encoder reads" immediately followed by
   `case 25:` (wrong-way count), THEN `case 23`/`case 24` (glitch
   counts) — the comment and the cases it describes are separated by
   an unrelated case, a reader trap for anyone using this switch as
   the probe-index reference (which `main.ts`'s `probe()` JSDoc, and
   this sprint's ticket 001, both point students/hosts at). Purely
   cosmetic — the switch is functionally correct regardless of case
   order. **Fix**: move `case 25` to after `case 24`, so the comment
   immediately precedes the cases it describes.
2. **WIRE-08 — unclamped numeric casts at the wire boundary.** Two
   sites: `wire_adapter.cpp`'s `setWheelsTimed(static_cast<int>(left),
   ...)` call (in `onWheelsX`/similar) — `WHEELS_V 2147483647 0 1000 #1`
   decodes (the wire grammar accepts any int32), and
   `static_cast<float>(2147483647)` rounds up to `2147483648.0f`,
   whose cast back to `int` is UB: benign (saturates) on the Cortex-M
   target's VCVT, but yields `INT32_MIN` on the x86 host harness — a
   full-speed *reverse* command from a max-forward wire value, host
   and target disagreeing in sign for wire values in
   `[2147483584, 2147483647]`. And a `SET`-field `×1000`
   `std::lround(value * 1000.0f)` cast to `int` (locate the exact
   call site — approximately `wire_adapter.cpp`, the `onSet`/`execSet`
   path; line numbers have drifted since the review, re-locate before
   editing): `SET pid_kp 3000000 #2` produces `3e9`, exceeding a
   32-bit range, making the `lround` result UB/unspecified. Neither
   path range-checks between the wire's full-int32 grammar and the
   narrower internal domain. **Fix**: clamp both sites to sane
   physical ranges before the cast (e.g. clamp to
   `[INT32_MIN, INT32_MAX]` is not sufficient since the OVERFLOW
   happens inside the float round-trip itself — clamp the *float*
   value to a range that survives the `int` cast losslessly on both
   host and target, such as `[-2000000000.0f, 2000000000.0f]` for the
   mm/s case and an equivalent bound for the ×1000 config case),
   refusing with `kRange` beyond the clamp — consistent with the
   existing cruise/duration policing pattern already used elsewhere in
   this file.
3. **WIRE-09 — `kCommandTable`'s explicit `[18]` size zero-fills on
   under-initialization.** `wire_handler.h`'s
   `static const VerbEntry kCommandTable[18];` and
   `wire_handler.cpp`'s matching `[18]` definition spell the count
   twice. Adding a 19th verb without updating both fails loudly
   (too many initializers) — fine. *Removing* one (or missing one
   while renaming) compiles **silently**: the array zero-fills the
   vacated slot, `e.name == nullptr`, and the first inbound sequenced
   verb that reaches it walks into `strcmp(verb, nullptr)` — UB, a
   hard fault on the robot, for every subsequent command. **Fix**:
   declare `static const VerbEntry kCommandTable[];` (no explicit
   size) in the header, define it with a deduced size in the `.cpp`,
   and add a `static_assert` pinning the expected count (e.g.
   `static_assert(sizeof(kCommandTable) / sizeof(kCommandTable[0]) ==
   18, "kCommandTable verb count");`) so a future accidental removal
   fails to COMPILE instead of silently shipping. No verb is added,
   removed, or reordered by this fix.

## Acceptance Criteria

- [ ] `diagValue()`'s `case 25` appears after `case 24`, immediately
      following the "23/24" comment; no case's return value or
      behavior changes.
- [ ] Both WIRE-08 cast sites clamp before casting; a host test sends
      `WHEELS_V` (or the relevant verb) with a wire value near
      `INT32_MAX` and asserts the resolved sign/magnitude matches
      between the clamp logic's own math and what the target's VCVT
      saturation would produce (i.e., the host and target no longer
      disagree in sign for the extreme-value range) — this is
      host-testable today per the review's own "Coverage" note
      (extreme-value cases in `test_wire_motion_verbs.py` would expose
      the x86 sign flip directly).
- [ ] A host test sends a `SET` for a config field with a value whose
      ×1000 product exceeds a 32-bit range and asserts a `kRange`
      refusal (or a clamped, well-defined result) instead of an
      unspecified/garbage value landing in the kernel.
- [ ] `kCommandTable` is declared without an explicit array size in
      `wire_handler.h`, defined with a deduced size in
      `wire_handler.cpp`, and a `static_assert` pins the count. Confirm
      by temporarily removing one entry locally (not committed) and
      observing a **compile failure**, not a silent zero-fill — this
      is the actual defect this fix closes; do not skip verifying it
      fails closed.
- [ ] All 18 verb names are unchanged, in the same order, after this
      fix (diff review).
- [ ] Full existing host suite passes with no regressions to
      `diagValue()`, wire-boundary casts, or verb dispatch.

## C++11 Gate Coverage

- **Inside the gate**: `wire_handler.h`/`.cpp` (the `kCommandTable`
  resize) and `wire_adapter.cpp` (the two cast clamps) — both fully
  host-testable; `tests/host/` already compiles both files.
- **Outside the gate**: `shims.cpp`'s `diagValue()` reorder — cosmetic
  only, no host test asserts case *order*, only case *values*, which
  are unchanged; verify by code review that the reorder is
  copy-paste-exact (no accidental value change). No robot is required
  for any item in this ticket — items 2 and 3 are meaningfully
  host-testable (per the review's own coverage note for WIRE-08, and
  the compile-failure check for WIRE-09), and item 1 has no behavior
  to test at all.

## Testing

- **Existing tests to run**: `tests/host/test_wire_motion_verbs.py`,
  `tests/host/test_wire_grammar.py`.
- **New tests to write**: extreme-value WHEELS_V/SET cast tests per
  the Acceptance Criteria above; the temporary-removal compile-failure
  check for `kCommandTable` (verify manually, not committed as an
  automated test — there's no host-test pattern in this repo for
  "assert this doesn't compile").
- **Verification command**: `pytest tests/host/test_wire_motion_verbs.py -k "extreme or clamp"`
  plus a full `pytest tests/host/` run before marking this ticket done.
