# canplay — can games on the bb-obstacle mat

Host programs that move tagged cans between the mat's numbered circles with a
gripper robot running `test/canbot.ts`. The overhead camera (aprilcam) seeds
the robot's pose before every leg; the robot does the driving.

| robot | gripper | link |
|---|---|---|
| zetuv (Cutebot, tag 58) | servo S1 | radio: `--relay magni` |
| tigez (Nezha, tag 57) | J2 / P2 | USB: `--host <pi>`, radio, or WiFi |

```sh
# move the can on circle 9 to circle 5, then go home
uv run python tools/canplay/canplay.py --robot zetuv --relay magni 9 5

# put cans on circles 2, 4, 6 (or name them: 13:2 64:4 63:6), parking blockers first
uv run python tools/canplay/setup.py --robot zetuv --relay magni 2 4 6
uv run python tools/canplay/setup.py --plan 13:2 64:4      # plan only, no robot

# keep a robot moving for a demo, until Ctrl-C
uv run python tools/canplay/demo_loop.py --robot zetuv --relay magni
```

Each can carries an AprilTag 122 mm up; `canplay.py` registers any new
non-robot tag at that height and adds it to radio-robot-lib
`config/mat/cans.json`. `canplay_cal_<robot>.json` holds each robot's learned
gripper offset, updated after every placement.
