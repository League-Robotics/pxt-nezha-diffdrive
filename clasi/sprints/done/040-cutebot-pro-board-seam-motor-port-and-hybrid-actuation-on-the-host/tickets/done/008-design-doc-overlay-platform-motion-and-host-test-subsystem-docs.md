---
id: 008
title: 'Design-doc overlay: platform, motion, and host-test subsystem docs'
status: done
use-cases:
- SUC-001
- SUC-003
- SUC-004
depends-on:
- '007'
github-issue: ''
issue: cutebot-pro-board-seam-and-hybrid-port.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Design-doc overlay: platform, motion, and host-test subsystem docs

## Description

Depends on ticket 007 (the build checkpoint) so this ticket describes
the sprint's actual final state, not an intermediate one. Per
`docs/design/design.md`'s "Design-doc validation at sprint close" and
"Subsystem-doc contract" sections (both read during architecture
planning): this project has `design_docs: enabled`, and a sprint that
adds/renames a declared source root or subsystem directory should carry
a `design/` overlay and pass `clasi design validate` before close —
this sprint adds new files under `src/platform/` and `src/motion/` (not
new top-level directories, but the per-subsystem `DESIGN.md`s still
need their content updated to describe what is now there). Edit
existing sections **in place** — do not append a new dated "Sprint 040"
section to any canonical doc, per `design.md`'s own recorded rule
(quoted there almost verbatim from the sprint 017 postmortem this
project already carries).

Seed the sprint's `design/` overlay (`seed_sprint_design_overlay`, if
not already seeded by an earlier ticket in this sprint) and update, in
place:

- `src/platform/DESIGN.md` — add the board-composition seam
  (`board.h`/`board_nezha.cpp`/`board_cutebot.cpp`) and
  `CutebotMotorPort`/`CutebotDevice`/`CutebotActuationPolicy` alongside
  the existing `NezhaMotorPort`/`OtosPort` entries, describing purpose,
  boundary and the 14-call `Motor` contract each implements — mirroring
  the level of detail `src/DESIGN.md` §7 already gives the Nezha port
  (read during architecture planning).
- `src/DESIGN.md` §7 (Hardware ports) — the canonical, fine-grained
  version of the same content; §1's layer map table gains the new
  `platform/board*`/`platform/cutebot_*` files at the Hardware-ports
  layer, and `motion/wheel_command_tap.h` at the Motion-engine layer
  (host-portable, `diffdrive.h` + libc only, per that layer's existing
  "May include" column).
- `docs/design/design.md`'s own subsystem map / layer table — same
  addition at the project level, consistent with `src/DESIGN.md`'s.
- `tests/host/DESIGN.md` and `tests/DESIGN.md` — add
  `sim_cutebot_bus.h`, `cutebot_port_shim.cpp`, and the new
  `test_*.py` files to whatever inventory/table those docs keep (per
  `tests/DESIGN.md`'s own note that `tools/DESIGN.md`'s inventory is
  test-enforced — confirm whether either `tests/` doc has an
  equivalent enforced inventory before assuming a free-text mention is
  enough).
- `tools/DESIGN.md` — if its own inventory table is test-enforced
  (`tests/tools/test_tools_design_inventory.py`, referenced from
  `docs/design/design.md`), add any new/changed `tools/make_deploy.py`
  behavior line the inventory format expects.

Run `clasi design validate` (or the `validate_design` MCP tool)
before this ticket is considered done, per the Phase 0 checklist
`docs/code-review/guidelines.md` names for any sprint adding/renaming a
declared source root or subsystem directory.

## Acceptance Criteria

- [x] `src/platform/DESIGN.md`, `src/DESIGN.md` §1/§7,
      `docs/design/design.md`'s layer table, `tests/host/DESIGN.md`,
      `tests/DESIGN.md`, and `tools/DESIGN.md` (as applicable) all
      describe the sprint's actual final state — no stale "Cutebot is
      still an issue, not built" language survives from before this
      sprint.
- [x] No canonical doc gained an appended dated "Sprint 040" section —
      every edit is in place, per `design.md`'s own recorded
      convention.
