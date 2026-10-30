"""tests/host/test_goto_target_behind.py -- sprint 044 ticket 006.

A GO_TO target behind the robot is reached by pivoting to its bearing and
driving forward, never by reversing. A wrong-way abort ends with its own
`wrongway` done reason instead of `stop`.

Run with::

    uv run pytest tests/host/test_goto_target_behind.py
"""

import ctypes
import math

import pytest

from test_goto_block_regression import (
    ProbeEngine,
    _FULL_DUTY_VELOCITY,
    _LANDING_TOLERANCE_MM,
    _PERIOD_MS,
    _PROBE_TIMEOUT_MS,
    _ready,
)
from test_motion_engine_reductions import Engine, LEFT, RIGHT, _ready as _engine_ready
from test_pose_estimator import (
    ENCODERS_ONLY,
    GYRO_ONLY,
    OPTICAL,
    Rig,
    lib as estimator_lib,  # noqa: F401 -- used as a fixture
)

_ARC_TOLERANCE = 15.0  # [mm] unchanged blended-arc path, 13.5 mm at +-10 deg closed
CHORD = 600.0  # [mm]
ARRIVE = 1.0   # [mm]
DEG = math.pi / 180.0

PROFILES = {
    "open": dict(accel=400.0, decel=400.0, v_max=200.0, omega_max=90.0, speed=200.0),
    "closed": dict(accel=600.0, decel=500.0, v_max=400.0, omega_max=120.0, speed=400.0),
}

BEHIND = [170, 172, 175, 177, 179, 180]
BEARINGS = sorted({s * b for b in BEHIND for s in (1, -1)} | {
    -165, -160, -150, -120, -100, -91, -89, -60, -30, -10, 0,
    10, 30, 60, 89, 91, 100, 120, 150, 160, 165,
})


def _wrap(angle):
    return math.atan2(math.sin(angle), math.cos(angle))


def _target(bearing_deg):
    b = bearing_deg * DEG
    return CHORD * math.cos(b), CHORD * math.sin(b)


def _apply_profile(lib, e, profile):
    p = PROFILES[profile]
    lib.meLimitsSetAccel(e._handle, p["accel"])
    lib.meLimitsSetDecel(e._handle, p["decel"])
    lib.meLimitsSetVMax(e._handle, p["v_max"])
    lib.meLimitsSetOmegaMax(e._handle, p["omega_max"])
    return p["speed"]


@pytest.mark.parametrize("bearing", [b for b in BEARINGS if abs(b) > 90])
def test_target_behind_always_splits(motion_lib, bearing):
    x, y = _target(bearing)
    assert motion_lib.meDecomposeGoToRWillSplit(x, y) == 1
    raw = motion_lib.meDecomposeGoToRBearingRaw(x, y)
    assert abs(_wrap(raw - bearing * DEG)) < 1e-3
    assert motion_lib.meDecomposeGoToRChord(x, y) == pytest.approx(CHORD, rel=1e-4)


@pytest.mark.parametrize("sign", [1.0, -1.0])
def test_target_dead_behind_splits_with_a_half_turn_pivot(motion_lib, sign):
    assert motion_lib.meDecomposeGoToRWillSplit(-CHORD, 0.0) == 1
    assert abs(motion_lib.meDecomposeGoToRBearingRaw(-CHORD, 0.0)) == pytest.approx(math.pi)


@pytest.mark.parametrize("bearing", [b for b in BEARINGS if abs(b) <= 90])
def test_forward_targets_decompose_as_before(motion_lib, bearing):
    x, y = _target(bearing)
    theta = _wrap(2.0 * math.atan2(y, x))
    expected = abs(theta) >= 50.0 * DEG
    assert bool(motion_lib.meDecomposeGoToRWillSplit(x, y)) == expected


