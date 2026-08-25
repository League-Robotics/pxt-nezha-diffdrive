---
id: '002'
title: 'Extract run.ts: the RUN command dispatcher'
status: open
use-cases: [SUC-001, SUC-002]
depends-on: ['001']
github-issue: ''
issue: break-up-main-ts-into-modules.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Extract run.ts: the RUN command dispatcher

## Description

Second extraction. Moves the RUN command dispatcher — the second
"zero-coupling" piece the 2026-08-23 code review's DES-05 finding
named — out of `main.ts` into `src/run.ts`: the no-initialiser state
block (`runParts: string[]`, `runNames: string[]`,
`runHandlers: ((arg: number) => void)[]`,
`runAnyHandlers: ((name: string, arg: number) => void)[]`,
`runWired: boolean`), `ensureRunState()`, `RUN_EVENT_SOURCE`,
`wireRunDispatch()`, `onRun()`, `onRunCommand()`, `runArg()`,
`runArgText()`, `runArgCount()`. Also move the dual-purpose comment
block immediately above `defaultSpeed`/`defaultYawRate` in today's
`main.ts` (the one covering both "why `_startProtocol()` runs
unconditionally at load" and "why the run-state arrays have no
initialiser") — **split it**: the no-initialiser/panic-980 rationale
paragraph (the one starting "Declared with NO INITIALISER, created on
first use...") must land verbatim next to `runParts` et al. in
`run.ts`; the wire-protocol-loop-start rationale may stay a short
pointer in `main.ts` near the `_startProtocol()` call, cross-
referencing `run.ts` if useful. Re-locate this comment by content, not
by the line numbers in `sprint.md`/the overlay — sprint 009 lands
before this ticket executes and will have shifted them.

This module is **fully self-contained**: nothing outside `run.ts`
reads or writes `runParts`/`runNames`/`runHandlers`/`runAnyHandlers`/
`runWired`, and nothing inside `run.ts` reaches into another module's
state. Lower risk than ticket 001 in that sense (no new cross-file
reference is introduced by this extraction), but the single highest-
consequence detail in the whole sprint to get right: the no-
initialiser pattern exists specifically because an initialiser here
caused a documented silent boot death (panic 980, no serial output,
measured on vevov 2026-08-21) — preserve it exactly, do not "clean it
up" by adding `= []` defaults.

## Acceptance Criteria

- [ ] `src/run.ts` created containing every item listed in the
      Description, each with JSDoc/`//%` annotations preserved
      verbatim, in their original relative order.
- [ ] `runParts`/`runNames`/`runHandlers`/`runAnyHandlers`/`runWired`
      keep **zero** initialisers — grep-verified (`let runParts:
      string[]`, no `= []` or similar, for all five).
      `ensureRunState()`'s guard logic (`if (!runX) runX = []`)
      unchanged.
- [ ] The dual-purpose comment block is split per the Description, not
      duplicated wholesale or dropped.
- [ ] `main.ts` no longer contains any of the moved code.
- [ ] `pxt.json`'s `files` array: `src/run.ts` inserted (position
      relative to `sim.ts`/`main.ts` is free — no load-time ordering
      constraint applies to this module; keep it adjacent to `sim.ts`
      for readability).
- [ ] `tsconfig.json`'s `files` array: same insertion.
- [ ] A real PXT build succeeds.
- [ ] `test/test.ts` and `test/testrig.ts` run in the PXT simulator
      with identical behavior to ticket 001's post-extraction baseline
      — in particular, confirm no RUN-related boot-time error appears
      (the panic-980 smoke check this pattern exists to prevent).
- [ ] Full existing `tests/host/` suite passes unchanged.
- [ ] `test_pxt_manifest_completeness.py` passes.
- [ ] No acceptance criterion above requires a robot.

## Implementation Plan

**Approach**: cut the listed state/functions and the relevant half of
the dual-purpose comment out of `main.ts`, paste into `src/run.ts`
inside the same `namespace diffDrive {}` wrapper. No behavior change,
no reordering beyond keeping the moved block contiguous.

**Files to create**: `src/run.ts`.

**Files to modify**: `src/main.ts`, `pxt.json`, `tsconfig.json`.

**Testing plan**: real build, then simulator/testrig parity against
ticket 001's baseline, then `tests/host/` regression, then manifest
completeness.

**Documentation updates**: none beyond what the overlay already
states; note in this ticket's completion notes if the comment-split
turned out differently than planned (e.g. if the shared comment did
not cleanly separate along the described line).

## C++11 Gate Coverage

Not applicable — TypeScript/manifest-only ticket, no C++ source
touched. Evidence: real PXT build, `test_pxt_manifest_completeness.py`,
`tsc -p .` manual check, simulator/testrig parity. No robot required.

## Testing

- **Existing tests to run**: full `pytest tests/host/`; `tsc -p .`.
- **New tests to write**: none.
- **Verification command**: real PXT build; `test/test.ts`/
  `test/testrig.ts` in the PXT simulator; `uv run pytest tests/host/`.
