---
id: '002'
title: Move src/motion/ (motion engine) and its cross-file references
status: done
use-cases:
- SUC-001
- SUC-002
depends-on:
- '001'
github-issue: ''
issue: ''
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Move src/motion/ (motion engine) and its cross-file references

## Description

Second move. Move `motion_engine.h` and `motion_engine.cpp` into a new
`src/motion/` directory — the one layer directly above `src/core/`
(`motion_engine.h` includes `core/diffdrive.h`, already qualified by
ticket 001). This ticket depends on ticket 001 because `src/platform/`
(ticket 003) needs `motion/motion_engine.h` to already resolve via its
own consumers (`otos_port.h`, `encoder_pose_source.h`) before it moves,
and because this ticket reuses the same include-qualification rule
ticket 001 just confirmed (including the same-directory case:
`motion_engine.cpp` including `motion_engine.h` needs `#include
"motion/motion_engine.h"`, not a bare include, even though both files
move into `src/motion/` together).

No new technical question — this ticket applies ticket 001's confirmed
rule at a smaller scale (2 files instead of 4, no test-infrastructure
rewrite needed since `test_pxt_manifest_completeness.py` was already
made recursive-aware).

## Acceptance Criteria

- [x] `src/motion/motion_engine.h` and `src/motion/motion_engine.cpp`
      exist; the two original `src/`-root files are gone.
- [x] Every `#include` naming `motion_engine.h`, anywhere in the repo,
      is requalified to `#include "motion/motion_engine.h"`:
      - `src/motion/motion_engine.cpp`: stayed BARE (`#include
        "motion_engine.h"`) — this criterion's literal text was stale.
        See "Deviation from plan" below: a real cloud build proved the
        same-directory rule ticket 001 established (bare, not
        qualified) also applies here, and qualifying it is FATAL.
      - `src/encoder_pose_source.h`: `#include "motion_engine.h"` ->
        `#include "motion/motion_engine.h"` (done)
      - `src/otos_port.h`: `#include "motion_engine.h"` -> `#include
        "motion/motion_engine.h"` (done)
      - `src/shims.cpp`: `#include "motion_engine.h"` -> `#include
        "motion/motion_engine.h"` (done)
      - `tests/host/motion_engine_shim.cpp`,
        `tests/host/fake_pose_source.h`,
        `tests/host/wire_motion_verb_shim.cpp`: `#include
        "motion_engine.h"` -> `#include "motion/motion_engine.h"`
        (done, all three)
- [x] Every `_SRC_DIR / "motion_engine.cpp"` path literal is requalified
      to `_SRC_DIR / "motion" / "motion_engine.cpp"` in:
      `test_motion_engine_gotow.py`, `test_motion_engine_primitives.py`,
      `test_motion_engine_deadline_boundary.py`,
      `test_motion_engine_reductions.py`, `test_motion_engine_settle.py`,
      `test_wire_motion_verbs.py`, `test_cxx11_syntax_gate.py`.
- [x] `pxt.json`'s `files[]` array has its `motion_engine.h`,
      `motion_engine.cpp` entries rewritten to `src/motion/...`, in
      place — array order and every other entry unchanged.
      `tsconfig.json` is untouched.
- [x] `test_pxt_manifest_completeness.py` (already made recursive in
      ticket 001) passes against the tree with both `core/` and
      `motion/` populated.
- [x] `uv run python tools/make_deploy.py` succeeds and produces a hex.
- [x] `uv run python tools/make_deploy.py --testrig` succeeds and
      produces a hex.
- [x] The relevant `tests/host/` subset passes (see Testing below).

## Deviation from plan (build-verified, both halves)

The dispatch corrected ticket 001's rule mid-flight and that correction
held, but this ticket surfaced a THIRD case ticket 001 never exercised:
an including file that is itself in a *subdirectory* of `src/`,
referencing a target in a *different, sibling* subdirectory of `src/`
(not `src/` root, not the same directory). Two real cloud-build
failures nailed it down:

1. **`motion_engine.cpp` -> `motion_engine.h`, same directory
   (`src/motion/`).** The ticket's own acceptance-criteria text (written
   before this run) said to qualify this to `"motion/motion_engine.h"`.
   That is WRONG and matches ticket 001's already-known same-directory
   trap exactly: quote-includes resolve relative to the directory of the
   file CONTAINING the `#include`, so from `src/motion/motion_engine.cpp`,
   `"motion/motion_engine.h"` searches `src/motion/motion/motion_engine.h`
   (does not exist) and the build fails with `fatal error:
   motion/motion_engine.h: No such file or directory`. Left BARE
   (`#include "motion_engine.h"`), exactly as the dispatch's corrected
   same-directory rule said, it resolves fine. This is now build-verified
   twice (ticket 001's diffdrive.cpp case, this ticket's motion_engine.cpp
   case) — the same-directory rule stands as: always bare, never
   qualified, regardless of how deep the shared directory sits.

