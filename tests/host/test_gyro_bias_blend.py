"""tests/host/test_gyro_bias_blend.py -- GyroBiasTracker's blend of the rest
and motion observations (src/motion/gyro_bias_tracker.h, sprint 044 ticket
013): a motion fit corrupted by encoder slip must not drown the rest rate.

Run with::

    uv run pytest tests/host/test_gyro_bias_blend.py
"""

import pytest

from test_pose_estimator import (  # noqa: F401
    GYRO_ONLY,
    OPTICAL,
    PER_HOUR,
    lib,
    make,
)


def legs(rig, count, slip):
    for k in range(count):
        sign = 1.0 if k % 2 == 0 else -1.0
        rig.lib.peSetTrackError(rig.h, slip if sign > 0 else 1.0 / slip)
        rig.spin(1.5, sign * 60.0)
        rig.drive(2.0, 200.0, 200.0)


@pytest.mark.parametrize("config", [OPTICAL, GYRO_ONLY])
@pytest.mark.parametrize("slip", [0.95, 1.05, 1.1])
def test_rest_after_slipping_legs_brings_the_rate_to_truth(lib, make, config, slip):
    rig = make(config)
    lib.peGyroBias(rig.h, 30.0 * PER_HOUR)
    legs(rig, 50, slip)
    rig.still(300.0)
    assert lib.peBiasRate(rig.h) == pytest.approx(30.0 * PER_HOUR,
                                                  abs=3.0 * PER_HOUR)


def test_a_gyro_only_robot_driving_without_rest_still_learns_the_bias(lib, make):
    rig = make(GYRO_ONLY, track_error=1.02)
    lib.peGyroBias(rig.h, 50.0 * PER_HOUR)
    for _ in range(100):
        rig.spin(3.0, 60.0)
        rig.spin(3.0, -60.0)
    assert lib.peBiasRate(rig.h) == pytest.approx(50.0 * PER_HOUR,
                                                  abs=10.0 * PER_HOUR)
