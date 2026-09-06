# tests/calibration — the on-robot calibration programs

**Owner:** Eric Busboom · **Last reviewed:** 2026-09-05 · **Status:**
active (consolidated here 2026-09-05 from `tests/playfield/` and
`tools/field_dance.py` at the stakeholder's direction: "a small number
of solid tests we're going to use for testing and calibration".
`tests/playfield/DESIGN.md` -- written at sprint 029's close and
extended by sprint 031 -- was folded into this document at the same
time; the "Conventions" and "Gate modes" sections below are its
content, with paths updated to this directory.)

Not unit tests: on-robot measurement programs that need a playfield,
its overhead camera and a live carrier, run by a person, with the
camera as the instrument. They write under `reports/`. `pytest` does
not collect them (no `test_` prefix).

## Entry point

`calibrate.py <dance|turns|lag|distance> [args]` runs the program of
that name; every program also runs on its own. All share one carrier /
camera option set (`--robot`, `--wifi NAME|IP`, `--radio`, `--host/--port`
for a Pi serial daemon, `--camera`, `--field-cm W H`, `--margin`) and one
safety posture: a fresh camera fix before every move, the projected end
pose checked against the field limits less the margin, and pivots-only
programs refusing inside the margin.

| program | what it measures | result |
|---|---|---|
| `field_dance.py` | convention: +90/+180/+90 turn left, 20/40/20 cm drive forward/back, home | PASS/FAIL only (`.claude/rules/field-dance-first.md`) |
| `turn_calibration.py` | `--mode sweep` (default): camera-scored pivots ±90/107/180, many repeats; `--set FIELD=VALUE` sweeps a knob; `--no-tlm` camera-only; `--no-poll` silent wire; `--render`, `--compare` | per-angle error, fit gain/offset, `rotational_slip` + `stop_distance` (029) / `pivot_overrun` (pre-029) suggestion |
| `turn_calibration.py --mode g1..g6` | sprint 029's six acceptance gates, folded in by sprint 031 ticket 007 | PASS/FAIL against the bars restated below |
| `lag_measure.py` | step-response drivetrain lag from `WHEELS_V` + `TLM FULL` (design S10.2) | `lag_s` per wheel; `--apply` SETs the mean |
| `distance.py` | camera-scored straights out and back at several lengths | fit gain/offset; `travel_calib` suggestion |
| `mount.py` | tag lever/height from in-place pivots, yaw residual from a probe | writes `tools/field_calibration.json`, registers the daemon |

## The calibration order (stakeholder, 2026-09-05)

1. `dance` -- robot in the middle, under a minute: which way is left,
   which way is forward, does it come home.
2. `mount` -- after any tag (re)mount: the tag's lever and height from
   in-place pivots (least squares, P = C + R(h) m), verified by the
   centre standing still through four more pivots, then the yaw residual
   from a forward probe. Writes the calibration of record and registers
   the daemon; from here the camera reports the centre of rotation.
3. `distance` -- straights out and back at several lengths, faced along
   the field's long axis: the fit gain is the wheel-size scale
   (`travel_calib`), the offset is end-of-leg braking, not a scale.
4. `turns` -- `--no-tlm --set lag=<x>` at a few lags (0, 0.04, 0.10),
   8 pivots each: the pivot error is a function of `lag` on the 029
   engine (vevov: linear, -65 deg/s; tigez: a plateau 0.04-0.10). Pick
   the centred value, then 12-24 pivots to confirm; the fit gain gives
   `rotational_slip`.
5. Bake `travel_calib`, `rotational_slip`, `lag_s` in radio-robot-lib
   `geometry.firmware_bake`; flash; confirm once with no live SET.

`lag` (the step-response measurement) is recorded for the drivetrain's
sake; it is NOT the operating value -- the arrival credit at the floor
speed makes 0.13 s stop pivots ~4.5 deg short, and `stop_distance`
cannot go negative to compensate (`motion_limits.h`). Sprint 031 owns
reconciling the two; until then step 4 is the calibration.

## Rules baked into the programs (each learned the hard way)

