---
id: '003'
title: Move src/platform/ (hardware ports + pose-source abstraction) and its cross-file
  references
status: done
use-cases:
- SUC-001
- SUC-002
depends-on:
- '001'
- '002'
github-issue: ''
issue: ''
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Move src/platform/ (hardware ports + pose-source abstraction) and its cross-file references

## Description

Third move. Move `platform_ports.h`, `nezha_port.h`, `nezha_port.cpp`,
`otos_port.h`, `otos_port.cpp`, and `encoder_pose_source.h` into a new
`src/platform/` directory — the hardware-facing port implementations
(I2C/CODAL) plus the pose-source abstraction they share (see
`sprint.md`'s Architecture Overview for why `encoder_pose_source.h`
groups here by role rather than with `motion/` by its one dependency).
Depends on tickets 001 and 002 because `otos_port.h` and
`encoder_pose_source.h` both include `motion/motion_engine.h`
(ticket 002), and `nezha_port.h` includes `core/diffdrive.h` and
`core/encoder_glitch_armor.h` (ticket 001) — those includes are already
qualified from those tickets and stay that way; this ticket only adds
the `platform/` qualification for the files moving now.

**One thing this ticket touches that isn't itself in `platform/`**:
`src/protocol.h` (still at `src/` root — it moves in ticket 004)
includes `platform_ports.h`. Since `platform_ports.h` moves in this
ticket, `protocol.h`'s include must be requalified now, even though
`protocol.h` itself won't move for another ticket. This is the general
pattern for every ticket in this sprint: fix every referencing file
repo-wide when the referenced file moves, regardless of whether the
referencing file has moved yet itself.

## Acceptance Criteria

- [x] `src/platform/platform_ports.h`, `src/platform/nezha_port.h`,
      `src/platform/nezha_port.cpp`, `src/platform/otos_port.h`,
      `src/platform/otos_port.cpp`, `src/platform/encoder_pose_source.h`
      exist; the six original `src/`-root files are gone.
- [x] Every `#include` naming one of these six files, anywhere in the
      repo, resolves correctly under the includer-relative rule
      (**CORRECTION found during implementation**: this ticket's two
      "same-directory case" bullets below were stale — copied from an
      earlier, incorrect "qualify relative to src/" reading that the
      dispatching team-lead had already flagged and overridden before
      this ticket started. `nezha_port.cpp` and `otos_port.cpp` sit in
      the SAME directory as the headers they include after the move, so
      their bare includes are LEFT UNCHANGED, per the same rule that
      keeps `src/core/diffdrive.cpp`'s `#include "diffdrive.h"` bare):
      - `src/platform/nezha_port.cpp`: `#include "nezha_port.h"` — left
        BARE, unchanged (same-directory case; requalifying it would have
        been wrong)
      - `src/platform/otos_port.cpp`: `#include "otos_port.h"` — left
        BARE, unchanged (same-directory case); its `#include
        "core/heading_wrap.h"` requalified to `#include
        "../core/heading_wrap.h"` (core/ is now a sibling directory of
        platform/, not a child)
      - `src/platform/platform_ports.h`: `#include "core/diffdrive.h"`
        -> `#include "../core/diffdrive.h"`
      - `src/platform/nezha_port.h`: `#include "core/diffdrive.h"` ->
        `#include "../core/diffdrive.h"`; `#include
        "core/encoder_glitch_armor.h"` -> `#include
        "../core/encoder_glitch_armor.h"`
      - `src/platform/otos_port.h`: `#include "motion/motion_engine.h"`
        -> `#include "../motion/motion_engine.h"`
      - `src/platform/encoder_pose_source.h`: `#include
        "motion/motion_engine.h"` -> `#include
        "../motion/motion_engine.h"`
      - `src/shims.cpp`: `#include "encoder_pose_source.h"` -> `#include
        "platform/encoder_pose_source.h"`; `#include "nezha_port.h"` ->
        `#include "platform/nezha_port.h"`; `#include "otos_port.h"` ->
        `#include "platform/otos_port.h"`; `#include "platform_ports.h"`
        -> `#include "platform/platform_ports.h"` (this completes
        `shims.cpp`'s include block — every include it has is now
        qualified; no later ticket touches it again)
      - `src/protocol.h` (not yet moved): `#include "platform_ports.h"`
        -> `#include "platform/platform_ports.h"`
      - `tests/host/motion_engine_shim.cpp`: `#include
        "encoder_pose_source.h"` -> `#include
        "platform/encoder_pose_source.h"`
      - `tests/host/encoder_pose_source_syntax_check.cpp` (found during
        the repo-wide sweep, not named in this ticket's original list but
        covered by "anywhere in the repo"): `#include
        "encoder_pose_source.h"` -> `#include
        "platform/encoder_pose_source.h"` (this file compiles against
        `-I src`, same as `motion_engine_shim.cpp` — it needs the
        qualified form for the exact same reason)
- [x] No `_SRC_DIR` path-literal changes are needed for this ticket —
      confirmed no `tests/host/*.py` file compiles
      `nezha_port.cpp`/`otos_port.cpp` directly as a `_SHIM_SOURCES`
      entry (verified during planning: only shim/header includes
      reference these six files, not compiled-source-path lists).
      Also confirmed `test_wire_constants_drift.py` and
      `test_wire_telemetry_projection.py`'s `.read_text()` calls name
      only `protocol.cpp`, `radio_transport.h`, `wire_adapter.cpp`, and
      `shims.cpp` — none of the six moved files — so neither needed a
      path update either.
- [x] `pxt.json`'s `files[]` array has its six entries (`platform_ports.h`,
      `nezha_port.h`, `nezha_port.cpp`, `otos_port.h`, `otos_port.cpp`,
      `encoder_pose_source.h`) rewritten to `src/platform/...`, in place
      — array order and every other entry unchanged. `tsconfig.json` is
      untouched.
