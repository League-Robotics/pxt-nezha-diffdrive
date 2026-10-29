"""tests/host/test_pose_estimator.py -- PoseEstimator and GyroBiasTracker
(src/motion/pose_estimator.h, gyro_bias_tracker.h; sprint 044 ticket 002)
in all three sensor configurations, driven by SimGyro / SimOptical and
scripted wheel speeds through pose_estimator_shim.cpp.

The shim moves a true robot; its encoders are exact unless a test sets a
track-width error, so heading error is always `estimator - truth`.

Run with::

    uv run pytest tests/host/test_pose_estimator.py
"""

import ctypes
import math
import pathlib

import pytest

from test_kernel_harness import compile_shared_lib
from test_odometry import (
    _ABS,
    _GOLDEN_FRAMES,
    _REL,
    _ROTATIONAL_SLIP,
    _TRACK_WIDTH,
    _TRAVEL_CALIB,
    _WHEEL_PATH,
)

_TEST_DIR = pathlib.Path(__file__).resolve().parent
_SRC_DIR = _TEST_DIR.parent.parent / "src"

OPTICAL, GYRO_ONLY, ENCODERS_ONLY = 0, 1, 2
DEG = math.pi / 180.0
PER_HOUR = DEG / 3600.0  # [rad/s] per deg/h

_SHIM_SOURCES = [
    _SRC_DIR / "core" / "diffdrive.cpp",
    _SRC_DIR / "motion" / "motion_engine.cpp",
    _SRC_DIR / "motion" / "velocity_shaper.cpp",
    _TEST_DIR / "pose_estimator_shim.cpp",
]

SENSOR_CONFIGS = [OPTICAL, GYRO_ONLY]


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    lib_path = compile_shared_lib(
        tmp_path_factory,
        sources=_SHIM_SOURCES,
        out_name="libpose_estimator_shim.so",
    )
    loaded = ctypes.CDLL(str(lib_path))
    vp, f, i, u = ctypes.c_void_p, ctypes.c_float, ctypes.c_int, ctypes.c_uint32
    loaded.peCreate.restype = vp
    loaded.peDestroy.argtypes = [vp]
    loaded.peSetGeometry.argtypes = [vp, f, f, f]
    loaded.peSetTrackError.argtypes = [vp, f]
    loaded.peAttach.argtypes = [vp, i]
    for name in ("peGyroBias", "peGyroNoise", "peGyroStep", "peGyroGlitch",
                 "peOpticalScale"):
        getattr(loaded, name).argtypes = [vp, f]
    loaded.peGyroWander.argtypes = [vp, f, f]
    loaded.peGyroSeed.argtypes = [vp, u]
    for name in ("peGyroDropout", "peGyroFreeze", "peGyroReadFail",
                 "peOpticalFreeze", "peOpticalDropout"):
        getattr(loaded, name).argtypes = [vp, i]
    loaded.peOpticalJump.argtypes = [vp, f, f]
    loaded.peDrive.argtypes = [vp, f, f, f, i]
    loaded.peOutput.argtypes = [vp, f, f, f, u, u]
    loaded.peSeed.argtypes = [vp, f, f, f]
    loaded.peReset.argtypes = [vp]
    loaded.peReprime.argtypes = [vp]
    for name in ("peX", "peY", "peHeading", "pePoseSourceX", "peBiasRate",
                 "peTruthX", "peTruthY", "peTruthHeading", "peTrueBias"):
        getattr(loaded, name).argtypes = [vp]
        getattr(loaded, name).restype = f
    for name in ("peConfig", "peAtRest"):
        getattr(loaded, name).argtypes = [vp]
        getattr(loaded, name).restype = i
    for name in ("peRejected", "peSteps"):
        getattr(loaded, name).argtypes = [vp]
        getattr(loaded, name).restype = u
    return loaded