@pytest.mark.parametrize("profile", sorted(PROFILES))
@pytest.mark.parametrize("bearing", BEARINGS)
def test_sweep_goto_w_pivots_then_drives_forward(motion_lib, bearing, profile):
    x, y = _target(bearing)
    with ProbeEngine(motion_lib) as e:
        _ready(e)
        speed = _apply_profile(motion_lib, e, profile)
        motion_lib.mePoseSourceSetPose(e._handle, 0.0, 0.0, 0.0)
        motion_lib.meGoToW(e._handle, x, y, speed, ARRIVE, _PROBE_TIMEOUT_MS)
        e.run_to_completion()

        assert e.wrong_way_count() == 0
        assert not motion_lib.meLastSegmentEndedByWrongWay(e._handle)
        tolerance = _ARC_TOLERANCE if abs(bearing) < 25 else _LANDING_TOLERANCE_MM
        assert math.hypot(e.probe_x() - x, e.probe_y() - y) < tolerance
        if abs(bearing) > 25:
            assert abs(_wrap(e.probe_heading() - bearing * DEG)) < 3.0 * DEG


def test_wrong_way_abort_latches_its_own_reason(motion_lib):
    with Engine(motion_lib) as e:
        _engine_ready(e)
        e.move_x(0.0, 90.0 * DEG, 100.0, 5000)
        e.step()
        e.service_move()
        assert not motion_lib.meLastSegmentEndedByWrongWay(e._handle)
        e.arm_motor_position(LEFT, 1000.0)
        e.arm_motor_position(RIGHT, -1000.0)
        e.step()

        assert not e.service_move()
        assert e.wrong_way_count() == 1
        assert motion_lib.meLastSegmentEndedByWrongWay(e._handle)


def test_wrong_way_latch_clears_when_the_next_segment_starts(motion_lib):
    with Engine(motion_lib) as e:
        _engine_ready(e)
        e.move_x(0.0, 90.0 * DEG, 100.0, 5000)
        e.step()
        e.service_move()
        e.arm_motor_position(LEFT, 1000.0)
        e.arm_motor_position(RIGHT, -1000.0)
        e.step()
        e.service_move()
        assert motion_lib.meLastSegmentEndedByWrongWay(e._handle)

        e.move_x(100.0, 0.0, 100.0, 5000)
        assert not motion_lib.meLastSegmentEndedByWrongWay(e._handle)


@pytest.fixture
def est(estimator_lib):
    lib = estimator_lib
    vp, f, u, i = ctypes.c_void_p, ctypes.c_float, ctypes.c_uint32, ctypes.c_int
    lib.peBeginKernel.argtypes = [vp, f, f]
    lib.peSetLimits.argtypes = [vp, f, f, f, f]
    lib.peGoToW.argtypes = [vp, f, f, f, f, u]
    lib.peRunMove.argtypes = [vp, f, u, u]
    lib.peRunMove.restype = u
    lib.peEndedByWrongWay.argtypes = [vp]
    lib.peEndedByWrongWay.restype = i
    lib.peWrongWayCount.argtypes = [vp]
    lib.peWrongWayCount.restype = u
    return lib


@pytest.mark.parametrize("config", [OPTICAL, GYRO_ONLY, ENCODERS_ONLY])
@pytest.mark.parametrize("profile", sorted(PROFILES))
@pytest.mark.parametrize("bearing", [-180, -177, -170, -100, -30, 0, 30, 100, 170, 177, 180])
def test_estimator_goto_w_target_behind_in_every_configuration(
        est, config, profile, bearing):
    lib = est
    x, y = _target(bearing)
    p = PROFILES[profile]
    rig = Rig(lib, config)
    try:
        lib.peBeginKernel(rig.h, 100.0, _FULL_DUTY_VELOCITY)
        lib.peSetLimits(rig.h, p["accel"], p["decel"], p["v_max"], p["omega_max"])
        lib.peGoToW(rig.h, x, y, p["speed"], ARRIVE, _PROBE_TIMEOUT_MS)
        ticks = lib.peRunMove(rig.h, _FULL_DUTY_VELOCITY, _PERIOD_MS, 4000)

        assert ticks < 4000
        assert lib.peWrongWayCount(rig.h) == 0
        assert not lib.peEndedByWrongWay(rig.h)
        miss = math.hypot(lib.peTruthX(rig.h) - x, lib.peTruthY(rig.h) - y)
        assert miss < _LANDING_TOLERANCE_MM
        if abs(bearing) > 25:
            heading = lib.peTruthHeading(rig.h)
            assert abs(_wrap(heading - bearing * DEG)) < 3.0 * DEG
    finally:
        rig.close()
