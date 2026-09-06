"""tests/tools/test_travel_calib_drift.py -- travelCalib mirror guard.

`src/motion/motion_engine.h`'s `travelCalib_` is the sole source of
truth for wheel travel per shaft degree (camera-measured, updated as
new bench data arrives). TWO host-side files hand-type a mirror of it,
and this module pins both:

1. `tools/tour_chart.py`'s `--travel-calib` default -- the fallback
   scale for LEGACY velocity CSVs recorded before the v6 wire carried
   wheel speed natively in mm/s (current-format CSVs are read at 1:1 --
   see that module's own unit-detection comment, keyed off the `mmps`
   column header). A stale mirror there silently mis-scales any legacy
   capture re-plotted with today's tool.
2. `tests/system/run_tour.py`'s `TRAVEL_CALIB` -- the mm-to-counts
   scale (`CPM = 10.0 / TRAVEL_CALIB`) every tour this project judges
   its motion work against is commanded and scored in. Added by sprint
   034 ticket 010: this was a THIRD copy that nothing checked, and it
   holds the exact constant that drifted before (0.8102 stayed mirrored
   well past the 0.7878 camera-measured update), so it was the copy
   most worth pinning and the only one that was not.

Both are exactly the failure mode this project's other drift tests
already guard against for the wire protocol's own mirrored constants
(test_wire_constants_drift.py).

Text-based, not an import: tools/tour_chart.py pulls in matplotlib at
module scope, which is not part of this project's `uv run pytest`
environment (see that module's own docstring -- it is invoked
separately, via `uv run --with matplotlib`), and tests/system/run_tour.py
opens a socket to a real robot. Reading all three files as plain text
needs neither a compiler, matplotlib, nor hardware.

Run with::

    uv run pytest tests/tools/test_travel_calib_drift.py
"""
import pathlib
import re

# tests/tools/test_travel_calib_drift.py -> tools -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_MOTION_ENGINE_H = _REPO_ROOT / "src" / "motion" / "motion_engine.h"
_TOUR_CHART_PY = _REPO_ROOT / "tools" / "tour_chart.py"
_RUN_TOUR_PY = _REPO_ROOT / "tests" / "system" / "run_tour.py"


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


def _run_tour_travel_calib():
    text = _RUN_TOUR_PY.read_text()
    match = re.search(r"^TRAVEL_CALIB\s*=\s*([0-9.]+)\s*$", text, re.M)
    assert match, "run_tour.py's TRAVEL_CALIB was not found"
    return float(match.group(1))


def test_run_tour_travel_calib_matches_motion_engine():
    """tests/system/run_tour.py's TRAVEL_CALIB must match
    motion_engine.h's travelCalib_ exactly.

    It is not a display setting: `CPM = 10.0 / TRAVEL_CALIB` is the
    mm-to-encoder-counts scale run_tour.py commands AND scores every
    tour in, so a stale copy moves the measured result of a tour without
    moving anything about the robot -- the same tour would be judged
    against a robot that does not exist. This suite (tests/system/) needs
    a real robot and is never run by `uv run pytest`, which is exactly
    why the constant inside it needs a guard that IS."""
    engine_value = _motion_engine_travel_calib()
    tour_value = _run_tour_travel_calib()
    assert engine_value == tour_value, (
        f"tests/system/run_tour.py's TRAVEL_CALIB ({tour_value}) has "
        f"drifted from src/motion/motion_engine.h's travelCalib_ "
        f"({engine_value}). Update run_tour.py's TRAVEL_CALIB to match; "
        f"its CPM (counts per mm) is derived from it."
    )