class Rig:
    def __init__(self, lib, config, track_error=1.0):
        self.lib = lib
        self.h = lib.peCreate()
        lib.peSetGeometry(self.h, _TRAVEL_CALIB, _TRACK_WIDTH, _ROTATIONAL_SLIP)
        lib.peSetTrackError(self.h, track_error)
        lib.peAttach(self.h, config)

    def close(self):
        self.lib.peDestroy(self.h)

    def drive(self, seconds, left, right, dt=0.01, every=4, ramp=None):
        steps = int(round(seconds / dt))
        for k in range(steps):
            if ramp is not None:
                self.lib.peGyroBias(self.h, ramp(k * dt))
            self.lib.peDrive(self.h, dt, left, right, 1 if k % every == 0 else 0)

    def still(self, seconds, dt=0.01, every=4, ramp=None):
        self.drive(seconds, 0.0, 0.0, dt, every, ramp)

    def spin(self, seconds, rate_deg, dt=0.01, every=4):
        half = rate_deg * DEG * _TRACK_WIDTH / 2.0  # [mm/s] per wheel
        self.drive(seconds, -half, half, dt, every)

    def swing(self, cycles, amplitude_deg=40.0, rate_deg=60.0):
        for _ in range(cycles):
            seconds = amplitude_deg / rate_deg
            self.spin(seconds, rate_deg)
            self.still(0.5)
            self.spin(seconds, -rate_deg)
            self.still(0.5)

    @property
    def error(self):  # [rad] heading error against truth
        return self.lib.peHeading(self.h) - self.lib.peTruthHeading(self.h)

    @property
    def position_error(self):  # [mm]
        return math.hypot(self.lib.peX(self.h) - self.lib.peTruthX(self.h),
                          self.lib.peY(self.h) - self.lib.peTruthY(self.h))


@pytest.fixture
def make(lib):
    rigs = []

    def build(config, track_error=1.0):
        rig = Rig(lib, config, track_error)
        rigs.append(rig)
        return rig

    yield build
    for rig in rigs:
        rig.close()


def test_encoders_only_matches_the_odometry_goldens(lib, make):
    rig = make(ENCODERS_ONLY)
    for (left, right), golden in zip(_WHEEL_PATH, _GOLDEN_FRAMES):
        lib.peOutput(rig.h, 0.01, left, right, 0, 0)
        frame = (lib.peX(rig.h), lib.peY(rig.h), lib.peHeading(rig.h))
        assert frame == pytest.approx(golden, rel=_REL, abs=_ABS)
    assert lib.pePoseSourceX(rig.h) == lib.peX(rig.h)
    assert lib.peConfig(rig.h) == ENCODERS_ONLY


def test_encoders_only_holds_a_rebase_like_odometry(lib, make):
    rig = make(ENCODERS_ONLY)
    lib.peOutput(rig.h, 0.01, 0.0, 0.0, 0, 0)
    lib.peOutput(rig.h, 0.01, 1250.0, 1250.0, 0, 0)
    lib.peOutput(rig.h, 0.01, 5000.0, -5000.0, 1, 1)
    assert lib.peX(rig.h) == pytest.approx(100.0, abs=_ABS)
    assert lib.peHeading(rig.h) == 0.0


def test_seed_sets_the_pose_and_reset_zeroes_it(lib, make):
    rig = make(GYRO_ONLY)
    rig.drive(1.0, 100.0, 100.0)
    lib.peSeed(rig.h, 500.0, -200.0, 1.0)
    assert (lib.peX(rig.h), lib.peY(rig.h), lib.peHeading(rig.h)) == (
        pytest.approx((500.0, -200.0, 1.0)))
    lib.peReset(rig.h)
    assert (lib.peX(rig.h), lib.peY(rig.h), lib.peHeading(rig.h)) == (0.0, 0.0, 0.0)


@pytest.mark.parametrize("config", SENSOR_CONFIGS)
def test_constant_bias_is_learned_and_removed_at_rest(lib, make, config):
    rig = make(config)
    lib.peGyroBias(rig.h, 50.0 * PER_HOUR)
    rig.still(300.0)
    assert abs(rig.error) < 0.1 * DEG
    assert lib.peBiasRate(rig.h) == pytest.approx(50.0 * PER_HOUR,
                                                  abs=5.0 * PER_HOUR)


