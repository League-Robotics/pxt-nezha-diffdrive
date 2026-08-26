---
id: '001'
title: 'Proof: move src/core/ (kernel + host-portable math), verify the include-qualification
  rule, and make the manifest-completeness guard subdirectory-aware'
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

# Proof: move src/core/ (kernel + host-portable math), verify the include-qualification rule, and make the manifest-completeness guard subdirectory-aware

## Description

First of five moves. Move `diffdrive.h`, `diffdrive.cpp`, `heading_wrap.h`,
and `encoder_glitch_armor.h` into a new `src/core/` directory — the
dependency-free layer (kernel + the two host-portable math utilities
that depend on nothing but libc, per `sprint.md`'s Architecture Overview
table). This is the sprint's **proof ticket**, mirroring sprint 012
ticket 001's role: it is where the sprint's two governing empirical
claims get tested against real code, before four more tickets build on
the assumption that they hold.

**What this ticket proves, specifically:**

1. **Cross-directory qualification works.** `motion_engine.h` (still at
   `src/` root in this ticket) including `core/diffdrive.h` is the
   already-confirmed case from the sprint's own pre-planning research.
2. **Same-directory qualification is also required — this is the
   untested case `sprint.md`'s Architecture Overview flags.**
   `diffdrive.cpp` includes `diffdrive.h` today with a bare
   `#include "diffdrive.h"`. After this ticket, both files live in
   `src/core/` together. If a bare same-directory include still worked,
   that would change every other ticket's approach (siblings moving
   together could stay unqualified). It does not: this project's builds
   pass `-I src` (never `-I src/core`), so `diffdrive.cpp` needs
   `#include "core/diffdrive.h"` even though `diffdrive.h` sits right
   next to it. Confirm this with a real build, not by reasoning about it
   — if it turns out bare same-directory includes DO work, say so
   explicitly in this ticket's completion notes, since it would change
   every remaining ticket's approach.
3. **The manifest-completeness guard must not silently degrade.**
   `tests/host/test_pxt_manifest_completeness.py`'s `_src_files_on_disk()`
   currently uses `_SRC_DIR.iterdir()` — not recursive. Once files start
   moving into subdirectories, this silently stops checking them (it
   does not fail — `iterdir()` just never sees them, so
   `test_every_src_file_is_manifest_listed()` quietly checks fewer files
   each ticket). By the end of this sprint it would be checking almost
   nothing. Rewrite it in this ticket, while the guard's behavior is
   still easy to verify against a mostly-flat tree, not in ticket 006 once
   the tree is already fully reorganized and there is no gap left to see.

## Acceptance Criteria

- [x] `src/core/diffdrive.h`, `src/core/diffdrive.cpp`,
      `src/core/heading_wrap.h`, `src/core/encoder_glitch_armor.h` exist;
      the four original `src/`-root files are gone (moved, not copied).
