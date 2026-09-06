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

## Relationship to sprint 029 and sprint 031

Sprint 029's acceptance session (`reports/bench-acceptance-029-20260904d.md`)
measured the same quantities on tovez with its own scripts
(`captures/bench-acceptance-029-20260904d/*.py`) as six named gates,
G1 through G6 (rest-heading accuracy, endpoint position, leg length,
first-tick tracking, tracking overshoot, square closure vs. baseline).

**Sprint 031 folds those six gates into `turn_calibration.py` as named
modes**, so there is one calibration/acceptance program instead of a
family of one-off scripts — the standalone `g1`-`g6` scripts under
`captures/bench-acceptance-029-20260904d/` are retired (or reduced to
thin wrappers where a still-cited capture path names one directly).

**Sprint 031 also restates G1 and G2**, the two bars the camera's own
noise floor could not resolve as originally set: camera heading noise
at rest measures sd 1.03°/sample (0.65° on a difference of 5-sample
means) and position repeatability is several mm — both already exceed
the original 0.4° (G1) and 5 mm (G2) bars before the drivetrain enters
into it at all. Restated:

- **G1** (rest-heading accuracy): mean|err| ≤ 1.0°, sd ≤ 1.0°, with
  ≥ 20-sample averaged fixes (up from single-sample fixes).
- **G2** (endpoint position): ≤ 10 mm.
- G3 (leg length), G4 (first-tick tracking), G5 (tracking overshoot),
  and G6 (square closure vs. baseline) are unchanged.

This is a floor set by today's instrument, not by the drivetrain's true
capability — a future fixture improvement (a larger tag, two tags, more
samples per fix) should re-tighten these bars rather than treat them as
permanent. See
`clasi/sprints/031-drivetrain-tuning-and-gate-acceptance-on-tovez/sprint.md`'s
Design Rationale for the full argument.

### Implementation (ticket 007)

`turn_calibration.py` gained `--mode {sweep,g1,g2,g3,g5,g6}` (default
`sweep`, the pre-existing pivot sweep, unchanged). G4 reports alongside
G3 (`--mode g3`), since sprint 029's `g3_run.py` already measured both
from the same telemetry in one script — no separate mode for it. Each
gate mode is one `run_gN()` drive function built on two new
camera/telemetry primitives, `one_leg()` and `one_arc()` (the
straight-line and arc analogues of the pre-existing `one_turn()`), plus
a shared `_wait_done()` completion-poll and `_enable_tlm_full()`
telemetry-setup helper factored out of the sweep's own code. Every
gate's scoring is a small pure function (`g1_score`, `g2_score`,
`arc_expected_endpoint_mm`, `arc_path_points`, `leg_metrics`,
`fit_wheel_lag`, `square_closure_ok`) with no Link/Camera dependency,
unit-tested in `tests/playfield/test_turn_calibration_gates.py` (27
cases: bar constants, scoring boundaries, arc geometry, synthetic-frame
metrics, lag-fit recovery, the completion-poll, and the camera
noise-floor calculation G1's bar is sized against). The sprint 029
standalone scripts (`captures/bench-acceptance-029-20260904d/g*.py`,
`lag_measure.py`) are retired as of this ticket — their captured
outputs remain as citations, but ticket 016 (Session C) runs the
consolidated program, not those scripts.

Each gate mode repeats the mandatory pre-flight path check
(`.claude/rules/playfield-testing.md`) from a measured start pose
before arming a commanded move — `tools/field.py`'s `check_path()` for
every translating mode (g2/g3/g5/g6), a new `arc_path_points()` for g2
so a curved leg's projected path (which bows past its own chord) is
checked, not just its endpoint. This could not be verified end-to-end
without a robot; what ticket 007 could and did verify: every mode's
pure scoring logic (above), and that each mode fails loudly rather
than hanging or silently no-op'ing on a missing precondition (an
unknown robot name errors out of argparse immediately; a bad host/port
raises rather than blocking) — confirmed by hand, not by pytest, since
it requires actually invoking `main()`.
