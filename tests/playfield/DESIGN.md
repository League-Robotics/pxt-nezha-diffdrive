# tests/playfield — camera-scored calibration programs on the field

**Owner:** Eric Busboom · **Last reviewed:** 2026-09-04 · **Status:**
experimental (written 2026-09-03 on master, outside sprint 029; this
document added at sprint 029's close, which found the directory
without one)

Not unit tests: these are on-robot measurement programs that need the
playfield, the overhead camera and a live carrier, and they write
their results under `reports/`. They live under `tests/` because each
one is an acceptance of a calibration claim, run by a person, with the
camera as the instrument. `pytest` does not collect them (no `test_`
prefix).

## Programs

- **`turn_calibration.py`** — pivots of ±90, ±107 and ±180 deg, many
  repeats, with wheel speeds recorded through telemetry, then charts.
  Per turn: a rest fix from the camera, the pivot, a rest fix after,
  the encoder's own belief, so the camera/encoder ratio and the
  per-direction offset fall out (`rotational_slip`, and the
  `rotation_gain_pos/neg` / `rotation_offset` pair radio-robot-lib's
  robot configs carry). `--dance` runs the pre-flight first
  (`.claude/rules/field-dance-first.md`); `--radio` and `--compare`
  (2026-09-04) drive over the relay and chart two robots side by side;
  `--render` re-draws from a saved run under the plotting venv. Results
  so far: tigez 2026-09-03 (`reports/tigez-turn-cal-20260903`, slip
  0.9617, overrun 5.5 mm at default cruise), gopiv/tigez/vevov
  2026-09-04 (`reports/` pivot over-rotation across drivetrains).

## Conventions

- Heading comes from the camera with the fixed +90 deg front-edge
  convention (`.claude/rules/tag-yaw-is-the-front-edge-not-the-hat.md`);
  `--heading-offset` exists only for the sub-degree physical residual.
- Sample heading at REST, never windowed across a move (the windowing
  reverses the sign of the pivot error; project memory
  `odometry-closure-tuning-knobs`).
- Every number a program prints that a config later carries must cite
  the run directory (`.claude/rules/measurement-citations.md`).

## Relationship to sprint 029

Sprint 029's acceptance session (`reports/bench-acceptance-029-20260904d.md`)
measured the same quantities on tovez with its own scripts
(`captures/bench-acceptance-029-20260904d/*.py`); the two should
converge on `turn_calibration.py` as the one calibration program, with
the sprint's `lag`/`stop_distance` measurements folded in as modes.
That is part of the tovez drivetrain tuning issue
(`clasi/issues/tovez-drivetrain-tuning-and-restated-acceptance-bars.md`).
