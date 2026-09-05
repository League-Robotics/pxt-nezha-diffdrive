#!/usr/bin/env python3
"""Shim: the field dance moved to tests/calibration/field_dance.py on
2026-09-05 (stakeholder: one home for the calibration programs). This
keeps `uv run tools/field_dance.py` working; run the new path directly,
or `tests/calibration/calibrate.py dance`, for the real thing."""
import pathlib
import runpy
import sys

_TARGET = pathlib.Path(__file__).resolve().parents[1] / 'tests' / 'calibration' / 'field_dance.py'
sys.argv[0] = str(_TARGET)
runpy.run_path(str(_TARGET), run_name='__main__')
