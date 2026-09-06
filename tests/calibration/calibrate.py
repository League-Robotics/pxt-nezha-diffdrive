#!/usr/bin/env python3
"""calibrate -- the one entry point for the on-robot calibration programs.

    uv run python tests/calibration/calibrate.py dance    [field_dance args]
    uv run python tests/calibration/calibrate.py turns    [turn_calibration args]
    uv run python tests/calibration/calibrate.py lag      [lag_measure args]
    uv run python tests/calibration/calibrate.py distance [distance args]
    uv run python tests/calibration/calibrate.py mount    [mount args]
    uv run python tests/calibration/calibrate.py acceptance <robot> [args]

Run them in this order on a robot that is new to a field, a firmware,
or has been rebuilt (the stakeholder's order, 2026-09-05):

  1. dance     convention check, under a minute, robot in the middle of
               the field: left is left, forward is forward, it comes home.
               PASS/FAIL, never a tuning number.
  2. mount     after a tag (re)mount: where the tag sits (lever, height)
               and its yaw residual, from in-place pivots and one probe;
               writes tools/field_calibration.json and registers the
               daemon. Everything below needs the centre of rotation the
               daemon reports once this is right.
  3. distance  camera-scored straights, out and back -> the wheel size
               (`travel_calib`); with the mount right the robot can be
               faced along a known direction and driven known distances.
  4. turns     camera-scored pivots; `--set lag=<x>` sweeps the arrival
               credit until pivots land centred (029 engine), then
               `rotational_slip` from the fit gain; `--render` charts,
               `--compare` overlays runs/robots.
  lag          the step-response drivetrain lag (design S10.2) -- the
               physical constant, for the record; the OPERATING lag comes
               from `turns` (tests/calibration/DESIGN.md).
  acceptance   NOT calibration: sprint 034's on-field acceptance of the
               consolidated link, camera and geofence -- a MOVE_X the
               camera confirms actually moved the robot, a registered
               pose against a known dot, and a geofence refusal with
               nothing sent. PASS/FAIL/BLOCKED, captured to
               captures/consolidation-acceptance-<robot>-<date>/notes.md.
               `--dry-run` prints the plan and opens nothing.

Each CALIBRATION subcommand takes the same carrier/camera options
(--robot, --wifi, --radio, --host/--port, --camera, --field-cm,
--margin) and writes under --out. `acceptance` is the exception and
says so in its own help: it takes the robot POSITIONALLY, its carriers
are --wifi-tcp (the default) / --radio / --serial HOST:PORT per
`.claude/rules/connecting-to-a-robot.md`, and it writes to
--capture-dir rather than --out, because its artifact is a capture a
MEASURED citation points at and not a report. `calibrate.py <sub>
--help` prints that program's own help.
"""
import pathlib
import runpy
import sys

HERE = pathlib.Path(__file__).resolve().parent
PROGRAMS = {
    'dance': 'field_dance.py',
    'turns': 'turn_calibration.py',
    'lag': 'lag_measure.py',
    'distance': 'distance.py',
    'mount': 'mount.py',
    'acceptance': 'consolidation_acceptance.py',
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help') or sys.argv[1] not in PROGRAMS:
        print(__doc__)
        return 0 if len(sys.argv) >= 2 and sys.argv[1] in ('-h', '--help') else 2
    target = HERE / PROGRAMS[sys.argv[1]]
    sys.argv = [str(target)] + sys.argv[2:]
    runpy.run_path(str(target), run_name='__main__')
    return 0


if __name__ == '__main__':
    sys.exit(main())
