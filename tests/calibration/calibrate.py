#!/usr/bin/env python3
"""calibrate -- the one entry point for the on-robot calibration programs.

    uv run python tests/calibration/calibrate.py dance    [field_dance args]
    uv run python tests/calibration/calibrate.py turns    [turn_calibration args]
    uv run python tests/calibration/calibrate.py lag      [lag_measure args]
    uv run python tests/calibration/calibrate.py distance [distance args]

Run them in that order on a robot that is new to a field or a firmware:

  dance     convention check, under a minute, robot in the middle of the
            field; PASS/FAIL, never a tuning number.
  turns     camera-scored pivots; `--set lag=<x>` sweeps the arrival
            credit until pivots land centred (029 engine); `--render`
            charts a run, `--compare` overlays runs/robots.
  lag       the step-response drivetrain lag (design S10.2) -- the
            physical constant, for the record; the OPERATING lag comes
            from `turns` (see tests/calibration/DESIGN.md).
  distance  camera-scored straights -> travel_calib.

Each subcommand takes the same carrier/camera options (--robot, --wifi,
--radio, --host/--port, --camera, --field-cm, --margin) and writes under
--out. `calibrate.py <sub> --help` prints that program's own help.
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