- **Register the tag mount** (`tools/camlink.py --register <robot>`)
  and read the daemon's centre/heading straight; never hand-correct a
  raw tag (2026-09-04: the 1.119 parallax dilation mis-projected legs
  into the margin twice).
- **`TLM FULL` during pivots provokes early terminations** on the 029
  engine (4-5 of 12 at the default cruise, encoders agreeing); score
  with `--no-tlm`.
- **Over the relay pool, two unacked moves mean a dead relay**, not a
  dead robot: the sweep reconnects through the pool and re-applies its
  SETs (relays `gozop`/`guvov`/`zetog` each went silent at least once).
- **A camera daemon error is a missed fix, not a crash** (camera 2
  dropped frames twice in 40 min on 2026-09-04). Never restart the
  aprilcam daemon from an agent (it loses the macOS camera grant) --
  the operator runs `aprilcam daemon restart` in Terminal, then the
  detector needs priming with a few polls.
- **Pivots the drivetrain cannot have produced are excluded** and
  marked: centre moved > 8 cm (a hand), camera vs encoder > 15 deg (a
  stale fix), encoders > 30 deg off the command (a garbled command
  executed as a different angle).
- 180 deg pivots snap to the commanded lap; the camera tracker can
  mis-lap when it drops samples.
- **A robot that does not pivot about a consistent point invalidates
  both `mount` and `turns`.** Both fit against a fixed centre.
  MEASURED gopiv 2026-09-05, `reports/pf2-recal-20260905/`: its mount
  solve had rms 15.9 mm (tigez 1.1, vevov 4.8) with the implied centre
  walking 6.9 cm monotonically across eight pivots, and one `face()`
  pivot TRANSLATED it 45 cm, confirmed by an independent `get_tag` --
  rotation about a point ~22 cm outside the robot. Alternating +-90
  sweeps HIDE this (the translations cancel); same-direction turns
  accumulate it. Watch the solve rms and the per-pivot centre drift,
  not just the angle error.
- **WiFi is not a viable carrier for these runs.** Both tigez and
  vevov dropped off the network entirely under sustained motor load on
  2026-09-05 (`reports/pf2-recal-20260905/NOTES.md`: TCP refused then
  100% packet loss; later "broken pipe, the carrier is gone"). The
  radio relay pool carried every run after that without incident.
  Prefer `--radio`, or a Pi serial daemon on the robot.
- **A script that connects without `link.hello()` is silently
  ignored.** It inherits the robot's `expectedNext_` while sending ids
  from 1, so every command classifies as a stale retransmit and is
  dropped -- `ack: None`, no motion, a perfectly healthy `STATUS`
  (2026-09-05, cost a run).
- Results so far: `reports/tigez-turn-cal-20260903/` (pre-029),
  `reports/turn-compare-20260904/` (three drivetrains, pre-029),
  `reports/turn-cal-029-20260904/` (vevov and tigez on the 029 engine,
  lag 0.04 / 0.05 baked).

## Conventions

- Heading comes from the camera with the fixed +90 deg front-edge
  convention (`.claude/rules/tag-yaw-is-the-front-edge-not-the-hat.md`);
  `--heading-offset` exists only for the sub-degree physical residual.
- Sample heading at REST, never windowed across a move (the windowing
  reverses the sign of the pivot error; project memory
  `odometry-closure-tuning-knobs`).
- Every number a program prints that a config later carries must cite
  the run directory (`.claude/rules/measurement-citations.md`).
- `wire_get()` opens its reply window at the SEND and takes the LAST
  match. It used to look back 2.5 s and take the FIRST, so a second
  `GET` of the same field inside that window re-reported the earlier
  answer and the `(live)` banner could lie about what the robot was
  configured to (MEASURED tovez 2026-09-05,
  `captures/session-b-20260905/notes.md`;
  `clasi/issues/wire-get-returns-a-stale-reading.md`). It also retries,
  because a fresh WiFi session drops the odd first reply (MEASURED
  vevov 2026-09-04, `reports/turn-cal-029-20260904/`).

## Gate modes: sprint 029's acceptance, folded in by sprint 031

