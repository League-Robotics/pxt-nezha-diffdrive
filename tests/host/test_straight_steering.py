"""tests/host/test_straight_steering.py -- sprint 044 ticket 008.

A GO_TO_W straight steers on the estimator pose (cross-track feedback with a
clamped yaw trim), and a final residual within the trim band is a short
straight, forward or reverse, rather than a pivot. Played against a true
two-wheel robot through pose_estimator_shim.cpp, sensors read every 4th tick.

Run with::

    uv run pytest tests/host/test_straight_steering.py -s
"""

import ctypes
import math
import statistics

import pytest

from test_goto_block_regression import _FULL_DUTY_VELOCITY, _PERIOD_MS
from test_pivot_closure import ARRIVE, TIMEOUT_MS, _rig
from test_pivot_closure import lib as pivot_lib  # noqa: F401 -- used as a fixture
from test_pose_estimator import ENCODERS_ONLY, GYRO_ONLY, OPTICAL
from test_pose_estimator import lib as estimator_lib  # noqa: F401 -- used as a fixture

DEG = math.pi / 180.0
GOAL_MEDIAN = 10.0  # [mm] sprint 044 goal 4
GOAL_P90 = 20.0     # [mm]
DEFAULT_FLOOR = 20.0  # [deg/s] the engine's own omega floor
CONFIGS = {"optical": OPTICAL, "gyro": GYRO_ONLY, "encoders": ENCODERS_ONLY}


@pytest.fixture
def lib(pivot_lib):
    vp, f, u, i = ctypes.c_void_p, ctypes.c_float, ctypes.c_uint32, ctypes.c_int
    pivot_lib.peSetSteering.argtypes = [vp, i, f, f, f, f]
    pivot_lib.peSetResidualTrim.argtypes = [vp, i, f, f, u, i, u]
    pivot_lib.peSetVFloor.argtypes = [vp, f]
    pivot_lib.peTrimCount.argtypes = [vp]
    pivot_lib.peTrimCount.restype = i
    pivot_lib.peTrimResidual.argtypes = [vp]
    pivot_lib.peTrimResidual.restype = f
    pivot_lib.peTrimTimedOut.argtypes = [vp]
    pivot_lib.peTrimTimedOut.restype = i
    return pivot_lib


def _off(lib, rig):
    lib.peSetSteering(rig.h, 0, 150.0, 4.0, 20.0, 0.15)
    lib.peSetResidualTrim(rig.h, 0, 30.0, 2.0, 250, 2, 3000)


def _leg(lib, rig, p, x, y, max_ticks=8000):
    lib.peGoToW(rig.h, x, y, p["speed"], ARRIVE, TIMEOUT_MS)
    ticks = lib.peRunMove(rig.h, _FULL_DUTY_VELOCITY, _PERIOD_MS, max_ticks)
    assert ticks < max_ticks
    return ticks


def _miss(lib, rig, x, y):  # [mm] truth to target
    return math.hypot(lib.peTruthX(rig.h) - x, lib.peTruthY(rig.h) - y)


def _cross_track(lib, rig, x, y, sx=0.0, sy=0.0):  # [mm] left of start->target
    length = math.hypot(x - sx, y - sy)
    ux, uy = (x - sx) / length, (y - sy) / length
    return -(lib.peTruthX(rig.h) - sx) * uy + (lib.peTruthY(rig.h) - sy) * ux


def _polar(distance, bearing):
    return distance * math.cos(bearing * DEG), distance * math.sin(bearing * DEG)


@pytest.mark.parametrize("config", [OPTICAL, GYRO_ONLY])
@pytest.mark.parametrize("slip", [1.05, 0.95])
@pytest.mark.parametrize("bearing", [40, -40])
@pytest.mark.parametrize("distance", [300.0, 1000.0])
def test_two_degree_pivot_error_arrives_within_one_cm_cross_track(
        lib, config, slip, bearing, distance):
    x, y = _polar(distance, bearing)
    results = {}
    for steered in (False, True):
        rig, p = _rig(lib, config, slip, floor=DEFAULT_FLOOR)
        try:
            lib.peSetPivotClosure(rig.h, 0, 250, 0.25, 45.0, 1.0, 3, 2500)
            if not steered:
                _off(lib, rig)
            _leg(lib, rig, p, x, y)
            results[steered] = abs(_cross_track(lib, rig, x, y))
            assert lib.peWrongWayCount(rig.h) == 0
        finally:
            rig.close()
    assert results[True] < 10.0
    if distance >= 1000.0:
        assert results[False] > 15.0


