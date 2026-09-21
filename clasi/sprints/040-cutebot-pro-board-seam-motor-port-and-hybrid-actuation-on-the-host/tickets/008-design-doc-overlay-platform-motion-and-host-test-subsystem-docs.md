---
id: 008
title: 'Design-doc overlay: platform, motion, and host-test subsystem docs'
status: open
use-cases: ["SUC-001", "SUC-003", "SUC-004"]
depends-on: ["007"]
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

- [ ] `src/platform/DESIGN.md`, `src/DESIGN.md` §1/§7,
      `docs/design/design.md`'s layer table, `tests/host/DESIGN.md`,
      `tests/DESIGN.md`, and `tools/DESIGN.md` (as applicable) all
      describe the sprint's actual final state — no stale "Cutebot is
      still an issue, not built" language survives from before this
      sprint.
- [ ] No canonical doc gained an appended dated "Sprint 040" section —
      every edit is in place, per `design.md`'s own recorded
      convention.
- [ ] `clasi design validate` (or `validate_design`) reports `ok: true`.
- [ ] Any test-enforced inventory (`tools/DESIGN.md`'s,
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
