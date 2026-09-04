# linefollow -- vevov on the KIPR line mat

Written 2026-09-02; results in `reports/line-follow-20260902/README.md`.
Robot-side code is `test/linefollow.ts` (85 lines: `RUN:line`, `RUN:abort`,
`RUN:linesense`, button A; PlanetX Trackbit on I2C 0x1A), built in place of
test.ts with `uv run python tools/make_deploy.py --program linefollow.ts
--robot vevov` and flashed from `.tmp/deploy-linefollow/built/binary.hex`. Host scripts run under the
aprilcam venv python (`~/.local/pipx/venvs/aprilcam/bin/python`) unless noted.

| file | role |
|---|---|
| `sensor_run.py [--radio] ROBOT OUT [speed] [max_s] [kp]` | run `RUN:line` over the farm serial daemon, log the LINE: trace + camera truth, abort at the rails |
| `chart_sensor.py run.json path.json out.png` | score the camera track against the line (`uv run --with numpy --with matplotlib`) |
| `linerun.py ROBOT LOG "CMD|wait" ...` | one lossless session to the farm daemon (plain python3) |
| `stage.py X Y HDG` | put the robot on a TRUE world pose from one camera fix; every pivot camera-verified |
| `kipr_course.path.json` | the course as traced from a deskewed camera frame; field frame, mm |
| `follow.py`, `camlog.py`, `chart.py` | the earlier camera-mapped odometry follower (comparison only) |

If the robot ever latches an e-stop, `SET estop_clear 1 #<id>` clears it
(the minimal program has no clear verb). Run `uv run tools/field_dance.py`
first, every session. The camera is a
diagnostic and a rail guard, never a steering input.
