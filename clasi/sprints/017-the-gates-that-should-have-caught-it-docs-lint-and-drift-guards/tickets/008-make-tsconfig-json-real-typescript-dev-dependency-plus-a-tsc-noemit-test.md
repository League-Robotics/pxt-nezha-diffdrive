---
id: 008
title: 'Make tsconfig.json real: typescript dev dependency plus a tsc --noEmit test'
status: open
use-cases: []
depends-on: []
github-issue: ''
issue: no-lint-or-typecheck-gate.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Make tsconfig.json real: typescript dev dependency plus a tsc --noEmit test

## Description

`tsconfig.json` exists, with a hand-maintained `files` array correctly kept
current by sprints 012 and 013, but nothing can execute it: `package.json`
declares only `pxt-microbit` as a dependency, `typescript` is not
installed, and `node_modules/typescript` does not exist. The 1149 lines of
student-facing TypeScript under `src/blocks/` are therefore type-checked
only by a full `pxt build` -- once per sprint, in the build-checkpoint
ticket (ticket 010 in this sprint) -- which type-checks but does not
*execute* anything, and a `goTo` geometry defect type-checked perfectly
while being behaviorally wrong.

**Stakeholder decision is already made** (recorded on the
`stakeholder_approval` gate): make `tsconfig.json` real rather than delete
it. Rationale on record: the review's Critical finding (block `goTo`
missing its target by 112mm) lived in TypeScript nothing executes or
type-checks between sprint build checkpoints; deleting the file would
close the paper-cut (an unmaintained config) but leave the actual gap
(no standalone TS check) open.

This ticket makes the file real. It does **not** attempt the "no
TypeScript is executed" gap the source issue calls out as its own future
conversation (a node-based harness with a stub `diffDrive` namespace) --
that's a larger investment, out of scope here. This ticket's job is: the
existing `tsconfig.json` should actually run and be checked automatically,
not describe a bigger testing initiative.

## What to change

1. Add `typescript` as a dev dependency in `package.json`. Pick a version
   compatible with `es2020` target output and the `moduleDetection: legacy`
   setting already in `tsconfig.json` -- don't need bleeding-edge, a recent
   stable release is fine. Confirm `npm install` (or whatever this repo's
   package manager is -- check for a lockfile) succeeds and
   `node_modules/typescript` exists afterward.
2. Add a pytest wrapper under `tests/host/` (or `tests/tools/` if that's a
   better fit for a Node-shelling test -- check which directory's `DESIGN.md`
   already documents non-compiler-shim external-process tests, if any) that
   shells `npx tsc --noEmit` (or the equivalent direct path to the installed
   `tsc` binary) and asserts a zero exit code. Follow the existing
   subprocess-invocation pattern used by `test_kernel_harness.py`'s
   `compile_shared_lib()` (capture stdout/stderr, assert returncode == 0,
   include the captured output in the assertion failure message so a
   failure is diagnosable from pytest output alone).
3. Run `tsc --noEmit` against the current tree and see what it reports. If
   it's clean, good. If it surfaces real type errors (plausible, since
   nothing has checked this before), fix genuine type errors that don't
   change behavior (e.g. missing type annotations, `any` leaks) but do
   **not** fix the `goTo` geometry defect itself here -- that's tracked as
   `block-go-to-misses-its-target.md`, a behavioral fix, not a type error,
   and is out of this sprint's "no firmware/TS behavior changes" scope. If
   `tsc` finds something that IS a real type error masking that defect or
   any other behavioral issue, flag it in the ticket's completion notes
   rather than silently fixing behavior.
4. Confirm the new test runs as part of the normal `uv run pytest` suite
   (no special invocation needed) so it participates in the sprint-close
   full-suite gate.

## Acceptance Criteria

- [ ] `package.json` lists `typescript` as a dev dependency; `npm install`
      (or equivalent) succeeds.
- [ ] A new pytest test shells `tsc --noEmit` against `tsconfig.json` and
      asserts success; it's discoverable by a normal `uv run pytest` run.
- [ ] The test passes against the current tree (either because `tsc` is
      clean, or because any real type errors found were fixed without
      changing runtime behavior).
- [ ] No behavioral TypeScript change -- specifically, the `goTo` geometry
      defect is NOT fixed here (that's a separate, tracked issue outside
      this sprint's scope).
- [ ] `tsconfig.json` itself is unchanged unless a genuine misconfiguration
      is found (e.g. its `files` array should be checked against ticket
      001/005's stale-path guard, but functional changes to it should be
      minimal and justified).

## Testing

- **Existing tests to run**: `uv run pytest tests/host/
  test_pxt_manifest_completeness.py` (sanity check that this ticket's
  `package.json`/`tsconfig.json` edits didn't disturb manifest
  consistency), plus a full `uv run pytest` once the new test is added, to
  confirm it's picked up and green.
- **New tests to write**: the `tsc --noEmit` pytest wrapper described
  above, e.g. `tests/host/test_typescript_typecheck.py`.
- **Verification command**: `uv run pytest tests/host/test_typescript_typecheck.py`.