- [x] Every `#include` naming one of these four files, anywhere in the
      repo, is requalified to `#include "core/<name>"` for the
      **cross-directory** cases — **EXCEPT** the same-directory
      `diffdrive.cpp` -> `diffdrive.h` case, which real-build evidence
      proved must stay BARE. See "Completion notes: same-directory
      finding" below — this deviates from the criterion as originally
      written, deliberately, backed by a build. Specifically, as
      implemented:
      - `src/core/diffdrive.cpp`: **stays** `#include "diffdrive.h"`
        (NOT requalified — see finding below; qualifying it broke the
        build).
      - `src/motion_engine.h`: `#include "diffdrive.h"` ->
        `#include "core/diffdrive.h"` (cross-directory, confirmed working)
      - `src/nezha_port.h`: `#include "diffdrive.h"` ->
        `#include "core/diffdrive.h"`; `#include "encoder_glitch_armor.h"`
        -> `#include "core/encoder_glitch_armor.h"` (cross-directory)
      - `src/otos_port.cpp`: `#include "heading_wrap.h"` ->
        `#include "core/heading_wrap.h"` (cross-directory)
      - `src/platform_ports.h`: `#include "diffdrive.h"` ->
        `#include "core/diffdrive.h"` (cross-directory)
      - `src/shims.cpp`: `#include "diffdrive.h"` -> `#include
        "core/diffdrive.h"` (cross-directory; its other five includes
        are untouched — they move in tickets 002/003)
      - `tests/host/kernel_shim.cpp`, `tests/host/fake_ports.h`,
        `tests/host/motion_engine_shim.cpp`,
        `tests/host/wire_motion_verb_shim.cpp`: `#include "diffdrive.h"`
        -> `#include "core/diffdrive.h"` (cross-directory: tests/host/ to
        src/core/)
      - `tests/host/heading_wrap_shim.cpp`,
        `tests/host/heading_wrap_syntax_check.cpp`: `#include
        "heading_wrap.h"` -> `#include "core/heading_wrap.h"`
        (cross-directory)
      - `tests/host/encoder_glitch_armor_shim.cpp`,
        `tests/host/encoder_glitch_armor_syntax_check.cpp`: `#include
        "encoder_glitch_armor.h"` -> `#include
        "core/encoder_glitch_armor.h"` (cross-directory)
