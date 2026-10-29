"""tests/host/test_pivot_closure.py -- sprint 044 ticket 007.

A GO_TO_W pivot ends on the estimator's heading, not the encoder count:
after the encoder pivot settles the engine reads the pose heading and
pivots the remaining error, bounded in count and time. Played against a
true two-wheel robot through pose_estimator_shim.cpp, with rotational slip
(trackError) and gyro bias, sensors read every 4th tick.

Run with::

    uv run pytest tests/host/test_pivot_closure.py
"""

import ctypes
import math

import pytest

from test_goto_block_regression import _FULL_DUTY_VELOCITY, _PERIOD_MS
from test_goto_target_behind import PROFILES
from test_pose_estimator import (
    ENCODERS_ONLY,
    GYRO_ONLY,
    OPTICAL,
    PER_HOUR,
    Rig,
    lib as estimator_lib,  # noqa: F401 -- used as a fixture
)

DEG = math.pi / 180.0
CHORD = 400.0  # [mm]
ARRIVE = 1.0   # [mm]
TIMEOUT_MS = 20000
LANDING = 0.5  # [deg] on truth


def _wrap(angle):
    return math.atan2(math.sin(angle), math.cos(angle))


def _target(bearing_deg):
    b = bearing_deg * DEG
    return CHORD * math.cos(b), CHORD * math.sin(b)


@pytest.fixture
def lib(estimator_lib):
    lib = estimator_lib
    vp, f, u, i = ctypes.c_void_p, ctypes.c_float, ctypes.c_uint32, ctypes.c_int
    lib.peBeginKernel.argtypes = [vp, f, f]
    lib.peSetLimits.argtypes = [vp, f, f, f, f]
    lib.peGoToW.argtypes = [vp, f, f, f, f, u]
    lib.peRunMove.argtypes = [vp, f, u, u]
    lib.peRunMove.restype = u
    lib.peSetSampleEvery.argtypes = [vp, i]
    lib.peSetOmegaFloor.argtypes = [vp, f]
    lib.peSetPivotClosure.argtypes = [vp, i, u, f, f, f, i, u]
    lib.peSetSteering.argtypes = [vp, i, f, f, f, f]
    lib.pePivotCorrections.argtypes = [vp]
    lib.pePivotCorrections.restype = i
    lib.pePivotResidual.argtypes = [vp]
    lib.pePivotResidual.restype = f
    lib.pePivotTimedOut.argtypes = [vp]
    lib.pePivotTimedOut.restype = i
    lib.peMoveActive.argtypes = [vp]
    lib.peMoveActive.restype = i
    lib.peEndedByWrongWay.argtypes = [vp]
    lib.peEndedByWrongWay.restype = i
    lib.peWrongWayCount.argtypes = [vp]
    lib.peWrongWayCount.restype = u
    return lib


FINE_FLOOR = 10.0  # [deg/s] a sim plant has no stiction, so its floor can be low


def _rig(lib, config, slip=1.0, bias_per_hour=0.0, profile="open",
         floor=FINE_FLOOR, every=4):
    p = PROFILES[profile]
    rig = Rig(lib, config, slip)
    lib.peBeginKernel(rig.h, 100.0, _FULL_DUTY_VELOCITY)
    lib.peSetLimits(rig.h, p["accel"], p["decel"], p["v_max"], p["omega_max"])
    lib.peSetSampleEvery(rig.h, every)
    lib.peSetOmegaFloor(rig.h, floor)
    lib.peGyroBias(rig.h, bias_per_hour * PER_HOUR)
    return rig, p


def _go(lib, rig, p, bearing):
    x, y = _target(bearing)
    lib.peGoToW(rig.h, x, y, p["speed"], ARRIVE, TIMEOUT_MS)
    ticks = lib.peRunMove(rig.h, _FULL_DUTY_VELOCITY, _PERIOD_MS, 6000)
    assert ticks < 6000
    return x, y


def _truth_error(lib, rig, bearing):  # [deg]
    return _wrap(lib.peTruthHeading(rig.h) - bearing * DEG) / DEG


@pytest.mark.parametrize("config", [OPTICAL, GYRO_ONLY])
@pytest.mark.parametrize("profile", ["open", "closed"])
@pytest.mark.parametrize("bias", [0.0, 150.0, -150.0])
@pytest.mark.parametrize("slip", [1.0, 1.03, 1.05, 0.95])
@pytest.mark.parametrize("bearing", [60, -90, 135, 180, -180, -170])
def test_pivot_lands_on_truth_under_slip_and_bias(
        lib, config, profile, bias, slip, bearing):
    rig, p = _rig(lib, config, slip, bias, profile)
    try:
        x, y = _go(lib, rig, p, bearing)
        assert lib.peWrongWayCount(rig.h) == 0
        assert abs(_truth_error(lib, rig, bearing)) < LANDING
        assert lib.pePivotCorrections(rig.h) <= 3
        assert not lib.pePivotTimedOut(rig.h)
        miss = math.hypot(lib.peTruthX(rig.h) - x, lib.peTruthY(rig.h) - y)
        assert miss < 15.0
    finally:
        rig.close()