@pytest.mark.parametrize("config", SENSOR_CONFIGS)
def test_constant_bias_is_removed_in_motion(lib, make, config):
    rig = make(config)
    lib.peGyroBias(rig.h, 50.0 * PER_HOUR)
    rig.still(120.0)
    start = rig.error
    uncorrected = 50.0 * PER_HOUR * 300.0
    rig.swing(30)
    assert uncorrected > 4.0 * DEG
    assert abs(rig.error - start) < 0.3 * DEG


@pytest.mark.parametrize("config", SENSOR_CONFIGS)
@pytest.mark.parametrize("noise,track_error", [(0.0, 1.0), (0.6 * DEG, 1.02)])
def test_constant_bias_is_learned_from_motion_alone(lib, make, config, noise,
                                                    track_error):
    rig = make(config, track_error)
    lib.peGyroNoise(rig.h, noise)
    lib.peGyroSeed(rig.h, 1)
    lib.peGyroBias(rig.h, 50.0 * PER_HOUR)
    rig.swing(240)
    uncorrected = 50.0 * PER_HOUR * 12.0 * 240.0 / 3.0
    assert uncorrected > 10.0 * DEG
    assert abs(rig.error) < 2.0 * DEG
    assert lib.peBiasRate(rig.h) == pytest.approx(50.0 * PER_HOUR,
                                                  abs=15.0 * PER_HOUR)


def stationary_run(rig, lib, ramp, seconds=1800.0, settle=120.0, dt=0.05,
                   noise=0.3 * DEG):
    lib.peGyroNoise(rig.h, noise)
    lib.peGyroSeed(rig.h, 12345)
    rig.still(settle, dt=dt, every=1, ramp=ramp)
    reference = rig.error
    worst = 0.0
    chunk = 60.0
    for k in range(int((seconds - settle) / chunk)):
        t0 = settle + k * chunk
        rig.still(chunk, dt=dt, every=1, ramp=lambda t, t0=t0: ramp(t0 + t))
        worst = max(worst, abs(rig.error - reference))
    return worst


STATIONARY_BIASES = {
    "50 deg/h constant": lambda t: 50.0 * PER_HOUR,
    "ramp 0 to +35 deg/h": lambda t: 35.0 * PER_HOUR * t / 1800.0,
    "ramp 0 to -35 deg/h": lambda t: -35.0 * PER_HOUR * t / 1800.0,
    "150 deg/h constant": lambda t: 150.0 * PER_HOUR,
    "-150 deg/h constant": lambda t: -150.0 * PER_HOUR,
}


@pytest.mark.parametrize("config", SENSOR_CONFIGS)
@pytest.mark.parametrize("name", list(STATIONARY_BIASES))
def test_thirty_minutes_still_holds_heading_within_two_degrees(lib, make, config,
                                                               name):
    rig = make(config)
    worst = stationary_run(rig, lib, STATIONARY_BIASES[name])
    assert worst < 2.0 * DEG
    assert rig.position_error < 5.0


@pytest.mark.parametrize("config", SENSOR_CONFIGS)
def test_a_ramping_bias_is_tracked_closely_enough_to_move_on(lib, make, config):
    ramp = STATIONARY_BIASES["ramp 0 to +35 deg/h"]
    rig = make(config)
    stationary_run(rig, lib, ramp, noise=0.0)
    truth = lib.peTrueBias(rig.h)
    assert lib.peBiasRate(rig.h) == pytest.approx(truth, abs=6.0 * PER_HOUR)


@pytest.mark.parametrize("config", SENSOR_CONFIGS)
def test_a_one_sample_glitch_leaves_no_persistent_offset(lib, make, config):
    rig = make(config, track_error=1.02)
    lib.peGyroBias(rig.h, 50.0 * PER_HOUR)
    rig.swing(3)
    before = rig.error
    rejected = lib.peRejected(rig.h)
    lib.peGyroGlitch(rig.h, 12.0 * DEG)
    rig.spin(0.01, 30.0, every=1)
    lib.peGyroGlitch(rig.h, 0.0)
    rig.spin(2.0, 30.0)
    assert lib.peRejected(rig.h) > rejected
    assert lib.peSteps(rig.h) == 0
    assert abs(rig.error - before) < 1.0 * DEG
    rig.swing(5)
    assert abs(rig.error - before) < 1.0 * DEG


