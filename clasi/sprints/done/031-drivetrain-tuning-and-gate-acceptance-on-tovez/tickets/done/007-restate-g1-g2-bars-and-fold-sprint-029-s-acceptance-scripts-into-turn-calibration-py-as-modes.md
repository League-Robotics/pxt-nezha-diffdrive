---
id: '007'
title: Restate G1/G2 bars and fold sprint 029's acceptance scripts into turn_calibration.py
  as modes
status: done
use-cases:
- SUC-005
- SUC-007
depends-on: []
github-issue: ''
issue: tovez-drivetrain-tuning-and-restated-acceptance-bars.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Restate G1/G2 bars and fold sprint 029's acceptance scripts into turn_calibration.py as modes

**Type: (b) desk work — programmer. No hardware; this ticket prepares
the tooling Session C (ticket 016) will run against.**

## Description

Camera heading noise at rest is sd 1.03°/sample (0.65° on a difference
of 5-sample means) and position repeatability is several mm
(`g1-run.log` line 1) — below G1's 0.4° sd and G2's 5 mm bars as
originally set. Per this sprint's Design Rationale, restate:

- **G1**: mean|err| ≤ 1.0°, sd ≤ 1.0°, with ≥ 20-sample averaged fixes.
- **G2**: endpoint ≤ 10 mm.
- Keep G3 (length), G4 (first-tick), G5 (tracking), G6 (closure vs.
  baseline) unchanged.

Separately, fold sprint 029's ad hoc acceptance scripts (the `g1`
through `g6` style captures used in
`reports/bench-acceptance-029-20260904d.md`) into
`tests/playfield/turn_calibration.py` as named, reusable modes, so
there is one calibration/acceptance program instead of a family of
one-off scripts. Retire the standalone scripts, or reduce them to thin
wrappers if an existing capture path still cites one by name.

## Acceptance Criteria

- [x] `tests/playfield/turn_calibration.py` documents the restated
      G1/G2 bars (with a comment or docstring citing this sprint's
      Design Rationale for why they moved).
- [x] Every sprint 029 acceptance behavior (G1 through G6) is reachable
      as a `turn_calibration.py` mode, verified by running each mode
      once in a dry-run/host-simulated form if the harness supports it,
      or documented as hardware-only otherwise.
- [x] `tests/playfield/DESIGN.md` (or the seeded sprint design overlay)
      reflects the consolidated program.
- [x] Session C (ticket 016) is written to use the consolidated
      program, not the original standalone g1-g6 scripts.

## Testing

- **Existing tests to run**: `tests/playfield/` and `tests/tools/`
  suites covering the pre-existing scripts being folded in.
- **New tests to write**: any host-testable portion of each mode's
  logic (bar comparison, capture parsing) gets a unit test; the
  on-robot drive logic itself is exercised in Session C, not here.
- **Verification command**: `uv run pytest tests/playfield/ tests/tools/`
