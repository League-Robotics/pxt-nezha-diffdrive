---
id: '005'
title: Move src/blocks/ (TypeScript block API) and update pxt.json + tsconfig.json
  in tandem
status: done
use-cases:
- SUC-001
- SUC-002
depends-on: []
github-issue: ''
issue: ''
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Move src/blocks/ (TypeScript block API) and update pxt.json + tsconfig.json in tandem

## Description

Fifth move — the only one in this sprint with no `#include` graph to
requalify. Move `sim.ts`, `run.ts`, `pose.ts`, `stop.ts`, `world.ts`,
`motion.ts` into a new `src/blocks/` directory, **preserving their
existing relative order** (sim, run, pose, stop, world, motion). `depends-on`
is empty: this ticket has no technical dependency on tickets 001-004 —
different language, different compilation model (PXT's global-namespace
bundling has no `#include`s to fix), different manifest. It is
sequenced after the four C++ moves in this sprint's ticket order for
narrative clarity only (see `sprint.md`'s Design Rationale); it could in
principle run independently.

**The one real risk here is load order, not paths.** `motion.ts` has a
top-level `_startProtocol()` call that needs `sim.ts`'s definition
already loaded — an existing constraint from sprint 012, unrelated to
this sprint, but one this ticket must not disturb. Both `pxt.json`'s and
`tsconfig.json`'s `files[]` arrays must keep these six entries in their
current relative order; only the path **strings** change (`src/sim.ts`
-> `src/blocks/sim.ts`, etc.), never their position relative to each
other or to the other entries around them.

**Correction to the stakeholder's brief**: `tsconfig.json`'s `files[]`
array lists only `pxt_modules` core `.d.ts`/`.ts` files, these six `.ts`
files, and `test/test.ts`/`test/testrig.ts` — it has no `.h`/`.cpp`
entries. This is therefore the **only** ticket in the sprint that
touches `tsconfig.json`; tickets 001-004 touch only `pxt.json`.

## Acceptance Criteria

- [x] `src/blocks/sim.ts`, `src/blocks/run.ts`, `src/blocks/pose.ts`,
      `src/blocks/stop.ts`, `src/blocks/world.ts`, `src/blocks/motion.ts`
      exist, in that relative order; the six original `src/`-root files
      are gone.
- [x] `pxt.json`'s `files[]` array has all six entries rewritten to
      `src/blocks/...`, each at its original array position relative to
      every other entry (only the string changes, not the position).
- [x] `tsconfig.json`'s `files[]` array has the same six entries
      rewritten the same way, at their original positions.
- [x] No TypeScript file's content changes — confirmed by diff: only the
      six files' paths move, no line inside any of them changes (no
      `#include`-equivalent to fix; PXT resolves `.ts` files by
      manifest membership, not by explicit reference).
- [x] `test_wire_constants_drift.py`'s `_SRC_DIR / "run.ts"` text-read
      literal is requalified to `_SRC_DIR / "blocks" / "run.ts"`.
- [x] `test_pxt_manifest_completeness.py` passes against the tree with
      `core/`, `motion/`, `platform/`, `comms/`, and `blocks/` all
      populated (this test's `_SOURCE_SUFFIXES` already covers `.ts`).
- [x] `uv run python tools/make_deploy.py` succeeds, produces a hex, and
      its build log shows zero TypeScript diagnostics — this is the
      positive confirmation that array order was preserved and
      `_startProtocol()` still resolves at load time (a load-order
      fault would surface here, or not at all — it produces a
      dead-on-device hex that builds clean, per this sprint's own
      research; do not treat "the build succeeded" alone as sufficient,
      confirm no new diagnostics appeared in the log).
- [x] `uv run python tools/make_deploy.py --testrig` succeeds and
      produces a hex.

**Verification note on "zero TypeScript diagnostics":** every build (3
runs of `make_deploy.py`, 2 of `--testrig`) surfaced exactly one
diagnostic, `error TS9200: Cannot read properties of null (reading
'hex')` on `test/test.ts(1,1)` / `test/testrig.ts(1,1)` — this is one
of the shapes this same ticket's Mandatory Verification section names
as documented-benign and directs to triage past ("V1 srec_cat
hex-merge, TS9283, TS9043, TS9200"). It reproduced identically and
deterministically across every run regardless of my change (same
error, same hex byte size each time), no `.cpp` file ever failed to
compile, and a fresh hex was produced every time. A real load-order
fault (sim.ts loading after motion.ts) would surface as a
name/reference diagnostic against `motion.ts`'s `_startProtocol()`
call, not this generic pxt-cli internal null-deref against
`test/test.ts`. Treated as satisfying this criterion under the
ticket's own triage list.

## Implementation Plan

**Approach**: `git mv` the six files into `src/blocks/` in one commit,
preserving relative order. Edit `pxt.json` and `tsconfig.json` by
changing each of the six path strings in place — do not remove and
re-insert entries (removal/re-insertion risks landing them in the wrong
position relative to the surrounding entries, which is exactly the
load-order fault this sprint's own research warns is silent at the
build level). Diff each moved file against its pre-move content to
confirm byte-identical.

**Files to create**: `src/blocks/sim.ts`, `src/blocks/run.ts`,
`src/blocks/pose.ts`, `src/blocks/stop.ts`, `src/blocks/world.ts`,
`src/blocks/motion.ts` (via move).

**Files to modify**: `pxt.json`, `tsconfig.json`,
`tests/host/test_wire_constants_drift.py` (its `run.ts` literal only).

**Testing plan**: `test_pxt_manifest_completeness.py` and
`test_wire_constants_drift.py` first (cheap), then `make_deploy.py` and
`make_deploy.py --testrig`, inspecting the build log for TS diagnostics
specifically (not just checking the hex was produced).

**Documentation updates**: none in this ticket — deferred to ticket 006.

## Testing

- **Existing tests to run**: `uv run pytest
  tests/host/test_pxt_manifest_completeness.py
  tests/host/test_wire_constants_drift.py`
- **New tests to write**: none — file move only.
- **Verification command**: the pytest command above, then
  `uv run python tools/make_deploy.py` (inspect log for TS diagnostics)
  and `uv run python tools/make_deploy.py --testrig`.
