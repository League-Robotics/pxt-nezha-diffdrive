"""tests/host/test_move_x_arc_space.py -- `MotionEngine::moveX()` drives
ONE constant-radius arc for any `(distance, rotation)`, and a tight arc
is shaped in the dominant wheel's frame.

Drives the real C++ engine to completion on ideal wheels
(`motion_engine_shim.cpp`'s `meProbeRunToCompletion()`, via
`test_goto_block_regression.py`'s `ProbeEngine`) and checks the
resulting body-frame endpoint and heading against the closed-form arc
R = distance / rotation:

    x = R sin(theta),  y = R (1 - cos(theta)),  heading = theta

over a gallery that covers the whole parameter plane
`reports/move-x-arc-space-20260906.md` maps: rotations from 30 deg to
two full turns, radii from 60 cm down to under half the track width
(inner wheel reversed), and reverse travel. HISTORY: moveX() used to
replace any |rotation| >= 50 deg move with pivot-then-straight -- a
different figure ending somewhere else (MEASURED gopiv 2026-09-01,
`reports/tours-20260901/circle.json`: a 360 deg arc drove as a 942 mm
straight line). Every case here except the first would have failed.

The second test pins the frame fix that had to ship with the split's
removal (report, figure 5): for a blended segment `Segment::remaining()`
used to measure the MEAN axis while the shaper's speed, brake budget and
arrival window are the dominant WHEEL's, so a tight arc braked on its
second tick, crawled at the floor and stopped short. With
`Segment::dominantScale()` a tight arc takes about as long as a
straight whose dominant wheel travels the same distance.

Like every host test this is ideal wheels -- no lag, no stiction. The
report names the bench checks that would settle hardware (wheels-up
MOVE_X at 50 mm / 180 deg, a radius sweep, a 94 cm / 360 deg circle from
a camera fix).

Run with::

    uv run pytest tests/host/test_move_x_arc_space.py
"""

import math

import pytest

from test_goto_block_regression import (
    ProbeEngine, _ready, _PROBE_SPEED_MM_S, _PROBE_TIMEOUT_MS, _PERIOD_MS,
)

# [mm] the ideal-wheels landing residual is the shaper's own arrival
# window (one tick of the floor speed, ~1.7 mm on the dominant wheel);
# test_goto_block_regression.py holds goToR() to 10 mm for the same
# reason. A tight arc's short mean axis sees a proportionally smaller
# residual, so 10 mm is generous everywhere in the gallery.
_LANDING_TOLERANCE_MM = 10.0
_HEADING_TOLERANCE_RAD = math.radians(1.0)


def _arc_end(distance_mm, rotation_rad):
    if abs(rotation_rad) < 1e-9:
        return distance_mm, 0.0
    r = distance_mm / rotation_rad
    return r * math.sin(rotation_rad), r * (1.0 - math.cos(rotation_rad))


@pytest.mark.parametrize("distance_mm,rotation_deg,label", [
    (300.0, 30.0, "wide arc, below the old split (control)"),
    (300.0, 90.0, "quarter circle, R 19 cm"),
    (150.0, 90.0, "quarter circle, R 9.5 cm"),
    (300.0, 180.0, "half circle, R 9.5 cm"),
    (50.0, 150.0, "near target, R 1.9 cm < b/2: inner wheel reversed"),
    (2.0 * math.pi * 150.0, 360.0, "full circle, R 15 cm, comes home"),
    (2.0 * math.pi * 100.0 * 2.0, 720.0, "two laps, R 10 cm, comes home"),
    (-250.0, 180.0, "reverse round a half circle"),
    (-150.0, -90.0, "reverse, clockwise"),
])
def test_move_x_lands_on_the_arc_endpoint(motion_lib, distance_mm,
                                          rotation_deg, label):
    rotation = math.radians(rotation_deg)
    expected_x, expected_y = _arc_end(distance_mm, rotation)
    with ProbeEngine(motion_lib) as e:
        _ready(e)
        e.move_x(distance_mm, rotation, _PROBE_SPEED_MM_S, _PROBE_TIMEOUT_MS)
        e.run_to_completion()

        miss = math.hypot(e.probe_x() - expected_x, e.probe_y() - expected_y)
        assert miss < _LANDING_TOLERANCE_MM, (
            f"{label}: landed {miss:.1f} mm from the arc endpoint "
            f"({e.probe_x():.0f}, {e.probe_y():.0f}) vs "
            f"({expected_x:.0f}, {expected_y:.0f})")
        assert e.probe_heading() == pytest.approx(
            rotation, abs=_HEADING_TOLERANCE_RAD), label