@pytest.mark.parametrize("config", SENSOR_CONFIGS)
def test_a_gyro_step_while_turning_is_taken_as_the_new_reference(lib, make, config):
    rig = make(config)
    rig.swing(2)
    before = rig.error
    rig.spin(0.5, 40.0, every=1)
    lib.peGyroStep(rig.h, 25.0 * DEG)
    rig.spin(1.0, 40.0, every=1)
    assert lib.peSteps(rig.h) == 1
    assert abs(rig.error - before) < 1.0 * DEG
    assert abs(lib.peBiasRate(rig.h)) < 5.0 * PER_HOUR


@pytest.mark.parametrize("config", SENSOR_CONFIGS)
def test_a_gyro_step_at_rest_is_not_folded_into_the_bias(lib, make, config):
    rig = make(config)
    lib.peGyroBias(rig.h, 40.0 * PER_HOUR)
    rig.still(120.0)
    before = rig.error
    lib.peGyroStep(rig.h, -0.6 * DEG)
    rig.still(120.0)
    assert abs(rig.error - before) < 0.1 * DEG
    assert lib.peBiasRate(rig.h) == pytest.approx(40.0 * PER_HOUR,
                                                  abs=5.0 * PER_HOUR)


def run_transition(rig, lib, impair, expect, bias=50.0):
    lib.peGyroBias(rig.h, bias * PER_HOUR)
    rig.still(60.0)
    rig.drive(2.0, 150.0, 200.0)
    before = rig.error
    before_position = rig.position_error
    impair()
    worst = 0.0
    worst_position = 0.0
    for _ in range(40):
        rig.drive(0.1, 150.0, 200.0, every=1)
        worst = max(worst, abs(rig.error - before))
        worst_position = max(worst_position, abs(rig.position_error - before_position))
    rig.drive(10.0, 150.0, 200.0, every=1)
    assert lib.peConfig(rig.h) == expect
    assert worst < 1.0 * DEG
    assert worst_position < 60.0


TRANSITIONS = [
    ("optical freeze", OPTICAL, lambda l, h: l.peOpticalFreeze(h, 1), GYRO_ONLY),
    ("optical dropout", OPTICAL, lambda l, h: l.peOpticalDropout(h, 1), GYRO_ONLY),
    ("optical jump", OPTICAL, lambda l, h: l.peOpticalJump(h, 300.0, -200.0),
     OPTICAL),
    ("gyro freeze from optical", OPTICAL, lambda l, h: l.peGyroFreeze(h, 1),
     ENCODERS_ONLY),
    ("gyro dropout from optical", OPTICAL, lambda l, h: l.peGyroDropout(h, 1),
     ENCODERS_ONLY),
    ("gyro read failure from optical", OPTICAL,
     lambda l, h: l.peGyroReadFail(h, 1), ENCODERS_ONLY),
    ("gyro freeze", GYRO_ONLY, lambda l, h: l.peGyroFreeze(h, 1), ENCODERS_ONLY),
    ("gyro dropout", GYRO_ONLY, lambda l, h: l.peGyroDropout(h, 1),
     ENCODERS_ONLY),
    ("gyro read failure", GYRO_ONLY, lambda l, h: l.peGyroReadFail(h, 1),
     ENCODERS_ONLY),
]


@pytest.mark.parametrize("name,start,impair,expect", TRANSITIONS,
                         ids=[t[0] for t in TRANSITIONS])
def test_a_sensor_lost_mid_run_degrades_without_a_heading_step(
        lib, make, name, start, impair, expect):
    rig = make(start)
    run_transition(rig, lib, lambda: impair(lib, rig.h), expect)


@pytest.mark.parametrize("start,impair,clear", [
    (OPTICAL, "peGyroDropout", "peGyroDropout"),
    (GYRO_ONLY, "peGyroReadFail", "peGyroReadFail"),
    (GYRO_ONLY, "peGyroFreeze", "peGyroFreeze"),
    (OPTICAL, "peOpticalDropout", "peOpticalDropout"),
])
def test_a_returning_sensor_rejoins_without_a_step(lib, make, start, impair, clear):
    rig = make(start)
    lib.peGyroBias(rig.h, 50.0 * PER_HOUR)
    rig.still(60.0)
    rig.drive(2.0, 150.0, 200.0, every=1)
    getattr(lib, impair)(rig.h, 1)
    rig.drive(8.0, 150.0, 200.0, every=1)
    assert lib.peConfig(rig.h) != start
    before = rig.error
    getattr(lib, clear)(rig.h, 0)
    worst = 0.0
    for _ in range(60):
        rig.drive(0.1, 150.0, 200.0, every=1)
        worst = max(worst, abs(rig.error - before))
    assert lib.peConfig(rig.h) == start
    assert worst < 1.0 * DEG


