---
id: '043'
title: Position-move hardware acceptance on zuvat and the kernel defaults
status: executing
branch: sprint/043-position-move-hardware-acceptance-on-zuvat-and-the-kernel-defaults
use-cases: []
issues:
- position-move-hardware-acceptance-and-the-zuvat-square.md
- kernel-defaults-from-the-fifty-cm-evidence.md
- remove-the-run-brick-scaffolding.md
- position-mode-default-and-docs-after-acceptance.md
- fine-velocity-actuator-behind-a-speed-path-switch.md
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sprint 043: Position-move hardware acceptance on zuvat and the kernel defaults

## Goals

Implement change-plan.md section 3 (C13 to C20): prove the sprint 042 position-move work on hardware and settle the defaults.

- Bench 50 cm stops on the one-wheel micro:bit rig.
- Zuvat (two motors, no camera; nolanet node loki): pivots and the square tour, with the closure metric and wheel speed curves, at `position_mode` 0 and 1.
- Stop timing, arcs.
- The `speed_path` A/B (the hardware half of the fine-velocity issue; the switch itself landed in 042 per D2, default 0).
- Kernel defaults from the fifty-cm evidence.
- Remove the run-brick scaffolding.
- Flip the position-mode default, update docs, and write the postmortem.

## Scope

### In Scope
- C13 to C20 of change-plan.md section 3.
- Hardware: local one-wheel micro:bit bench rig; robot zuvat on nolanet node loki.

### Out of Scope
- New host features (all in sprint 042).
- Any new host feature; the only code changes are baked defaults, tooling, and removal of test scaffolding.

## Issues
- position-move-hardware-acceptance-and-the-zuvat-square.md
- kernel-defaults-from-the-fifty-cm-evidence.md
- remove-the-run-brick-scaffolding.md
- position-mode-default-and-docs-after-acceptance.md
- fine-velocity-actuator-behind-a-speed-path-switch.md (hardware A/B half)

## Dependencies
Depends on sprint 042 (host work must be complete and green). The defaults flip and scaffolding removal are gated on the acceptance results.

Sources: `docs/code-review/2026-10-27/change-plan.md`, `docs/code-review/2026-10-27/motor-path-review.md` (section 8).

## Architecture

Compact (borderline trivial): no new module, no cross-module dependency, no
data-model change. Work is measurement, baked defaults and tooling.

**What changed.** (1) `tools/mb50.py` is ported into this repo with a
`--mode position`; a closure-metrics helper joins `tour_capture.py` /
`tour_chart.py`. (2) Per-robot kernel constants and the `position_mode` /
`speed_path` defaults in `src/comms/config_fields.h` and
`radio-robot-lib/config/robots/*.json` change value, with a capture citation
beside each. (3) `RUN brick*` raw-I2C probes are deleted from `test/test.ts`.

**Why.** Sprint 042 shipped the position-move path host-tested only; nothing
has run on hardware. Defaults may change only on measured evidence
(`.claude/rules/measurement-citations.md`).

**Impact.** Default flips change student-visible move behavior; the host
suite's default-pinning tests are updated in the same commit. Zuvat has no
camera or OTOS: all closure numbers are encoder truth and are labelled so.

**Migration.** None. Defaults are live-settable (`SET position_mode`), so
an accepted-mode failure is reverted by one constant.

**Design overlay.** `src/comms/DESIGN.md` (defaults) and `tools/DESIGN.md`
(bench and closure tooling) only. Architecture review: self-review passed,
recorded as passed (single-concern tooling and value changes).

## Use Cases

- SUC-001: Stakeholder sees how closely a two-motor square tour closes, per
  position mode, with the wheel speed curves.
- SUC-002: Developer runs a repeatable bench 50 cm stop and gets mm-level
  error per trial with the path confirmed.
- SUC-003: A robot stops promptly on STOP/ESTOP/watchdog during a built-in move.
- SUC-004: Students get defaults (move mode, kernel constants) that were
  chosen on measured evidence, with the evidence in-tree.

## Hardware rules for every hardware ticket

- Keep runs short; send STOP between runs; never send brick opcode 0x1D.
- Evidence lands under `captures/zuvat-position-<date>/` (bench:
  `captures/bench-position-<date>/`): hex, CSVs, PNGs, `notes.md`.
- If a bar is missed: record the number and the capture, do NOT tune
  silently; set the ticket to done with a "bar not met" note and tell the
  team-lead.
- Zuvat: no camera, so camera steps in the field rules do not apply.

## Tickets

| # | Title | depends-on |
| --- | --- | --- |
| 001 | Bench tool and 50 cm acceptance | none |
| 002 | Zuvat bring-up, wire smoke, stop timing | none |
| 003 | Zuvat pivots and two-wheel start skew | 002 |
| 004 | Zuvat square tour closure and speed curves | 002, 003 |
| 005 | Arcs: position_mode 2 vs kernel | 004 |
| 006 | speed_path A/B | 001, 002 |
| 007 | Kernel defaults baked from the evidence | 001, 004, 006 |
| 008 | Remove RUN brick scaffolding | 001, 002 |
| 009 | Flip defaults, docs, postmortem | 004, 005, 006, 007, 008 |
