"""tests/host/test_pose_estimator_latency.py -- the in-motion gyro gate
(src/motion/pose_estimator.h, sprint 044 ticket 012): a gyro that lags the
encoders at pivot ends, or a robot whose wheels slip, must not leave the
encoders' heading baked into the estimate.

Reads come every 4th 25 ms tick (10 Hz), as on the robot.

Run with::

    uv run pytest tests/host/test_pose_estimator_latency.py
"""

import math

import pytest

from test_pose_estimator import (  # noqa: F401
    DEG,
    GYRO_ONLY,
    OPTICAL,
    PER_HOUR,
    lib,
    make,
)

TICK = 0.025  # [s]
PIVOTS = [90, -45, 180, -90, 135, -180, 45, 90, -135, 180,
          -45, 90, -180, 135, -90, 45, -135, 90, -90, 180]  # [deg]
RATE = 120.0  # [deg/s]


def pivot_run(lib, make, config, latency, slip, old_gate=False):
    rig = make(config, track_error=slip,
               max_plausible_rate=0.0 if old_gate else None)
    lib.peGyroLatency(rig.h, latency)
    lib.peGyroBias(rig.h, 150.0 * PER_HOUR)
    rig.still(3.0, dt=TICK)
    for angle in PIVOTS:
        rig.spin(abs(angle) / RATE, math.copysign(RATE, angle), dt=TICK)
        rig.still(1.0, dt=TICK)
    return rig


@pytest.mark.parametrize("config", [OPTICAL, GYRO_ONLY])
@pytest.mark.parametrize("latency", [0.1, 0.2])  # [s]
@pytest.mark.parametrize("slip", [0.95, 1.05])
def test_twenty_pivots_with_lag_and_slip_end_on_truth_with_no_steps(
        lib, make, config, latency, slip):
    rig = pivot_run(lib, make, config, latency, slip)
    assert abs(rig.error) < 0.5 * DEG
    assert lib.peSteps(rig.h) == 0


@pytest.mark.parametrize("slip", [0.95, 1.05])
def test_the_pre_fix_gate_bakes_the_encoders_slip(lib, make, slip):
    old = pivot_run(lib, make, GYRO_ONLY, 0.1, slip, old_gate=True)
    new = pivot_run(lib, make, GYRO_ONLY, 0.1, slip)
    assert lib.peSteps(old.h) > 0
    assert abs(old.error) > 2.0 * DEG
    assert abs(new.error) < 0.5 * DEG


@pytest.mark.parametrize("config", [OPTICAL, GYRO_ONLY])
def test_a_ten_degree_glitch_in_a_pivot_is_rejected_and_not_taken(lib, make, config):
    rig = make(config)
    rig.still(3.0, dt=0.01)
    rig.spin(0.5, 60.0, dt=0.01, every=1)
    before = rig.error
    lib.peGyroGlitch(rig.h, 10.0 * DEG)
    rig.spin(0.5, 60.0, dt=0.01, every=1)
    assert lib.peRejected(rig.h) > 0
    assert abs(rig.error - before) < 1.0 * DEG
    rig.spin(0.5, 60.0, dt=0.01, every=1)
    assert lib.peSteps(rig.h) == 1
    assert abs(rig.error) < 1.0 * DEG