def test_move_x_never_produces_the_old_corner(motion_lib):
    """move_x(30 cm, 90 deg) ends at the arc's (19.1, 19.1) cm, 22 cm
    away from the corner (0, 30) the old pivot-then-straight produced --
    the same 22 cm gap the report's figure 1 draws."""
    rotation = math.pi / 2.0
    with ProbeEngine(motion_lib) as e:
        _ready(e)
        e.move_x(300.0, rotation, _PROBE_SPEED_MM_S, _PROBE_TIMEOUT_MS)
        e.run_to_completion()
        corner_x, corner_y = 300.0 * math.cos(rotation), 300.0 * math.sin(rotation)
        gap = math.hypot(e.probe_x() - corner_x, e.probe_y() - corner_y)
        assert gap > 200.0


def _ticks_for(motion_lib, distance_mm, rotation_rad, cruise):
    with ProbeEngine(motion_lib) as e:
        _ready(e)
        e.move_x(distance_mm, rotation_rad, cruise, _PROBE_TIMEOUT_MS)
        ticks = e.run_to_completion()
        b = e.effective_track_width()
        heading_err = e.probe_heading() - rotation_rad
    return ticks, heading_err, b


def test_tight_arc_is_shaped_on_the_dominant_wheel(motion_lib):
    """move_x(5 cm, 180 deg) has a dominant wheel travelling
    50 + pi*b/2 mm while the mean axis travels only 50 mm. Shaped on the
    mean axis (as built before this change) the shaper brakes from the
    second tick and the segment crawls at the floor: emulated 1.99 s
    against 1.32 s, landing 5.6 deg short (report, figure 5). Shaped on
    the dominant wheel it takes about as long as a STRAIGHT whose one
    wheel does the same distance, and lands on heading."""
    cruise = 250.0
    rotation = math.pi
    arc_ticks, heading_err, b = _ticks_for(motion_lib, 50.0, rotation, cruise)
    dominant_mm = 50.0 + rotation * 0.5 * b
    straight_ticks, _, _ = _ticks_for(motion_lib, dominant_mm, 0.0, cruise)

    # The landing residual is the shaper's arrival window: one tick of
    # the 70 mm/s floor on the dominant wheel (~1.7 mm of ~229 mm here),
    # which this tight arc turns into ~1.3 deg of yaw. That is the same
    # one-tick residual every segment carries; a pure pivot's is smaller
    # only because it floors on omegaFloor (20 deg/s) instead.
    floor_tick_mm = 70.0 * (_PERIOD_MS / 1000.0)
    residual_bound = rotation * floor_tick_mm / dominant_mm + math.radians(0.3)
    assert abs(heading_err) < residual_bound, (
        f"heading error {math.degrees(heading_err):.2f} deg exceeds the "
        f"floor-tick bound {math.degrees(residual_bound):.2f} deg")
    # Same dominant-wheel work, same time, within a couple of ticks; the
    # as-built crawl was ~1.5x.
    assert arc_ticks <= straight_ticks + 3, (
        f"tight arc took {arc_ticks} ticks ({arc_ticks * _PERIOD_MS} ms) "
        f"against {straight_ticks} for an equivalent straight")
