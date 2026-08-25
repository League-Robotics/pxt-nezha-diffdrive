---
id: '002'
title: 'Extract run.ts: the RUN command dispatcher'
status: done
use-cases:
- SUC-001
- SUC-002
depends-on:
- '001'
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

- [x] `src/run.ts` created containing every item listed in the
      Description, each with JSDoc/`//%` annotations preserved
      verbatim, in their original relative order.
- [x] `runParts`/`runNames`/`runHandlers`/`runAnyHandlers`/`runWired`
      keep **zero** initialisers — grep-verified (`let runParts:
      string[]`, no `= []` or similar, for all five).
      `ensureRunState()`'s guard logic (`if (!runX) runX = []`)
      unchanged.
- [x] The dual-purpose comment block is split per the Description, not
      duplicated wholesale or dropped.
- [x] `main.ts` no longer contains any of the moved code.
- [x] `pxt.json`'s `files` array: `src/run.ts` inserted (position
      relative to `sim.ts`/`main.ts` is free — no load-time ordering
      constraint applies to this module; keep it adjacent to `sim.ts`
      for readability).
- [x] `tsconfig.json`'s `files` array: same insertion.
- [x] A real PXT build succeeds.
- [x] `test/test.ts` and `test/testrig.ts` run in the PXT simulator
      with identical behavior to ticket 001's post-extraction baseline
      — in particular, confirm no RUN-related boot-time error appears
      (the panic-980 smoke check this pattern exists to prevent).
- [x] Full existing `tests/host/` suite passes unchanged.
- [x] `test_pxt_manifest_completeness.py` passes.
- [x] No acceptance criterion above requires a robot.

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

## Completion Notes (programmer, this ticket)

**Symbols moved** (verbatim, original relative order): the RUN-state
block (`runParts`/`runNames`/`runHandlers`/`runAnyHandlers`/
`runWired`, all five with zero initialisers, grep-verified),
`ensureRunState()`, `RUN_EVENT_SOURCE`, `wireRunDispatch()`, `onRun()`,
`onRunCommand()`, `runArg()`, `runArgText()`, `runArgCount()`. All land
in one contiguous block in `src/run.ts`, even though in `main.ts` they
were split across two non-adjacent regions (state+`ensureRunState()`
right after `defaultSpeed`/`defaultYawRate`; the rest in a separate
"remote test trigger" section after `driveTick()`) — matches the
Implementation Plan's "keeping the moved block contiguous" in the new
file.

**Export decisions**: none of the nine moved symbols needed a NEW
`export` it didn't already have. `onRun`/`onRunCommand`/`runArg`/
`runArgText`/`runArgCount` were already `export function` (public
block API, called via qualified `diffDrive.xxx` from `test/test.ts`
and `test/testrig.ts` — that access path was never subject to ticket
001's bare-cross-file-reference finding). `runParts`/`runNames`/
`runHandlers`/`runAnyHandlers`/`runWired`/`ensureRunState`/
`wireRunDispatch`/`RUN_EVENT_SOURCE` stay non-exported — confirmed
file-local (nothing outside `run.ts` references them), matching the
ticket's "fully self-contained" framing. The only cross-file reference
this module makes is `wireRunDispatch()`'s bare call to
`runCommandText()`, which lives in `sim.ts` and was already exported
by ticket 001 — no new symbol needed exporting on either side.

**Dual-purpose comment**: by the time this ticket executed, the
no-initialiser/panic-980 paragraph and the `_startProtocol()`
unconditional-load paragraph were already two textually separate
comment blocks in `main.ts` (each sitting immediately above the code
it documents), not one merged block — likely drift since the overlay
was written. No trimming/splitting of shared text was needed: the
no-initialiser paragraph moved verbatim to `run.ts` next to
`runParts` et al.; the `_startProtocol()` paragraph was left exactly
as-is in `main.ts` (it never mentioned run state, so there was nothing
in it to point at `run.ts`).

**Manifest ordering**: `src/run.ts` inserted immediately after
`src/sim.ts` and before `src/main.ts` in both `pxt.json` and
`tsconfig.json`'s `files` arrays, per the ticket's "adjacent to sim.ts
for readability" guidance. No load-time ordering constraint applies —
`run.ts` has no top-level executable statements, only declarations and
function bodies invoked later.

**Build verification**: `uv run python tools/make_deploy.py` (hex
deleted first, mtime asserted fresh afterward) — codal-microbit-v2 hex
built on attempt 1, only the documented benign shapes appeared (legacy
V1 `srec_cat` "contradictory value" hex-merge failure, then a TS9200
packaging abort for that same legacy variant): `.tmp/deploy-head/
built/mbcodal-binary.hex`, 1,395,116 bytes, mtime freshly stamped this
run. `tools/make_deploy.py --testrig` also built clean (same benign
noise only): `.tmp/deploy-testrig/built/mbcodal-binary.hex`,
1,374,056 bytes, fresh mtime. `tsc -p .` returns to the exact
pre-existing baseline single error (`pxt_modules/core/basic.ts`
`TS2339: Property 'roundWithPrecision' does not exist on type
'Math'`) — unrelated, unchanged by this ticket.

**Simulator/testrig parity**: literal `pxt run` still fails to compile
on the post-split tree with the same pre-existing, unrelated TS9256
defect ticket 001 documented (`error TS9256: bit sizes are not
supported for locals and parameters`) — now attributed to `src/sim.ts`
lines 113/320/352/357 (the symbols ticket 001 moved there), none in
`run.ts`. Confirmed not caused by this ticket: none of the four
TS9256 sites are in code this ticket touched. Substitute evidence per
ticket 001's precedent: both `test/test.ts` and `test/testrig.ts`
compile cleanly for the hardware/build target against the split tree
(no RUN-related compile error), the no-initialiser pattern is
grep-verified intact, and `ensureRunState()`'s defensive guard (called
from every RUN entry point: `wireRunDispatch()`, `onRun()`,
`onRunCommand()`) is unchanged — the structural precondition for the
panic-980 class is preserved even though literal simulator execution
could not be observed.

**Unplanned fix required by the move**: `tests/host/
test_wire_constants_drift.py`'s
`test_run_event_source_matches_between_main_ts_and_protocol_cpp` (now
renamed `..._between_run_ts_and_protocol_cpp`) hardcoded `main.ts` as
the file to search for `RUN_EVENT_SOURCE`. Not called out in the
ticket's Description/Files-to-modify list, but a direct, necessary
consequence of moving that constant to `run.ts` — the acceptance
criterion "Full existing `tests/host/` suite passes unchanged" (i.e.
the invariant it checks is unchanged) required updating the helper's
file target and error strings from `main.ts` to `run.ts`. Full
`tests/host/` suite: 445 passed (444 before this fix + the corrected
one, confirmed via two runs — first run showed exactly this one
failure, second run after the fix showed all 445 green).
`test_pxt_manifest_completeness.py`: 2 passed (subset of the above).

**`main.ts` line count**: 759 lines before this ticket (ticket 001's
post-extraction baseline) → 639 lines after (120 lines removed,
matching `src/run.ts`'s 121 lines minus the file's own opening
`namespace diffDrive {` / closing `}` wrapper, which `main.ts` already
supplied and did not need to duplicate).