Sprint 029's acceptance session (`reports/bench-acceptance-029-20260904d.md`)
measured six named gates on tovez with its own one-off scripts
(`captures/bench-acceptance-029-20260904d/*.py`): G1 rest-heading
accuracy, G2 endpoint position, G3 leg length, G4 first-tick tracking,
G5 tracking overshoot, G6 square closure vs. baseline.

**Sprint 031 folded those six into `turn_calibration.py` as named
modes**, so there is one calibration/acceptance program instead of a
family of one-off scripts -- the standalone `g1`-`g6` scripts are
retired (or reduced to thin wrappers where a still-cited capture path
names one directly).

**Sprint 031 also restates G1 and G2**, the two bars the camera's own
noise floor could not resolve as originally set: camera heading noise
at rest measures sd 1.03 deg/sample (0.65 deg on a difference of
5-sample means) and position repeatability is several mm -- both
already exceed the original 0.4 deg (G1) and 5 mm (G2) bars before the
drivetrain enters into it at all. Restated:

- **G1** (rest-heading accuracy): mean|err| <= 1.0 deg, sd <= 1.0 deg,
  with >= 20-sample averaged fixes (up from single-sample fixes).
- **G2** (endpoint position): <= 10 mm.
- G3, G4, G5 and G6 are unchanged.

This is a floor set by today's instrument, not by the drivetrain's true
capability -- a future fixture improvement (a larger tag, two tags,
more samples per fix) should re-tighten these bars rather than treat
them as permanent. See
`clasi/sprints/done/031-drivetrain-tuning-and-gate-acceptance-on-tovez/sprint.md`'s
Design Rationale for the full argument.

### Implementation (sprint 031 ticket 007)

`--mode {sweep,g1,g2,g3,g5,g6}` defaults to `sweep`, the pre-existing
pivot sweep, unchanged. G4 reports alongside G3 (`--mode g3`), since
sprint 029's `g3_run.py` already measured both from the same telemetry
in one script. Each gate mode is one `run_gN()` drive function built on
two camera/telemetry primitives, `one_leg()` and `one_arc()` (the
straight-line and arc analogues of `one_turn()`), plus a shared
`_wait_done()` completion-poll and `_enable_tlm_full()` helper factored
out of the sweep's own code. Every gate's scoring is a small pure
function (`g1_score`, `g2_score`, `arc_expected_endpoint_mm`,
`arc_path_points`, `leg_metrics`, `fit_wheel_lag`, `square_closure_ok`)
with no Link/Camera dependency, unit-tested in
`test_turn_calibration_gates.py` (27 cases: bar constants, scoring
boundaries, arc geometry, synthetic-frame metrics, lag-fit recovery,
the completion-poll, and the camera noise-floor calculation G1's bar is
sized against). That test file is the one `test_`-prefixed file in this
directory and IS collected by pytest -- it is pure host logic and needs
no robot.

Each gate mode repeats the mandatory pre-flight path check
(`.claude/rules/playfield-testing.md`) from a measured start pose
before arming a commanded move -- `tools/field.py`'s `check_path()` for
every translating mode (g2/g3/g5/g6), and `arc_path_points()` for g2 so
a curved leg's projected path (which bows past its own chord) is
checked, not just its endpoint.

**Known gap** (2026-09-05): `distance.py`'s `face()` and `mount.py`'s
`--face` command pivots with NO `check_safe()` on the result, on the
assumption that a pivot does not translate. gopiv broke that
assumption -- one `face()` call moved it 45 cm on a railless field
(`reports/pf2-recal-20260905/`; see the gopiv rule below) -- and
`face()` retries 3x, so it can correct
repeatedly from a worsening position with nothing re-checking the
margin.

## Field facts the programs assume

- Main playfield: 134.3 x 89.3 cm, camera 3 `arducam-ov9782-usb-camera`,
  rails, margin 12 cm. Secondary: 110 x 70 cm, camera 2 `hd-usb-camera`,
  NO rails -- margin 15 cm and pivots-first.
- `tools/field_calibration.json` is the calibration of record for tag
  mounts; the field dance still reads it directly (via `tools/`).
- Lights: the Shelly at 192.168.1.122 turns off by itself; every
  program re-asserts it before a move.