@pytest.mark.parametrize("slip", [1.0, 1.05])
@pytest.mark.parametrize("bearing", [60, -120])
def test_encoders_only_steers_on_odometry_without_regression(lib, slip, bearing):
    x, y = _polar(600.0, bearing)
    pose_miss, truth_miss = {}, {}
    for steered in (False, True):
        rig, p = _rig(lib, ENCODERS_ONLY, slip, floor=DEFAULT_FLOOR)
        try:
            if not steered:
                _off(lib, rig)
            _leg(lib, rig, p, x, y)
            pose_miss[steered] = math.hypot(lib.peX(rig.h) - x, lib.peY(rig.h) - y)
            truth_miss[steered] = _miss(lib, rig, x, y)
            assert lib.peWrongWayCount(rig.h) == 0
        finally:
            rig.close()
    assert pose_miss[True] <= pose_miss[False] + 0.5
    assert pose_miss[True] < 2.0
    # Odometry cannot see a rotation the wheels slipped, so the truth miss is
    # the unobserved heading error carried down the chord.
    assert truth_miss[True] <= truth_miss[False] + 6.0


def _sweep(lib, config, steered=True):
    errors = []
    for bearing in (60, -75, 100, -135, 180, 170):
        for distance in (100.0, 250.0, 500.0, 1000.0):
            for slip in (1.0, 1.05, 0.95):
                for bias in (0.0, 150.0, -150.0):
                    x, y = _polar(distance, bearing)
                    rig, p = _rig(lib, config, slip, bias, floor=DEFAULT_FLOOR)
                    try:
                        if not steered:
                            _off(lib, rig)
                        _leg(lib, rig, p, x, y)
                        assert lib.peWrongWayCount(rig.h) == 0
                        errors.append(_miss(lib, rig, x, y))
                    finally:
                        rig.close()
    errors.sort()
    return statistics.median(errors), errors[int(0.9 * len(errors))]


@pytest.mark.parametrize("name", ["optical", "gyro"])
def test_arrival_sweep_meets_the_sprint_goal(lib, name, capsys):
    base = _sweep(lib, CONFIGS[name], steered=False)
    median, p90 = _sweep(lib, CONFIGS[name])
    with capsys.disabled():
        print(f"\n{name}: open loop median {base[0]:.1f} p90 {base[1]:.1f} mm;"
              f" steered median {median:.1f} p90 {p90:.1f} mm")
    assert median < GOAL_MEDIAN
    assert p90 < GOAL_P90


def test_encoders_only_sweep_is_reported_and_no_worse(lib, capsys):
    base = _sweep(lib, ENCODERS_ONLY, steered=False)
    median, p90 = _sweep(lib, ENCODERS_ONLY)
    with capsys.disabled():
        print(f"\nencoders: open loop median {base[0]:.1f} p90 {base[1]:.1f} mm;"
              f" steered median {median:.1f} p90 {p90:.1f} mm")
    assert median <= base[0] + 1.0
    assert p90 <= base[1] + 2.0


@pytest.mark.parametrize("config", [OPTICAL, GYRO_ONLY, ENCODERS_ONLY])
@pytest.mark.parametrize("offset", [(20.0, 0.0), (-20.0, 0.0), (-28.0, 6.0),
                                    (12.0, -10.0), (-3.0, 0.0)])
