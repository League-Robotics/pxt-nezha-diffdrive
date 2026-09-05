# tests/calibration — the on-robot calibration programs

**Owner:** Eric Busboom · **Last reviewed:** 2026-09-05 · **Status:**
active (consolidated here 2026-09-05 from `tests/playfield/` and
`tools/field_dance.py` at the stakeholder's direction: "a small number
of solid tests we're going to use for testing and calibration")

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
| `turn_calibration.py` | camera-scored pivots ±90/107/180, many repeats; `--set FIELD=VALUE` sweeps a knob; `--no-tlm` camera-only; `--render`, `--compare` | per-angle error, fit gain/offset, `rotational_slip` + `stop_distance` (029) / `pivot_overrun` (pre-029) suggestion |
| `lag_measure.py` | step-response drivetrain lag from `WHEELS_V` + `TLM FULL` (design S10.2) | `lag_s` per wheel; `--apply` SETs the mean |
| `distance.py` | camera-scored straights out and back at several lengths | fit gain/offset; `travel_calib` suggestion |

## The 029-engine calibration order

1. `dance` -- robot in the middle, under a minute.
2. `turns --no-tlm --set lag=<x>` at a few lags (0, 0.04, 0.10), 8
   pivots each: the pivot error is a function of `lag` on this engine
   (vevov: linear, −65 deg/s; tigez: a plateau 0.04-0.10). Pick the
   centred value.
3. `distance` at that lag: straights within a few mm confirm the lag
   does not break braking; the fit gain is the `travel_calib` scale.
4. `turns` 12-24 pivots at the chosen lag; bake `lag_s` (and
   `travel_calib` if the gain moved) in radio-robot-lib
   `geometry.firmware_bake`; flash; confirm once with no live SET.

`lag` (the step-response measurement) is recorded for the drivetrain's
sake; it is NOT the operating value -- the arrival credit at the floor
speed makes 0.13 s stop pivots ~4.5 deg short, and `stop_distance`
cannot go negative to compensate (`motion_limits.h`). Sprint 031 owns
reconciling the two; until then step 2 is the calibration.

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
- Results so far: `reports/tigez-turn-cal-20260903/` (pre-029),
  `reports/turn-compare-20260904/` (three drivetrains, pre-029),
  `reports/turn-cal-029-20260904/` (vevov and tigez on the 029 engine,
  lag 0.04 / 0.05 baked).

## Field facts the programs assume

- Main playfield: 134.3 x 89.3 cm, camera 3 `arducam-ov9782-usb-camera`,
  rails, margin 12 cm. Secondary: 110 x 70 cm, camera 2 `hd-usb-camera`,
  NO rails -- margin 15 cm and pivots-first.
- `tools/field_calibration.json` is the calibration of record for tag
  mounts; the field dance still reads it directly (via `tools/`).
- Lights: the Shelly at 192.168.1.122 turns off by itself; every
  program re-asserts it before a move.