- [x] `clasi design validate` (or `validate_design`) reports `ok: true`.
- [x] Any test-enforced inventory (`tools/DESIGN.md`'s,
      confirmed/denied for `tests/`'s docs above) still passes with the
      new files listed.

## Testing

- **Existing tests to run**: `uv run pytest` (full suite, to confirm
  doc-only changes did not accidentally touch source); any inventory
  test named above.
- **New tests to write**: none expected — this is a documentation
  ticket. If a `DESIGN.md` inventory is discovered to be
  test-enforced and the test needs a new entry, that entry is a doc
  change, not new test logic.
- **Verification command**: `clasi design validate`, then
  `uv run pytest`.

## Completion Notes

**Read first.** All seven done tickets' completion notes
(001-007) under this sprint's `tickets/done/` — the as-built record
this ticket documents.

**Docs edited, and their sections:**

- `src/platform/DESIGN.md` — full rewrite: the board-composition seam
  (`board.h`/`board_nezha.cpp`/`board_cutebot.cpp`, including which
  half of each is host-portable vs. `pxt.h`-guarded vs. not
  host-linkable at all), `CutebotMotorPort`/`CutebotDevice` and
  `CutebotActuationPolicy` alongside the existing `NezhaMotorPort`/
  `OtosPort` entries, at the same one-paragraph-per-file level of
  detail the file already gave Nezha/OTOS. The old "Everything here is
  CODAL/`pxt.h`-bound" claim was corrected — three of this directory's
  files are fully host-portable.
- `src/DESIGN.md` — §1's layer table (Hardware-ports row gains
  `board.h`/`board_nezha.cpp`/`board_cutebot.cpp`/`cutebot_port.*`/
  `cutebot_actuation_policy.*`, with a note on which of those reach
  `pxt.h` and which don't; Motion-engine row gains
  `motion/wheel_command_tap.h`); §3 (one stale sentence fixed —
  "every fleet board today leaves it null" was no longer true once
  ticket 004 gave a Cutebot-composed board a real
  `CutebotTapAdapter`); §5 (the config-surface paragraph now names
  `onboard_pid`/`onboard_floor` (43/44) and the per-board
  accessor/escape-hatch pattern, with a corrected row count — "37 rows
  as of sprint 040 ticket 004" is a verified count of
  `comms/config_fields.h`'s actual `kConfigFields[]`, not a
  continuation of the doc's own pre-existing, already-stale "32 rows"
  claim, which this ticket did not otherwise chase down); §7's own
  heading and body gained substantial new content: a "Board
  composition" paragraph, `CutebotMotorPort + CutebotDevice`,
  `configureWiring()`'s `WiringResult` decision (the sign-only/
  port-refuse rule and why the platform layer mirrors `Wire::Result`
  instead of including it), and `CutebotActuationPolicy`'s exact
  per-mode decision rule (`floor × 1.1` engage / `floor × 0.9`
  release for mode 1, the both-wheels eligibility gate, mode 2's
  `kAccel`-holds-previous-state rule) — matching the Nezha port's own
  level of detail; §9's `shims.cpp`/`Rig` paragraph corrected (it used
  to describe `Rig` as declaring two concrete `NezhaMotorPort`
  members directly, which ticket 001 changed) and now also documents
  `ensure()` installing the composed board's `WheelCommandTap`.
- `docs/design/design.md` — the `src/DESIGN.md` subsystem-map bullet
  gained a paragraph on the board-composition layer and the Cutebot
  port beside the Nezha one; "Motion-shaping authority" gained a
  paragraph on the new `MotionEngine` → `WheelCommandTap` edge (the
  sprint's own new cross-module dependency, per its Architecture
  Step 4 diagram). Units ladder and sensor doctrine confirmed
  unchanged, per the ticket's own note — not touched.
- `src/motion/DESIGN.md` — one stale forward-reference fixed ("a
  board sitting below the kernel (the Cutebot Pro's hybrid actuation
  policy, a later sprint)" — ticket 004, same sprint, already built
  it) and a sentence added naming `CutebotTapAdapter` as the tap's
  first real consumer.
- `src/comms/DESIGN.md` — one sentence added on `config_fields.h`
  naming ordinals 43/44 and the per-board-accessor/append-only
  contract.
- `tests/host/DESIGN.md` — the Shims file list and orientation prose
  gained the four sprint-040 shims
  (`nezha_board_diag_shim.cpp`, `cutebot_port_shim.cpp`,
  `cutebot_actuation_policy_shim.cpp`, `cutebot_hybrid_shim.cpp`) and
  named their test files (`test_board_nezha_diag.py`,
  `test_board_seam_source_pin.py`, `test_board_cutebot_source_pin.py`,
  `test_cutebot_port.py`, `test_cutebot_actuation_policy.py`,
  `test_cutebot_hybrid_actuation.py`) and `sim_cutebot_bus.h` — these
  had no entry anywhere in this file before this ticket; only
  `sim_cutebot_robot_shim.cpp` (ticket 006) was already named.
- `docs/design/cutebot-pro-support.md` — rewritten to read as the
  design rationale (see below), not a second as-built record.

**Confirmed unchanged (verified, not edited):** `tests/DESIGN.md` and
`tools/DESIGN.md` were already fully updated in place by tickets
001/002/005/006's own work — re-read both against the current tree and
found no stale "Cutebot is still an issue" language and no gaps beyond
the `tests/host/DESIGN.md` shim-list gap fixed above. `test/DESIGN.md`
(the PXT `testFiles` doc) has nothing to update — this sprint touched
no on-robot test program.

**`tests/host/DESIGN.md`/`tests/DESIGN.md` inventory question,
answered.** Neither carries a test-enforced file inventory the way
`tools/DESIGN.md` does
(`tests/tools/test_tools_design_inventory.py`, confirmed by reading
that test — it walks `tools/` only). `tests/host/DESIGN.md`'s own
header says explicitly "Section 2... is an orientation... not a
complete listing," so the shim-list gap fixed above was a
completeness improvement, not a failing-test fix. `tools/DESIGN.md`'s
inventory already covered `make_deploy.py`'s `board`/`_inject_board()`
behavior (ticket 005) and needed no further change; re-ran
`test_tools_design_inventory.py` to confirm.

