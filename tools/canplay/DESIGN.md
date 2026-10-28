# tools/canplay — can and cube games on the bb-obstacle mat

**Owner:** Eric Busboom · **Last reviewed:** 2026-10-27 · **Status:**
experimental. Host-side programs only; nothing here is linked into the
robot firmware.

Host programs that move tagged cans between the mat's numbered circles, or
sort coloured cubes into garages, with a gripper robot running
`test/canbot.ts`. The overhead camera (aprilcam) seeds the robot's pose
before every leg and the robot does the driving on its own odometry. See
[`README.md`](README.md) for the commands.

## Pieces

| file | role |
|---|---|
| `canplay.py` | circle-to-circle can moves; also the camera, link and planning code the other programs import |
| `setup.py` | puts cans on chosen circles in the fewest moves |
| `demo_loop.py` | repeats `setup.py` over a list of layouts |
| `duo.py` | two robots on one mat, each in its own worker process, with reserved field strips |
| `cubeplay.py`, `cubeplan.py` | cube sorting, one leg at a time or as a planned blind batch |
| `cubes.py` | cube detection in the deskewed camera frame |
| `matcam.py` | camera-to-mat homography, saved to `matcam.json` |
| `canplay_cal_<robot>.json`, `cubeplay_cal_<robot>.json` | each robot's learned gripper offset |
| `layouts/` | saved circle layouts for `demo_loop.py` |

## Conventions

- The camera is read before a leg and after it, never during a move
  (`docs/design/design.md`, camera doctrine).
- Calibration JSON is data, rewritten by the programs after each placement.
- The programs import `canplay.py` for camera, link and planning code;
  keep that one-way so the others stay small.