- [x] Every `_SRC_DIR / "diffdrive.cpp"` path literal is requalified to
      `_SRC_DIR / "core" / "diffdrive.cpp"` in: `test_kernel_harness.py`,
      `test_motion_engine_gotow.py`, `test_motion_engine_primitives.py`,
      `test_motion_engine_deadline_boundary.py`,
      `test_motion_engine_reductions.py`, `test_motion_engine_settle.py`,
      `test_wire_motion_verbs.py`, `test_cxx11_syntax_gate.py`. (These
      files' `motion_engine.cpp`/`wire_handler.cpp`/`wire_adapter.cpp`
      entries, where present, stay unqualified for now — tickets 002/004
      handle those. These are `.py` path literals used to locate the
      file for compilation, not `#include` directives, so they are
      unaffected by the same-directory finding below — that finding is
      specific to the C++ preprocessor's quote-include search order.)
- [x] `pxt.json`'s `files[]` array has its four `diffdrive.h`,
      `diffdrive.cpp`, `heading_wrap.h`, `encoder_glitch_armor.h` entries
      rewritten to `src/core/...`, in place — array order and every other
      entry unchanged. `tsconfig.json` is untouched (it lists no `.h`/
      `.cpp` entries — see sprint.md's Migration Concerns correction).
- [x] `tests/host/test_pxt_manifest_completeness.py`'s
      `_src_files_on_disk()` recurses into subdirectories (e.g.
      `_SRC_DIR.rglob(...)`) and returns `src/`-relative paths that
      preserve any directory prefix, instead of `f"src/{p.name}"` over a
      non-recursive `iterdir()`. Both of its tests
      (`test_every_src_file_is_manifest_listed`,
      `test_no_manifest_entry_is_stale`) pass against the now-partially-
      nested tree, and would correctly catch a moved-but-unlisted or
      listed-but-missing file if one existed. Verified directly (not
      assumed): a temporary sentinel file was written to `src/core/`,
      confirmed present in `_src_files_on_disk()`'s output, confirmed
      absent from `pxt.json`'s manifest, confirmed to appear in the
      `missing` list `test_every_src_file_is_manifest_listed()` would
      assert on — then removed. See Completion notes.
- [x] `uv run python tools/make_deploy.py` succeeds and produces a hex.
- [x] `uv run python tools/make_deploy.py --testrig` succeeds and
      produces a hex.
- [x] The relevant `tests/host/` subset passes: `test_kernel_harness.py`,
      `test_heading_wrap.py`, `test_encoder_glitch_armor.py`,
      `test_motion_engine_*.py`, `test_wire_motion_verbs.py`,
      `test_cxx11_syntax_gate.py`, `test_pxt_manifest_completeness.py`.
- [x] Completion notes record explicitly whether the same-directory
      qualification requirement (finding 2 above) was confirmed as
      expected, since every later ticket in this sprint relies on it.
      **It was NOT confirmed as expected — the opposite was found.**
      See below.

## Completion notes: same-directory finding

**Finding 2 from the Description ("same-directory qualification is also
required") is WRONG. The real build proves the opposite: same-directory
includes must stay BARE.**

Evidence, gathered against the real cloud/local build
(`uv run python tools/make_deploy.py`), not reasoned about:

1. First attempt qualified `src/core/diffdrive.cpp`'s own include of
   `diffdrive.h` to `#include "core/diffdrive.h"`, per this ticket's
   literal Acceptance Criteria text. Build failed with a genuine
   compile diagnostic (hard failure, no retry, per
   `classify_attempt()`'s own "did a .cpp fail to compile" rule):
   ```
   /home/build/prj2/source/nezha-diffdrive/src/core/diffdrive.cpp:8:28:
   fatal error: core/diffdrive.h: No such file or directory
   ```
2. Root cause: PXT's build sandbox stages each `pxt.json`-listed file at
   a path that preserves its manifest-relative directory, so
   `diffdrive.cpp` lands at
   `.../source/nezha-diffdrive/src/core/diffdrive.cpp`. The C++
   preprocessor's quote-include (`#include "..."`) search order checks
   the *including file's own directory* first. From within
   `.../src/core/`, `#include "core/diffdrive.h"` resolves to
   `.../src/core/core/diffdrive.h` — a self-inflicted double-nesting
   that does not exist. There is no `-I src` (or equivalent) flag in
   this build's actual compile invocation that would let the qualified
   form resolve some other way; the sprint's own pre-planning research
   assumed one existed project-wide, but the real compile command
   (captured in the build log) shows no such flag for this extension's
   source root.
3. Reverted `src/core/diffdrive.cpp`'s own include back to the original
   bare `#include "diffdrive.h"` (both files are in `src/core/`
   together, so the current-file-directory search finds it directly at
   `.../src/core/diffdrive.h`). Rebuilt: `make_deploy.py` succeeded on
   attempt 1, hex produced (1,399,931 bytes). `make_deploy.py --testrig`
   also succeeded on attempt 1, hex produced (1,377,296 bytes). Both
   only showed the documented-benign V1 srec_cat hex-merge / TS9200
   shapes from `tools/DESIGN.md`, not a real compile diagnostic.
4. Confirmed the cross-directory case (finding 1: `motion_engine.h`,
   still at `src/` root, including `core/diffdrive.h`) is unaffected and
   still requires qualification — its own file lives at
   `.../src/motion_engine.h`, so `#include "core/diffdrive.h"` resolves
   relative to that directory to `.../src/core/diffdrive.h`, which
   exists. This is why the sprint's pre-planning cross-directory test
   passed: it happened to be testing quote-include's
   directory-of-current-file rule, not a global `-I src` flag, and got
   the right answer for the wrong assumed reason.

**Why `uv run pytest` did not catch this in either direction.** The host
test harness (`tests/host/*.py`'s `compile_shared_lib()`) explicitly
passes `include_dirs=[_SRC_DIR, _TEST_DIR]` (i.e. `-I src`) to the host
g++ invocation. With that flag present, quote-include falls through to
`-I` search after failing the current-file-directory check, so
`#include "core/diffdrive.h"` from within `src/core/diffdrive.cpp`
*does* resolve on the host (via `-I src` -> `src/core/diffdrive.h`) even
though it does not in the real PXT build (which has no equivalent
flag). This is exactly the gap the ticket's dispatch flagged up front:
"this failure class appears ONLY in the cloud C++ compile... A real
build is the proof, not the test suite" — confirmed in the strongest
possible way, since the host suite would have reported this ticket
green with the wrong include in place.

**Impact on remaining sprint tickets (002-006):** any ticket that moves
files where two files in the SAME destination subdirectory `#include`
each other (sibling headers/sources landing together) should keep those
particular includes BARE, not qualify them — qualifying a same-directory
include is what breaks the build. Only includes that cross a directory
boundary (a file in one subdirectory, or `src/` root, including a file
that lives in a *different* subdirectory) need the `"subdir/name.h"`
qualified form. This should be flagged to the team-lead / sprint plan
before ticket 002 proceeds, since ticket 002 and later were drafted
under the original (now-disproven) assumption.

## Other observations (reported, not fixed — out of scope this ticket)

- None found. The four moved files required no other changes; per
  ticket scope, no opportunistic cleanup was performed.

## Implementation Plan

**Approach**: move the four files with `git mv` (preserves history),
then fix every reference in the order: production `src/` includes,
`tests/host/` shim/syntax-check includes, `tests/host/*.py` path
literals, `pxt.json`. Rewrite
`test_pxt_manifest_completeness.py`'s disk-listing helper before running
it against the moved tree, so its own test run is real evidence, not
passing-by-omission. Run the scoped host-test subset first (cheap,
catches include mistakes fast), then both `make_deploy.py` builds last
(expensive, authoritative for the actual failure mode this sprint
guards against).

**Files to create**: `src/core/diffdrive.h`, `src/core/diffdrive.cpp`,
`src/core/heading_wrap.h`, `src/core/encoder_glitch_armor.h` (via move).

**Files to modify**: `src/motion_engine.h`, `src/nezha_port.h`,
`src/otos_port.cpp`, `src/platform_ports.h`, `src/shims.cpp`,
`tests/host/kernel_shim.cpp`, `tests/host/fake_ports.h`,
`tests/host/motion_engine_shim.cpp`,
`tests/host/wire_motion_verb_shim.cpp`,
`tests/host/heading_wrap_shim.cpp`,
`tests/host/heading_wrap_syntax_check.cpp`,
`tests/host/encoder_glitch_armor_shim.cpp`,
`tests/host/encoder_glitch_armor_syntax_check.cpp`,
`tests/host/test_kernel_harness.py`,
`tests/host/test_motion_engine_gotow.py`,
`tests/host/test_motion_engine_primitives.py`,
`tests/host/test_motion_engine_deadline_boundary.py`,
`tests/host/test_motion_engine_reductions.py`,
`tests/host/test_motion_engine_settle.py`,
`tests/host/test_wire_motion_verbs.py`,
`tests/host/test_cxx11_syntax_gate.py`,
`tests/host/test_pxt_manifest_completeness.py`, `pxt.json`.

**Testing plan**: scoped `tests/host/` subset listed in Acceptance
Criteria, then `make_deploy.py` and `make_deploy.py --testrig`. Do not
run the full `tests/host/` suite (per this project's per-ticket scoping
convention — the full suite runs once at `close_sprint`).

**Documentation updates**: none in this ticket — `src/DESIGN.md` and
`docs/design/*.md` prose sweeps are ticket 006's job, once all moves are
final and there's one sweep instead of five.

## Testing

- **Existing tests to run**: `uv run pytest tests/host/test_kernel_harness.py
  tests/host/test_heading_wrap.py tests/host/test_encoder_glitch_armor.py
  tests/host/test_motion_engine_gotow.py
  tests/host/test_motion_engine_primitives.py
  tests/host/test_motion_engine_deadline_boundary.py
  tests/host/test_motion_engine_reductions.py
  tests/host/test_motion_engine_settle.py
  tests/host/test_wire_motion_verbs.py tests/host/test_cxx11_syntax_gate.py
  tests/host/test_pxt_manifest_completeness.py`
- **New tests to write**: none — this ticket moves files and rewrites one
  existing test helper's file-discovery logic; no new behavior to cover.
- **Verification command**: the pytest command above, then
  `uv run python tools/make_deploy.py` and
  `uv run python tools/make_deploy.py --testrig`.
