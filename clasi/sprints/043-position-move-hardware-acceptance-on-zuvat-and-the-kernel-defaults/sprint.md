---
id: '043'
title: Position-move hardware acceptance on zuvat and the kernel defaults
status: roadmap
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
- Architecture, use cases and tickets are produced when this sprint is detailed.

## Issues
- position-move-hardware-acceptance-and-the-zuvat-square.md
- kernel-defaults-from-the-fifty-cm-evidence.md
- remove-the-run-brick-scaffolding.md
- position-mode-default-and-docs-after-acceptance.md
- fine-velocity-actuator-behind-a-speed-path-switch.md (hardware A/B half)

## Dependencies
Depends on sprint 042 (host work must be complete and green). The defaults flip and scaffolding removal are gated on the acceptance results.

Sources: `docs/code-review/2026-10-27/change-plan.md`, `docs/code-review/2026-10-27/motor-path-review.md` (section 8).
