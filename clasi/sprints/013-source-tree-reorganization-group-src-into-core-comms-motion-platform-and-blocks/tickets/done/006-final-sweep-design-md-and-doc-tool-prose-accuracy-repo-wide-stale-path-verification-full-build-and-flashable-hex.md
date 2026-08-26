---
id: '006'
title: 'Final sweep: DESIGN.md and doc/tool prose accuracy, repo-wide stale-path verification,
  full build and flashable hex'
status: done
use-cases:
- SUC-001
- SUC-002
depends-on:
- '001'
- '002'
- '003'
- '004'
- '005'
github-issue: ''
issue: ''
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Final sweep: DESIGN.md and doc/tool prose accuracy, repo-wide stale-path verification, full build and flashable hex

## Description

Sixth and last ticket. By this point every file has moved and every
functional reference (`#include`s, manifests, test path literals) is
already fixed by tickets 001-005 — `shims.cpp`'s own includes were
completed in ticket 003 and need no further change here. What remains is
prose accuracy (`src/DESIGN.md` itself, `docs/design/*.md`, `tools/`
comments), a repo-wide verification pass, and the sprint's final,
authoritative build.

**`src/DESIGN.md` changes** (the doc explicitly named in the
stakeholder's brief as needing an update):

1. Fix the now-false opening claim (line 5): "`src/` is flat — no
   subdirectories — so this one document carries the logical subsystem
   breakdown as sections." Replace with an accurate statement of the new
   layout, while keeping the doc's role (behavioral/design detail
   directory structure alone can't carry) intact.
2. Update §1's layer-map table's "Files" column to show the new
   directory-qualified names (e.g. `core/diffdrive.h/.cpp`,
   `motion/motion_engine.h/.cpp`, `platform/nezha_port.*`, `platform/
   otos_port.*`, `platform/platform_ports.h`, `comms/serial_transport.*`,
   `comms/radio_transport.*`, `comms/wire_handler.h/.cpp`, `comms/
   wire_adapter.h/.cpp`, `comms/protocol.h/.cpp`, `shims.cpp` unchanged,
   `blocks/sim.ts` etc.).
3. Update §2-§9's individual section headings to include the new
   directory prefix (e.g. "## 2. Kernel — `core/diffdrive.h/.cpp`
   (...)"), matching §1's table. This is judged in-scope as a
   factual-accuracy fix (the move makes the current headings wrong), not
   a "while-we're-here" improvement — flagged as an explicit judgment
   call in `sprint.md`'s Open Questions; if the stakeholder prefers only
   §1's table to change and the numbered headers left as stable
   historical anchors, that's a small, reversible edit to redo.
4. Add a new `## 16. Sprint 013 — architecture diagram and change
   summary` section, matching the convention §12-§15 already establish
   for recording each sprint's structural change (before/after layout,
   one paragraph — this sprint's own `sprint.md` Architecture section is
   the source, condensed here the way §15 condensed sprint 012's).

**`docs/design/*.md` changes**: `design.md` line 31 ("`src/` is flat, so
that one doc carries the logical subsystem breakdown as sections") and
its units-ladder table's `src/motion.ts`/`pose.ts`/`stop.ts`/`world.ts`/
`run.ts` mentions (line 59); `overview.md`'s "Shim + blocks" layer
description (lines 80-81, the six `.ts` files); `specification.md`
line 35's file list. Every mention of `src/firm/diffdrive/`, `src/firm/
control/...`, `src/tests/diffdrive/` in any of these docs refers to the
**upstream** `radio-robot` repository's own source tree, not this
repo's `src/` — leave those untouched; do not "fix" a path that was
never this repo's to begin with.

**`tools/` changes**: `tlm.py`'s two comment mentions of
`src/wire_adapter.cpp` (now `src/comms/wire_adapter.cpp`);
`make_deploy.py`'s two comment mentions of `src/wire_adapter.cpp`/
`src/wire_handler.cpp` in its triage-example docstring. Confirmed during
planning that `make_deploy.py` has no functional (non-comment)
dependency on any specific `src/` path — it copies whatever `pxt.json`'s
`files`/`testFiles` name, so no logic change is needed there, only these
comments.

**`tests/host/` prose sweep**: the docstrings/comments across
`tests/host/*.py` that cite a moved file's old bare path (e.g. "`src/
diffdrive.cpp`" -> "`src/core/diffdrive.cpp`", "`src/wire_adapter.cpp`"
-> "`src/comms/wire_adapter.cpp`") — mechanical string updates only, no
prose rewording beyond the path itself.

## Acceptance Criteria

- [x] `src/DESIGN.md`: opening "flat" claim corrected; §1 table's Files
      column shows directory-qualified names for every entry that moved;
      §2-§9 headings updated to match (or, if the stakeholder's answer to
      the Open Question in `sprint.md` says otherwise, left as
      historical anchors — confirm which before editing); new §16
      "Sprint 013" section added, matching §12-§15's established format.
- [x] `docs/design/design.md`, `docs/design/overview.md`,
      `docs/design/specification.md`: every mention of a bare `src/
      <filename>` path for one of the 30 moved files is updated to its
      new qualified path. Every mention of the upstream `radio-robot`
      repo's own `src/firm/...`/`src/tests/...` paths is confirmed
      untouched (these are not this repo's paths).
- [x] `tools/tlm.py`, `tools/make_deploy.py`: the four identified
      comment-only path mentions updated to their new qualified paths.
      No functional/logic change to either file.
- [x] `tests/host/*.py` docstrings/comments citing a moved file's old
      bare path are updated to the new qualified path (mechanical string
      substitution; no prose rewording).
- [x] Repo-wide grep verification: searching `tests/`, `tools/`, and
      `docs/design/` for a bare (unqualified) mention of any of the 30
      moved filenames finds nothing left unaccounted for, other than the
      confirmed-out-of-scope upstream `radio-robot` references. Record
      the exact grep command(s) used and their output in this ticket's
      completion notes.
- [x] `src/` contains exactly: `core/`, `motion/`, `platform/`,
      `comms/`, `blocks/`, `shims.cpp`, `DESIGN.md` — no other top-level
      entries.
- [x] Full `tests/host/` suite passes (this ticket's own scoped subset
      is "everything," since it touches prose across the whole
      directory — this does not replace `close_sprint`'s own full-suite
      gate, it is this ticket's own verification that its prose edits
      introduced no syntax errors in any docstring-adjacent code).
- [x] `uv run python tools/make_deploy.py` succeeds and produces a
      flashable hex from the fully reorganized tree.
- [x] `uv run python tools/make_deploy.py --testrig` succeeds and
      produces a flashable hex.
- [x] Completion notes record the final hex's location/size and confirm
      both builds' triage output shows no real compile error (only the
      documented benign V1/TS9200-class noise, if any).

## Completion Notes

**Job 1 — repo-wide stale-path sweep.**

Grep command used (per moved filename, scoped to `tests/`, `tools/`,
`docs/design/`, and `src/DESIGN.md`; the same sweep was also run
unscoped across the whole repo, excluding `node_modules/`,
`pxt_modules/`, `.git/`, `.tmp/`, `.claude/`):

```
for f in diffdrive.h diffdrive.cpp heading_wrap.h encoder_glitch_armor.h \
         motion_engine.h motion_engine.cpp platform_ports.h nezha_port.h \
         nezha_port.cpp otos_port.h otos_port.cpp encoder_pose_source.h \
         protocol.h protocol.cpp serial_transport.h serial_transport.cpp \
         radio_transport.h radio_transport.cpp wire_handler.h wire_handler.cpp \
         wire_adapter.h wire_adapter.cpp sim.ts run.ts pose.ts stop.ts \
         world.ts motion.ts; do
  grep -rn -F "src/$f" tests tools docs/design src/DESIGN.md
done
```

Fixed (mechanical `src/<old>` -> `src/<newdir>/<old>` substitution,
comment/prose only, no logic changes):

- `src/DESIGN.md`: opening claim (line 5), §1 table's Files column (11
  rows), §2-§9 headings (8 headings), new §16 added.
- `docs/design/design.md` line 31 (flat claim) and line 61 (units-ladder
  table's Blocks row).
- `docs/design/overview.md` lines 80-81 (Shim + blocks layer list).
- `docs/design/specification.md` line 35 (pxt.json files-array table).
- `tools/tlm.py` lines 77, 250 (`wire_adapter.cpp` -> `comms/wire_adapter.cpp`).
- `tools/make_deploy.py` lines 99-101 (`wire_adapter.cpp`/`wire_handler.cpp`
  triage-example docstring).
- `tests/host/*.py` (17 files): test_cxx11_syntax_gate.py,
  test_encoder_glitch_armor.py, test_heading_wrap.py,
  test_kernel_harness.py, test_motion_engine_gotow.py,
  test_motion_engine_primitives.py, test_motion_engine_reductions.py,
  test_motion_engine_settle.py, test_radio_transport_rx_capacity.py,
  test_regression_yaw_taper_pure_turn.py, test_wire_motion_completion.py,
  test_wire_motion_verbs.py, test_wire_per_transport_isolation.py, and
  the shim/syntax-check/fake `.cpp`/`.h` files that share this
  directory's comment style: wire_mock_adapter.h,
  wire_motion_verb_shim.cpp, radio_transport_rx_capacity_shim.cpp,
  motion_engine_shim.cpp, kernel_shim.cpp, heading_wrap_shim.cpp,
  heading_wrap_syntax_check.cpp, encoder_glitch_armor_shim.cpp,
  encoder_glitch_armor_syntax_check.cpp,
  encoder_pose_source_syntax_check.cpp, fake_ports.h, fake_pose_source.h
  — all comment-only, no `#include` line was ever stale (verified: no
  functional `#include "src/<old>..."` hit existed anywhere in the repo
  before this ticket started).
- `tests/host/README.md` (host-portable-C++ description line, and the
  literal `compile_shared_lib()` example command — copy-pasteable, so
  treated as functional-adjacent, not pure prose).
- `tests/host/DESIGN.md` (§3 "only portable sources compile here" list).

Deliberately left as HISTORICAL narrative (accurate at the time they
describe, predating this sprint's move; rewriting them would misrepresent
what was true when written):

- `src/DESIGN.md` §12-§15 (sprint 006/007/008/012 change-summary
  sections) — body text and their own file-location prose describe each
  sprint's state *at that sprint*; only §16 is new, §1's table and the
  §2-§9 headings (this sprint's "current state" surface) were the parts
  updated.
- `tests/host/test_pxt_manifest_completeness.py` lines 13-14 — recaps
  sprint 007 ticket 006's own historical manifest-omission defect, at
  paths accurate when that defect was found.
- `tests/host/test_wire_constants_drift.py` line 348 — narrates sprint
  012 ticket 002's `main.ts` -> `run.ts` move, accurate at that sprint.
- `tests/tools/test_make_deploy_triage.py` lines 65-66, 80 — verbatim
  captured real-compiler-output fixtures ("mirrors the confirmed
  Wire::Column defect... a real GCC diagnostic"); the triage logic under
  test parses diagnostic shape, not the path string, so these are pinned
  historical transcripts, not path assertions.
- `tools/DESIGN.md` line 110 — narrates a specific sprint 008 ticket 006
  verification session ("Verified against real builds, this session"),
  paths accurate then. (This file was flagged as a "known prose target"
  going in; on inspection its one hit is this historical narrative, not
  a current-layout claim — left unchanged.)
- `clasi/sprints/done/**`, `clasi/issues/*.md` (5 root-level open
  issues: finish-the-vevov-calibration-verification.md,
  travel-calib-is-2.8-percent-too-large.md,
  tour-corner-fixes-are-stale-cache.md,
  host-harness-masks-include-path-errors.md,
  gotoworld-overshoots-by-fixed-stopping-distance.md),
  `docs/code-review/2026-08-23/raw/*.md` (pinned to commit `46c40a8`,
  "every claim below was verified against the working tree at commit
  46c40a8") — all archived/historical narrative, out of this ticket's
  scope per its own historical-narrative exemption.
- `docs/design/{design,overview,specification}.md`'s remaining bare
  filename mentions with no literal `src/<name>` substring (e.g.
  `design.md`'s "`diffdrive.h/.cpp` is a vendored..." at line 185,
  `specification.md`'s "block-API modules (`sim.ts`, ...)" at lines
  71-78 and 763) — the ticket's Description named specific line numbers
  (31, 59/61, 35) for these three files; these additional bare mentions
  never wrote the literal `src/<name>` pattern the acceptance criterion
  and this sweep target, so were left matching the same "leave
  undirected body prose as-is" treatment already applied to
  `src/DESIGN.md` §2-9's own bodies. Flagged here per the ticket's "if
  unsure, leave it and list it" instruction.
- `tests/host/test_block_toolbox_order.py`, `test_motion_engine_deadline_boundary.py`
  — named as "known prose targets from ticket 005's grep" in this
  ticket's dispatch; on inspection neither contains an actual stale
  `src/<old-path>` reference (`test_motion_engine_deadline_boundary.py`'s
  three `src/shims.cpp` mentions are still correct — `shims.cpp` didn't
  move; `test_block_toolbox_order.py`'s `motion.ts`/`stop.ts`/`run.ts`/
  `main.ts` mentions were never written with a `src/` prefix at all, so
  there was nothing stale to mechanically fix without rewording prose,
  which is out of scope).

No functional (`#include`, manifest, or test-path-literal) stale
reference was found anywhere in the repo — ticket 004's finding (8
hidden refs behind a `_read(name)` helper) does not recur here; this
ticket's sweep was prose/comment-only throughout.

**Job 2 — reorganization verification.**

`git ls-tree -r HEAD --name-only -- src/`:

```
src/DESIGN.md
src/blocks/motion.ts
src/blocks/pose.ts
src/blocks/run.ts
src/blocks/sim.ts
src/blocks/stop.ts
src/blocks/world.ts
src/comms/protocol.cpp
src/comms/protocol.h
src/comms/radio_transport.cpp
src/comms/radio_transport.h
src/comms/serial_transport.cpp
src/comms/serial_transport.h
src/comms/wire_adapter.cpp
src/comms/wire_adapter.h
src/comms/wire_handler.cpp
src/comms/wire_handler.h
src/core/diffdrive.cpp
src/core/diffdrive.h
src/core/encoder_glitch_armor.h
src/core/heading_wrap.h
src/motion/motion_engine.cpp
src/motion/motion_engine.h
src/platform/encoder_pose_source.h
src/platform/nezha_port.cpp
src/platform/nezha_port.h
src/platform/otos_port.cpp
src/platform/otos_port.h
src/platform/platform_ports.h
src/shims.cpp
```

Exactly `core/`, `motion/`, `platform/`, `comms/`, `blocks/`,
`shims.cpp`, `DESIGN.md` at the top level — no stray root-level
`.h`/`.cpp`/`.ts`, no duplicates.

`pxt.json`'s `files[]` (26 `src/`-prefixed entries + `README.md`) was
diffed by hand against the on-disk tree above and matches exactly, one
entry per file, `sim.ts` before `motion.ts` preserved. `tsconfig.json`'s
`files[]` six `.ts` entries match `pxt.json`'s order (`sim.ts, run.ts,
pose.ts, stop.ts, world.ts, motion.ts`).
`uv run pytest tests/host/test_pxt_manifest_completeness.py -q` -> `2
passed` — confirmed genuinely recursive (`_SRC_DIR.rglob("*")`, not a
flat `iterdir()`), not silently skipping subdirectories.

**Job 3 — final build + flashable hex.**

Both `.tmp/deploy-head/built/mbcodal-binary.hex` and
`.tmp/deploy-testrig/built/mbcodal-binary.hex` were removed before each
respective build; both builds completed on attempt 1 with the
documented-benign V1 `srec_cat` hex-merge ("contradictory ... value")
plus an unrelated `TS9200` (`Cannot read properties of null (reading
'hex')`, a pxt-core JS caching `TypeError` on `fillExtInfoAsync`) —
neither build showed any `.cpp` failing to compile; every one of the 30
moved/reorganized `src/` files (core/diffdrive.cpp, motion/motion_engine.cpp,
platform/nezha_port.cpp, platform/otos_port.cpp, comms/wire_handler.cpp,
comms/wire_adapter.cpp, comms/radio_transport.cpp, comms/serial_transport.cpp,
comms/protocol.cpp, shims.cpp) compiled cleanly (only pre-existing,
unrelated PXT-core warnings: sign-compare in nezha_port.cpp:305,
unused-function in core/serial.cpp, no-return in core/music.cpp).

- Primary hex: `.tmp/deploy-head/built/mbcodal-binary.hex`, 1,400,201
  bytes, mtime fresh (post-removal), sha256
  `59a668da89bafa24311fcc70596d6c6cebacdc54f19fddb3ce51f241ef9692fe`.
- Testrig hex: `.tmp/deploy-testrig/built/mbcodal-binary.hex`,
  1,377,386 bytes, mtime fresh (post-removal), sha256
  `8557de980685e0559a75d5f7576f6bb76584b2c4151352f3d9c2fbb03aec72ca`.

`uv run pytest tests/host/ -q` -> `447 passed` (this ticket's own scoped
verification, run before the builds).
`uv run pytest -q` (full suite) -> `597 passed` — matches the sprint's
stated baseline exactly.

**Hand-off: unverified on hardware.** Nobody has flashed a post-reorg
hex to a robot. This build proves the fully reorganized tree compiles
and links cleanly through both the primary and testrig variants; it does
NOT prove the device boots. The specific exposure `src/DESIGN.md` §16
now documents: `src/blocks/motion.ts` has a top-level `_startProtocol()`
call that needs `src/blocks/sim.ts` loaded first, and PXT compiles in
manifest order. Ticket 005 preserved `sim.ts, run.ts, pose.ts, stop.ts,
world.ts, motion.ts` order in both `pxt.json` and `tsconfig.json`, and
this ticket confirmed that order is still intact in both manifests — but
a load-order fault produces a hex that builds perfectly clean and is
dead on device (this project has shipped exactly that class before:
`disablesVariants: ["mbdal"]`). Boot verification on real hardware is
the team-lead's next step, not something this ticket or this sprint
claims.

## Implementation Plan

**Approach**: prose sweep first (docs, `src/DESIGN.md`, `tools/`
comments, `tests/host/` docstrings), verified by repo-wide grep, then
the two full-scope builds last (this ticket's authoritative evidence
that the sprint's success criteria are met end to end).

**Files to create**: none.

**Files to modify**: `src/DESIGN.md`, `docs/design/design.md`,
`docs/design/overview.md`, `docs/design/specification.md`,
`tools/tlm.py`, `tools/make_deploy.py`, and whichever `tests/host/*.py`
files the grep in Acceptance Criteria finds still citing an old bare
path.

**Testing plan**: full `tests/host/` suite (this ticket's own scope
covers the whole directory's prose, so its own verification matches),
then `make_deploy.py` and `make_deploy.py --testrig` as the sprint's
final, authoritative confirmation of `sprint.md`'s Success Criteria.

**Documentation updates**: this ticket *is* the documentation-update
ticket — see Description above for the full list.

## Testing

- **Existing tests to run**: `uv run pytest tests/host/` (full
  directory — this ticket's prose sweep spans it)
- **New tests to write**: none — documentation and prose accuracy only.
- **Verification command**: the pytest command above, then
  `uv run python tools/make_deploy.py` and
  `uv run python tools/make_deploy.py --testrig`, plus the repo-wide
  grep verification named in Acceptance Criteria.