- [x] `test_pxt_manifest_completeness.py` passes against the tree with
      `core/`, `motion/`, and `platform/` all populated.
- [x] `uv run python tools/make_deploy.py` succeeds and produces a hex.
- [x] `uv run python tools/make_deploy.py --testrig` succeeds and
      produces a hex.
- [x] The relevant `tests/host/` subset passes (see Testing below).

## Implementation Plan

**Approach**: `git mv` the six files into `src/platform/`, fix the two
same-directory includes (`nezha_port.cpp`, `otos_port.cpp`) first, then
`shims.cpp` (all four of its remaining bare includes resolve in this one
ticket), then `protocol.h` (the not-yet-moved cross-reference), then the
test shim include, then `pxt.json`. Run the scoped host-test subset,
then both `make_deploy.py` builds.

**Files to create**: `src/platform/platform_ports.h`,
`src/platform/nezha_port.h`, `src/platform/nezha_port.cpp`,
`src/platform/otos_port.h`, `src/platform/otos_port.cpp`,
`src/platform/encoder_pose_source.h` (via move).

**Files to modify**: `src/shims.cpp`, `src/protocol.h`,
`tests/host/motion_engine_shim.cpp`, `pxt.json`.

**Testing plan**: scoped `tests/host/` subset (below), then
`make_deploy.py` and `make_deploy.py --testrig`. Full suite deferred to
`close_sprint`.

**Documentation updates**: none in this ticket — deferred to ticket 006.

## Testing

- **Existing tests to run**: `uv run pytest
  tests/host/test_motion_engine_gotow.py
  tests/host/test_motion_engine_primitives.py
  tests/host/test_pxt_manifest_completeness.py
  tests/host/test_cxx11_syntax_gate.py`
  (these exercise `motion_engine_shim.cpp`, the only test-side file
  changed by this ticket, plus the manifest guard; `shims.cpp` and
  `nezha_port.cpp`/`otos_port.cpp` are CODAL-bound and not
  host-compiled — see `src/DESIGN.md` §1 — so their correctness is
  proven by the real build below, not by `pytest`)
- **New tests to write**: none — file move only.
- **Verification command**: the pytest command above, then
  `uv run python tools/make_deploy.py` and
  `uv run python tools/make_deploy.py --testrig` (this ticket's
  authoritative evidence, since `shims.cpp`/`nezha_port.*`/`otos_port.*`
  cannot be host-compiled).