def test_a_gyro_that_is_never_there_is_encoders_only(lib, make):
    rig = make(ENCODERS_ONLY)
    lib.peGyroBias(rig.h, 500.0 * PER_HOUR)
    rig.still(60.0)
    rig.spin(2.0, 45.0)
    assert lib.peConfig(rig.h) == ENCODERS_ONLY
    assert rig.error == pytest.approx(0.0, abs=1e-4)


def test_optical_position_beats_encoders_on_a_miscalibrated_track(lib, make):
    errors = {}
    for config in (OPTICAL, ENCODERS_ONLY):
        rig = make(config, track_error=1.03)
        lib.peGyroBias(rig.h, 40.0 * PER_HOUR)
        rig.still(60.0)
        for _ in range(10):
            rig.drive(4.0, 200.0, 200.0)
            rig.spin(1.5, 60.0)
        errors[config] = rig.position_error
    assert errors[OPTICAL] < errors[ENCODERS_ONLY] / 3.0
    assert errors[OPTICAL] < 20.0


def test_optical_position_follows_the_arm_corrected_centre(lib, make):
    rig = make(OPTICAL)
    lib.peGyroBias(rig.h, 50.0 * PER_HOUR)
    rig.still(60.0)
    for _ in range(6):
        rig.spin(1.5, 60.0)
        rig.drive(3.0, 150.0, 150.0)
    assert rig.position_error < 10.0
    assert abs(rig.error) < 0.5 * DEG


def test_gyro_only_position_runs_along_the_corrected_heading(lib, make):
    rig = make(GYRO_ONLY, track_error=1.03)
    lib.peGyroBias(rig.h, 40.0 * PER_HOUR)
    rig.still(60.0)
    for _ in range(10):
        rig.drive(4.0, 200.0, 200.0)
        rig.spin(1.5, 60.0)
    assert rig.position_error < 40.0


def test_still_robot_position_does_not_wander_on_optical_noise(lib, make):
    rig = make(OPTICAL)
    rig.drive(3.0, 150.0, 150.0)
    rig.still(1.0)
    x, y = lib.peX(rig.h), lib.peY(rig.h)
    lib.peOpticalJump(rig.h, 5.0, 5.0)
    rig.still(30.0)
    assert math.hypot(lib.peX(rig.h) - x, lib.peY(rig.h) - y) < 5.0


@pytest.mark.parametrize("config", SENSOR_CONFIGS)
def test_idle_reads_at_ten_hz_learn_the_bias_at_rest(lib, make, config):
    rig = make(config)
    lib.peGyroBias(rig.h, 40.0 * PER_HOUR)
    rig.still(300.0, every=10)
    assert lib.peBiasRate(rig.h) == pytest.approx(40.0 * PER_HOUR,
                                                  abs=5.0 * PER_HOUR)
    assert abs(rig.error) < 0.2 * DEG


@pytest.mark.parametrize("config", SENSOR_CONFIGS)
def test_reprime_after_a_reseed_takes_the_new_gyro_frame_without_a_step(
        lib, make, config):
    rig = make(config)
    rig.spin(1.0, 45.0)
    rig.still(1.0)
    steps = lib.peSteps(rig.h)
    rejected = lib.peRejected(rig.h)
    lib.peGyroStep(rig.h, 30.0 * DEG)
    lib.peSeed(rig.h, 0.0, 0.0, 0.5)
    lib.peReprime(rig.h)
    rig.still(2.0)
    assert lib.peHeading(rig.h) == pytest.approx(0.5, abs=0.2 * DEG)
    assert lib.peSteps(rig.h) == steps
    assert lib.peRejected(rig.h) == rejected
