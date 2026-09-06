#!/usr/bin/env python3
"""Shim: the field dance moved to tests/calibration/field_dance.py on
2026-09-05 (stakeholder: one home for the calibration programs). This
keeps `uv run tools/field_dance.py` working; run the new path directly,
or `tests/calibration/calibrate.py dance`, for the real thing.

Running this file executes the dance. IMPORTING it does not -- it
re-exports the real module's namespace instead, so
`tests/tools/test_field_dance_accel_bake.py`'s `import field_dance`
(with `tools/` on `sys.path`) still reaches `_dance_accel_decel()`
without driving a robot. The first version of this shim called
`runpy.run_path(..., run_name='__main__')` unconditionally, which made
that import run `main()` and take the whole pytest session down with
`SystemExit: 1`.
"""
import importlib.util
import pathlib
import runpy
import sys

_TARGET = pathlib.Path(__file__).resolve().parents[1] / 'tests' / 'calibration' / 'field_dance.py'

if __name__ == '__main__':
    sys.argv[0] = str(_TARGET)
    runpy.run_path(str(_TARGET), run_name='__main__')
else:
    _spec = importlib.util.spec_from_file_location('_field_dance_impl', _TARGET)
    _impl = importlib.util.module_from_spec(_spec)
    sys.modules['_field_dance_impl'] = _impl
    _spec.loader.exec_module(_impl)
    globals().update({k: v for k, v in vars(_impl).items()
                      if not k.startswith('__')})