2. **`motion_engine.h` -> `core/diffdrive.h`, sibling directories
   (`src/motion/` -> `src/core/`).** `motion_engine.h` inherited
   `#include "core/diffdrive.h"` unchanged from ticket 001, when
   `motion_engine.h` still lived at `src/` root and that path was correct
   (root -> child subdirectory). Moving `motion_engine.h` itself into
   `src/motion/` broke it: quote-include resolution is relative to the
   INCLUDING FILE's own directory, not to any fixed `src/` root, so
   `"core/diffdrive.h"` from `src/motion/motion_engine.h` searched
   `src/motion/core/diffdrive.h` (does not exist) ->
   `fatal error: core/diffdrive.h: No such file or directory`. Fixed to
   `#include "../core/diffdrive.h"` (relative to `src/motion/`, one level
   up then into `core/`), which built clean.

**Refined rule for tickets 003-006** (both halves now build-verified
across three cases: root->child, same-dir, and sibling->sibling): a
quote-include always resolves relative to the directory of the file
that CONTAINS the `#include` line, never relative to any fixed `src/`
root and never relative to the top translation unit. Concretely:
  - Same directory, any depth: bare, never qualified.
  - Including file is directly in `src/` root, target in a child
    subdirectory: qualify as `"<subdir>/<name>.h"`.
  - Including file is itself in a subdirectory, target is in a
    DIFFERENT sibling subdirectory of `src/`: qualify as
    `"../<sibling-subdir>/<name>.h"`, NOT `"<sibling-subdir>/<name>.h"`.
    Ticket 003 will hit this directly: once `otos_port.h`/
    `encoder_pose_source.h` move into `src/platform/`, their existing
    `#include "motion/motion_engine.h"` (root->child form, correct
    today) must become `#include "../motion/motion_engine.h"` once they
    are no longer in `src/` root themselves.

No logic changes, no symbol renames — this is include-path surgery only,
exactly as scoped. Both `make_deploy.py` and `make_deploy.py --testrig`
now succeed end to end (see commit for hex sizes/mtimes).

## Implementation Plan

**Approach**: `git mv` the two files into `src/motion/`, fix the
same-directory `#include` in `motion_engine.cpp` first (the case ticket
001 just proved matters), then fix every cross-file reference, then the
`_SRC_DIR` literals, then `pxt.json`. Run the scoped host-test subset,
then both `make_deploy.py` builds.

**Files to create**: `src/motion/motion_engine.h`,
`src/motion/motion_engine.cpp` (via move).

**Files to modify**: `src/encoder_pose_source.h`, `src/otos_port.h`,
`src/shims.cpp`, `tests/host/motion_engine_shim.cpp`,
`tests/host/fake_pose_source.h`,
`tests/host/wire_motion_verb_shim.cpp`,
`tests/host/test_motion_engine_gotow.py`,
`tests/host/test_motion_engine_primitives.py`,
`tests/host/test_motion_engine_deadline_boundary.py`,
`tests/host/test_motion_engine_reductions.py`,
`tests/host/test_motion_engine_settle.py`,
`tests/host/test_wire_motion_verbs.py`,
`tests/host/test_cxx11_syntax_gate.py`, `pxt.json`.

**Testing plan**: scoped `tests/host/` subset (below), then
`make_deploy.py` and `make_deploy.py --testrig`. Full suite deferred to
`close_sprint`.

**Documentation updates**: none in this ticket — deferred to ticket 006.

## Testing

- **Existing tests to run**: `uv run pytest
  tests/host/test_motion_engine_gotow.py
  tests/host/test_motion_engine_primitives.py
  tests/host/test_motion_engine_deadline_boundary.py
  tests/host/test_motion_engine_reductions.py
  tests/host/test_motion_engine_settle.py tests/host/test_wire_motion_verbs.py
  tests/host/test_cxx11_syntax_gate.py
  tests/host/test_pxt_manifest_completeness.py
  tests/host/test_kernel_harness.py`
- **New tests to write**: none — file move only.
- **Verification command**: the pytest command above, then
  `uv run python tools/make_deploy.py` and
  `uv run python tools/make_deploy.py --testrig`.