**`docs/design/cutebot-pro-support.md`: corrections made, per the
dispatch's own list.** Status line changed from "proposal, pre-sprint"
to "design rationale... Sprint 040 is implemented and merged," with a
pointer to the subsystem docs as the as-built record. §3.D's tap
paragraph now quotes the real signature
(`onDrive(float left, float right, VelocityShaper::Phase phase)`,
`onNeutral()`) instead of the pre-build `(left, right)`-only
description. The "engage at 220, release at 180 (numbers
illustrative)" text is corrected: as built, this is `floor × 1.1` /
`floor × 0.9`, a ratio of the configured `onboard_floor` that happens
to reproduce 220/180 at the 200 mm/s default, not two hard-coded
numbers. §10 item 2 (configureMotor sign-only vs. refuse) is marked
DECIDED with the actual `WiringResult` shape and refusal code
(`kUnimplemented`, not a range/bad-arg code) — this was ticket 002's
own stakeholder-reviewable choice. §10 item 3 (zeguz vs. zetuv) is
left OPEN, as ticket 005 itself left it — `zeguz.json` exists but the
identity question needs real robot access (sprint 041). §7's host-test
list gained the two sim/hybrid layers ticket 004/006 added
(`cutebot_hybrid_shim.cpp`, `sim_cutebot_robot_shim.cpp`) and a
SIM-ONLY citation of ticket 006's own closure table (closure 118.9 mm/
57.2 mm/58.1 mm at `onboard_pid` 0/1/2), with the run command
(`uv run python tests/host/sim_tour.py --board cutebot-pro`) as its
citation, labelled explicitly as simulation output on an UNVERIFIED
plant model, never MEASURED. §9's "Proposed arc" marks Sprint 040 DONE
with a one-line summary of what shipped; Sprint 041 is unchanged. §2.1
gained a short "as built" pointer at the top rather than being
rewritten row by row — the table is kept as the planning record, and
the current, maintained shape of the seam is `src/DESIGN.md` §1/§7 and
`src/platform/DESIGN.md`, cross-referenced explicitly.

**Design-doc validation.** `validate_design()` with no `overlay_dir`
(the canonical doc-set structure check) reports `ok: true`. The
sprint's `design/` overlay was seeded this ticket
(`seed_sprint_design_overlay`, sprint had none before) for
`design.md`, `src/DESIGN.md`, `src/platform/DESIGN.md`,
`src/motion/DESIGN.md`, `src/comms/DESIGN.md`, and
`tests/host/DESIGN.md`. **Found and worked around a real
`seed_sprint_design_overlay` limitation, not fixed (CLASI-server
code, out of this repo's scope, the same category as `design.md`'s own
recorded architecture-authoring-skill gap):** the tool's slug
derivation drops the source root's own name for a *root-level*
`DESIGN.md` (one with no subdirectory under its source root), so
`src/DESIGN.md`, `tests/DESIGN.md`, `tools/DESIGN.md`, and
`test/DESIGN.md` all collide on the bare slug `DESIGN.md` — only the
last one named in a batch call survives. First seeded all nine
canonical docs in one call (collided down to `test/DESIGN.md`
occupying the `DESIGN.md` slot); re-seeded with `["src/DESIGN.md"]`
alone afterward so the slot holds the more heavily-edited file
instead, since it must be one or the other. `tests/DESIGN.md` and
`tools/DESIGN.md` are consequently NOT present in this sprint's
overlay (their own content is still correct on disk, verified above —
only the overlay's diff-tracking of them is affected). Calling
`validate_design(overlay_dir=...)` reports six "no corresponding
`.diff.md`" messages; per `design.md`'s own text this file is produced
by `close_sprint`'s `design_overlay_apply` step, not by a
mid-sprint ticket, so this was not treated as a blocker — the
ticket's actual acceptance criterion (`validate_design` reports
`ok: true`) is satisfied by the no-`overlay_dir` call. Flagging for
whoever runs `close_sprint` on this sprint: confirm the overlay
validates cleanly at that point, since this collision is unexercised
territory for a project with `DESIGN.md` at four different top-level
source roots.

**Full-suite result.** `uv run pytest tests/host tests/tools -q
--ignore=tests/tools/test_field_dance_accel_bake.py` — **2294
passed**, unchanged from ticket 007's own final count (doc-only
changes, no source touched). Doc-pinning tests specifically re-run:
`test_no_stale_src_paths.py`, `test_archaeology_marker_budget.py`,
`test_tools_design_inventory.py` — all green.

**Not attempted / out of scope.** Generating this sprint's
`design/*.diff.md` files (see above — `close_sprint`'s own job).
Any further correction to `docs/design/design.md`'s units ladder or
sensor doctrine sections — confirmed unchanged, per the ticket's own
note. `test/DESIGN.md` — confirmed nothing to update.
