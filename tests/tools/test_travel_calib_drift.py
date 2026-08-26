"""tests/tools/test_travel_calib_drift.py -- travelCalib mirror guard.

`src/motion/motion_engine.h`'s `travelCalib_` is the sole source of
truth for wheel travel per shaft degree (camera-measured, updated as
new bench data arrives). `tools/tour_chart.py`'s `--travel-calib`
default is a hand-typed mirror of that value, used as the fallback
scale for LEGACY velocity CSVs recorded before the v6 wire carried
wheel speed natively in mm/s (current-format CSVs are read at 1:1 --
see that module's own unit-detection comment, keyed off the `mmps`
column header). A stale mirror here silently mis-scales any legacy
capture re-plotted with today's tool -- exactly the failure mode this
project's other drift tests already guard against for the wire
protocol's own mirrored constants (test_wire_constants_drift.py).

Text-based, not an import: tools/tour_chart.py pulls in matplotlib at
module scope, which is not part of this project's `uv run pytest`
environment (see that module's own docstring -- it is invoked
separately, via `uv run --with matplotlib`). Reading both files as
plain text needs neither a compiler nor matplotlib.

Run with::

    uv run pytest tests/tools/test_travel_calib_drift.py
"""
import pathlib
import re

# tests/tools/test_travel_calib_drift.py -> tools -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_MOTION_ENGINE_H = _REPO_ROOT / "src" / "motion" / "motion_engine.h"
_TOUR_CHART_PY = _REPO_ROOT / "tools" / "tour_chart.py"


def _motion_engine_travel_calib():
    text = _MOTION_ENGINE_H.read_text()
    match = re.search(r"travelCalib_\s*=\s*([0-9.]+)f;", text)
    assert match, "motion_engine.h's travelCalib_ default was not found"
    return float(match.group(1))


def _tour_chart_travel_calib_default():
    text = _TOUR_CHART_PY.read_text()
    match = re.search(
        r"add_argument\('--travel-calib',\s*type=float,\s*default=([0-9.]+)\)",
        text,
    )
    assert match, "tour_chart.py's --travel-calib default was not found"
    return float(match.group(1))


def test_tour_chart_travel_calib_default_matches_motion_engine():
    """tour_chart.py's --travel-calib default must match motion_engine.h's
    travelCalib_ exactly. The two drifted apart once already (0.8102
    mirrored well past the 0.7878 camera-measured update) with nothing
    but a CLI --help string and a doc comment to keep them aligned."""
    engine_value = _motion_engine_travel_calib()
    tool_value = _tour_chart_travel_calib_default()
    assert engine_value == tool_value, (
        f"tools/tour_chart.py's --travel-calib default ({tool_value}) has "
        f"drifted from src/motion/motion_engine.h's travelCalib_ "
        f"({engine_value}). Update tour_chart.py's argparse default (and "
        f"its module docstring's example invocation) to match."
    )
