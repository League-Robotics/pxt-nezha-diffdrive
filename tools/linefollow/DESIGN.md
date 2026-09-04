# tools/linefollow — vevov on the KIPR line mat

**Owner:** Eric Busboom · **Last reviewed:** 2026-09-04 · **Status:**
experimental (written 2026-09-02 on master, outside sprint 029; this
document added at sprint 029's close, which found the directory
without one — see `README.md` here for the run-by-run account and
`reports/line-follow-20260902/`)

Host side of a line-following experiment: drive vevov along the black
line on the KIPR mat, both by a camera-seeded pure-pursuit on the
robot's own odometry (`follow.py`) and by the on-robot Trackbit sensor
loop (`sensor_run.py`, robot code `test/linefollow.ts`), and score
both against the overhead camera.

## Pieces

| file | role |
|---|---|
| `kipr_course.path.json` | the reference path, traced from a deskewed camera frame, field frame, mm |
| `stage.py` | put the robot on the path start: camera fix, pivot, drive, re-fix |
| `follow.py` | world-anchored pure pursuit on odometry; ONE camera fix before to seed the field→odometry transform, one after to score |
| `sensor_run.py` | run the robot's own `RUN:line` sensor loop over the relay and log it |
| `linerun.py` | one lossless session to a farm robot's serial daemon (dynamic `_mbserial._tcp` port), timestamped replies |
| `camlog.py` | log the camera-measured centre of rotation to CSV at the daemon's rate — diagnostic only, nothing reaches the robot |
| `chart.py`, `chart_sensor.py` | score and chart a run: reference path, camera track, odometry track, cross-track error |

## Conventions it depends on

- **Camera doctrine** (`docs/design/design.md`): one fix at the start,
  one at the end, recording throughout; nothing the camera sees
  mid-run reaches the robot.
- **Calibration of record**: since sprint 029 ticket 006 every tool
  here reads `tools/field_calibration.json`'s `robots.vevov` entry
  (lever, parallax, camera, tag, radio) and derives the heading offset
  as `90 + mount_yaw_residual_deg`. These are vevov tools and pin
  `vevov` explicitly rather than following `default_robot`. They use
  the RAW tag plus the tool-side `lever_cm`/`parallax_k`, not a daemon
  registration — the two paths must not be mixed
  (`clasi/issues/parallax-k-and-registered-mount-z-correct-twice.md`).
- **Carrier**: the torture relay pool (`tools/fieldlink.py`) or a farm
  serial daemon (`linerun.py`); the host scripts run under the aprilcam
  venv's python where the README says so.

## Results and open ends

`reports/line-follow-20260902/README.md`: the on-robot sensor loop
holds 0.8-1.0 cm over 2.3 m; the camera-seeded odometry pursuit
drifts about 5 cm (the odometry's own rotation error). `i2cf` climbs
during runs — the Trackbit shares the I2C bus with the Nezha brick,
which is the sprint 030 bus/fiber-safety topic. No host tests: every
script drives or reads live hardware; `chart*.py` could be pinned
against a captured run if this grows.