@pytest.mark.parametrize("bearing", [60, 135, 180, -170])
def test_default_floor_lands_within_two_ticks_of_floor_travel(lib, bearing):
    rig, p = _rig(lib, GYRO_ONLY, 1.05, 150.0, floor=20.0)
    try:
        _go(lib, rig, p, bearing)
        assert abs(_truth_error(lib, rig, bearing)) < 1.0
    finally:
        rig.close()


@pytest.mark.parametrize("slip", [1.0, 1.05])
def test_encoders_only_is_unchanged(lib, slip):
    results = []
    for enabled in (0, 1):
        rig, p = _rig(lib, ENCODERS_ONLY, slip)
        try:
            lib.peSetPivotClosure(rig.h, enabled, 250, 0.25, 45.0, 1.0, 3, 2500)
            x, y = _target(120)
            lib.peGoToW(rig.h, x, y, p["speed"], ARRIVE, TIMEOUT_MS)
            ticks = lib.peRunMove(rig.h, _FULL_DUTY_VELOCITY, _PERIOD_MS, 6000)
            assert lib.pePivotCorrections(rig.h) == 0
            results.append((ticks, lib.peTruthX(rig.h), lib.peTruthY(rig.h),
                            lib.peTruthHeading(rig.h)))
        finally:
            rig.close()
    assert results[0] == results[1]


def test_slip_without_closure_misses_so_the_closure_is_what_lands_it(lib):
    rig, p = _rig(lib, GYRO_ONLY, 1.05)
    try:
        lib.peSetPivotClosure(rig.h, 0, 250, 0.25, 45.0, 1.0, 3, 2500)
        lib.peSetSteering(rig.h, 0, 150.0, 4.0, 20.0, 0.15)
        _go(lib, rig, p, 120)
        assert abs(_truth_error(lib, rig, 120)) > 3.0
    finally:
        rig.close()


def test_correction_count_is_capped(lib):
    rig, p = _rig(lib, GYRO_ONLY, 1.05)
    try:
        lib.peSetPivotClosure(rig.h, 1, 250, 0.0001, 45.0, 1.0, 1, 2500)
        _go(lib, rig, p, 150)
        assert lib.pePivotCorrections(rig.h) == 1
        assert not lib.peEndedByWrongWay(rig.h)
    finally:
        rig.close()


def test_timeout_gives_up_and_drives_the_straight(lib):
    rig, p = _rig(lib, GYRO_ONLY, 1.05)
    try:
        lib.peSetPivotClosure(rig.h, 1, 250, 0.25, 45.0, 1.0, 3, 100)
        x, y = _go(lib, rig, p, 120)
        assert lib.pePivotTimedOut(rig.h) == 1
        assert lib.pePivotCorrections(rig.h) == 0
        assert not lib.peEndedByWrongWay(rig.h)
        assert math.hypot(lib.peTruthX(rig.h), lib.peTruthY(rig.h)) > 0.8 * CHORD
    finally:
        rig.close()


@pytest.mark.parametrize("fault", ["peGyroReadFail", "peGyroDropout"])
@pytest.mark.parametrize("bearing", [90, -135])
def test_sensor_dropout_mid_pivot_does_not_step_the_heading(lib, fault, bearing):
    getattr(lib, fault).argtypes = [ctypes.c_void_p, ctypes.c_int]
    rig, p = _rig(lib, GYRO_ONLY, 1.05, every=1)
    try:
        x, y = _target(bearing)
        lib.peGoToW(rig.h, x, y, p["speed"], ARRIVE, TIMEOUT_MS)
        previous = lib.peHeading(rig.h)
        previous_truth = lib.peTruthHeading(rig.h)
        worst = 0.0
        for tick in range(6000):
            if tick == 15:
                getattr(lib, fault)(rig.h, 1)
            lib.peRunMove(rig.h, _FULL_DUTY_VELOCITY, _PERIOD_MS, 1)
            heading = lib.peHeading(rig.h)
            truth = lib.peTruthHeading(rig.h)
            worst = max(worst, abs((heading - previous) - (truth - previous_truth)))
            previous, previous_truth = heading, truth
            if not lib.peMoveActive(rig.h):
                break
        assert not lib.peMoveActive(rig.h)
        assert worst < 0.3 * DEG
        assert lib.peWrongWayCount(rig.h) == 0
        assert lib.pePivotTimedOut(rig.h) == 0
    finally:
        rig.close()