def test_residual_within_the_band_is_a_short_straight_not_a_pivot(
        lib, config, offset):
    x, y = offset
    rig, p = _rig(lib, config, 1.0, floor=DEFAULT_FLOOR)
    try:
        _leg(lib, rig, p, x, y)
        assert abs(lib.peTruthHeading(rig.h)) < 0.3 * DEG
        assert abs(lib.peX(rig.h) - x) < 3.0
        assert abs(lib.peTruthX(rig.h) - x) < 3.0
        assert lib.peWrongWayCount(rig.h) == 0
        assert (lib.peTruthX(rig.h) > 0.0) == (x > 0.0)
    finally:
        rig.close()


@pytest.mark.parametrize("config", [OPTICAL, GYRO_ONLY, ENCODERS_ONLY])
def test_overshoot_is_backed_off_not_turned_around(lib, config):
    rig, p = _rig(lib, config, 1.0, floor=DEFAULT_FLOOR)
    try:
        _leg(lib, rig, p, 400.0, 0.0)
        before = lib.peTruthHeading(rig.h)
        pose_x = lib.peX(rig.h)
        _leg(lib, rig, p, pose_x - 22.0, 0.0)
        assert abs(lib.peTruthHeading(rig.h) - before) < 0.3 * DEG
        assert lib.peX(rig.h) == pytest.approx(pose_x - 22.0, abs=3.0)
        assert lib.peTruthX(rig.h) < pose_x
        assert lib.peWrongWayCount(rig.h) == 0
    finally:
        rig.close()


def test_a_residual_beyond_the_band_still_pivots(lib):
    rig, p = _rig(lib, OPTICAL, 1.0, floor=DEFAULT_FLOOR)
    try:
        x, y = -60.0, 0.0
        _leg(lib, rig, p, x, y)
        assert abs(lib.peTruthHeading(rig.h)) > 90.0 * DEG
    finally:
        rig.close()


def test_trim_closes_an_along_track_miss_after_the_straight(lib):
    rig, p = _rig(lib, OPTICAL, 1.0, floor=DEFAULT_FLOOR)
    try:
        lib.peOpticalScale(rig.h, 0.98)
        x, y = _polar(500.0, 60)
        _leg(lib, rig, p, x, y)
        assert lib.peTrimCount(rig.h) >= 1
        assert math.hypot(lib.peX(rig.h) - x, lib.peY(rig.h) - y) < 3.0
    finally:
        rig.close()


def test_trim_count_is_capped(lib):
    rig, p = _rig(lib, OPTICAL, 1.0, floor=DEFAULT_FLOOR)
    try:
        lib.peOpticalScale(rig.h, 0.98)
        lib.peSetVFloor(rig.h, 0.01)
        lib.peSetResidualTrim(rig.h, 1, 30.0, 0.0, 250, 2, 3000)
        _leg(lib, rig, p, *_polar(500.0, 60))
        assert lib.peTrimCount(rig.h) == 2
        assert not lib.peMoveActive(rig.h)
    finally:
        rig.close()


def test_trim_gives_up_on_its_timeout(lib):
    rig, p = _rig(lib, OPTICAL, 1.0, floor=DEFAULT_FLOOR)
    try:
        lib.peOpticalScale(rig.h, 0.98)
        lib.peSetResidualTrim(rig.h, 1, 30.0, 2.0, 250, 2, 1)
        _leg(lib, rig, p, *_polar(500.0, 60))
        assert lib.peTrimTimedOut(rig.h) == 1
        assert lib.peTrimCount(rig.h) == 0
    finally:
        rig.close()


@pytest.mark.parametrize("config", [OPTICAL, GYRO_ONLY, ENCODERS_ONLY])
def test_steering_trim_never_trips_wrong_way_or_leaves_the_leg_open(lib, config):
    for bearing in (60, -100, 180, -170):
        for slip in (0.9, 1.1):
            rig, p = _rig(lib, config, slip, 400.0, floor=DEFAULT_FLOOR)
            try:
                lib.peSetPivotClosure(rig.h, 0, 250, 0.25, 45.0, 1.0, 3, 2500)
                _leg(lib, rig, p, *_polar(800.0, bearing))
                assert lib.peWrongWayCount(rig.h) == 0
                assert not lib.peMoveActive(rig.h)
            finally:
                rig.close()
