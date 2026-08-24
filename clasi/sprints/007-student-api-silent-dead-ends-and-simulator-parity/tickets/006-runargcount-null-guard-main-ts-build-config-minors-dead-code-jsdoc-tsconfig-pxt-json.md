---
id: '006'
title: runArgCount null guard + main.ts/build-config Minors (dead code, JSDoc, tsconfig,
  pxt.json)
status: open
use-cases:
- SUC-006
depends-on: []
github-issue: ''
issue: runargcount-guard-and-shim-minors.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# runArgCount null guard + main.ts/build-config Minors (dead code, JSDoc, tsconfig, pxt.json)

## Description

This is the `main.ts`/TypeScript-side half of the batched Minors issue
(R-15 + grouped Minors); ticket 007 handles the C++/wire-side half
(DIAG splice, wire-boundary casts, verb-table sizing) — split by file
cluster and testing-evidence profile, not by importance. Six
independent, one-to-five-line fixes:

1. **`runArgCount()` null guard (R-15, BLK-02, the only non-trivial
   item here).** `main.ts`'s `runArgCount()` dereferences `runParts`
   unguarded (`return runParts.length - 1`), while its sibling
   `runArgText()` already guards (`if (!runParts || ...) return ""`).
   `runParts` is deliberately declared with no initializer (namespace
   initializers run after a test file's top-level code — an
   initializer here would both crash early registration AND wipe
   handlers already registered, per the file's own header comment) and
   is first assigned inside the RUN event handler. Any call to
   `runArgCount()` before the first RUN event — e.g. a test program
   logging it at top level, or a student calling it from a button
   handler at boot — dereferences an undefined array: the documented
   silent-boot-death class (panic 980, no serial output; measured on
   vevov 2026-08-21 for this exact declaration pattern). Narrowed by
   verification: any top-level `onRun`/`onRunCommand` registration
   disarms it via `ensureRunState()`, so exposure is limited to
   programs using `runArgCount` with no handler registered. **Fix**:
   mirror the sibling — `if (!runParts) return 0`.
2. **Dead `microphone` dependency in `pxt.json`.** Two independent
   code-review passes found zero references to `microphone` anywhere
   in `src/`/`test/` and disagreed on what that means (one: dead,
   delete or comment why it must stay; the other: assumed deliberate
   V2-gating, not a finding). **Fix**: document, don't delete — add
   the rationale-with-uncertainty paragraph already drafted in this
   sprint's `sprint.md`/`design/DESIGN.md` discussion into
   `docs/design/specification.md` §2 (direct edit; not part of the
   canonical design-doc-overlay set). Do not remove the dependency
   from `pxt.json` — deleting a shipped extension's declared
   dependency on the strength of a source grep, with no confirmed
   understanding of PXT's editor/variant-gating behavior, risks a
   silent breakage a source-only review cannot see, for a Low-priority
   hygiene item.
3. **`tsconfig.json` cannot type-check its own file set.** Its `files`
   list omits `pxt_modules/core/serial.ts`, yet `main.ts`'s `emitLine`
   sim body and `test/testrig.ts` call `serial.writeLine`, which lives
   there. **Fix**: add `"pxt_modules/core/serial.ts"` to `tsconfig.json`'s
   `files` array. While there, audit whether any other `pxt_modules/core/*`
   file `main.ts`/`test/*.ts` calls into is similarly missing (e.g.
   pins/LED helpers testFiles use) and add it too if found — but do
   not go looking for unrelated tsconfig improvements beyond what
   `main.ts`/testFiles actually reference.
4. **Dead `maxNudges` variable.** `main.ts`'s `maxNudges = 6` ("bounded
   arrival retries") is a leftover from before `goToWorld()` became
   deliberately one-pass (see its own header comment: "ONE PASS...
   No arrival nudging"). Never referenced. **Fix**: delete the
   variable declaration.
5. **`goToWorld()`'s JSDoc still promises repeat-until-arrival.** The
   exported JSDoc says "Repeats until inside the arrival tolerance,"
   contradicting the function's own body comment ("ONE PASS... no
   creeping up on it") and the camera-is-diagnostics doctrine (the
   overhead camera never drives a leg; the OTOS-based one-pass design
   is deliberate). **Fix**: rewrite the JSDoc to describe the actual
   one-pass behavior — drives one leg toward the target and stops; any
   remaining error is inherited by the next call/hop, not corrected in
   place.
6. **DIAG `case 25` spliced between the "23/24" comment and its
   cases** — this item is implemented in `shims.cpp`, but tracked here
   for issue-completeness bookkeeping since it's part of the same
   Minors batch; see ticket 007 for the actual fix (kept there since
   it shares a file cluster with the wire-boundary casts and verb-table
   sizing, not with this ticket's TS-side items).

## Acceptance Criteria

- [ ] `runArgCount()` has the `if (!runParts) return 0` guard,
      matching `runArgText()`'s existing pattern exactly.
- [ ] `docs/design/specification.md` §2 documents the `microphone`
      dependency's uncertain rationale; `pxt.json` itself is
      unchanged (dependency retained).
- [ ] `tsconfig.json`'s `files` array includes
      `pxt_modules/core/serial.ts`; a plain `tsc -p .` (or the
      project's equivalent type-check invocation) no longer fails on
      `main.ts` for a missing `serial` type — confirm by actually
      running the type-check, not just editing the file.
- [ ] `maxNudges` is deleted from `main.ts`; confirm no reference
      remains (it had none before this ticket either, so this is a
      pure deletion, not a behavior change).
- [ ] `goToWorld()`'s exported JSDoc describes one-pass behavior,
      consistent with its own body comment.
- [ ] Full existing host suite passes (none of these five items touch
      host-tested code, so this is a regression check, not new
      coverage).

## C++11 Gate Coverage

All five items in this ticket are `main.ts`/`tsconfig.json`/
`pxt.json` — entirely outside the C++11 host-test gate (no host test
reaches any of these files). Evidence available: a PXT build/type-check
succeeding (specifically confirms item 3, the `tsconfig.json` fix, and
that item 1's guard doesn't break compilation), code review for items
1, 4, and 5 (each a small, easily-verified-by-reading diff), and the
`specification.md` §2 edit for item 2 is a docs-only change with no
code to test. No robot is required for any item in this ticket.

## Testing

- **Existing tests to run**: full `pytest tests/host/` (regression
  check only — none of this ticket's items touch host-tested files).
- **New tests to write**: none — no host-testable surface is added or
  changed.
- **Verification command**: a PXT build/type-check
  (confirms items 1 and 3 compile correctly) plus
  `pytest tests/host/` (confirms no unrelated regression).
