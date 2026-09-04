"""tests/host/test_motion_engine_shaping_fields.py -- REWRITTEN sprint 029
ticket 003 (design docs/design/motion-profile-unification.md S4.1):
this file used to pin the thirteen individual MotionEngine shaping
fields (aAccelMmS2_/aDecelMmS2_/vMaxMmS_/brakeFrac_/distTaper_/
yawTaper_/distFloor_/turnFloor_/rampMs_/...), all of which ticket 003
DELETES. There is now exactly one settable shaping surface --
`MotionEngine::limits()`, returning a `MotionLimits&` (motion_limits.h)
-- and this file is the smoke test for it: every field defaults to a
real, positive fleet-bake value (no more "0 selects legacy mode"; design
S8: "now always active, no legacy mode"), round-trips a valid SET
through its own getter, and silently keeps the prior value on an
invalid SET (the same ">0, else keep prior" style
setPivotOverrunMm()/setRotationalSlip() already used, and that
MotionLimits' own setters (motion_limits.h) still use).

Covers:
  1. Every MotionLimits field defaults to its documented fleet-bake
     value (motion_limits.h's own field comments) -- accel/decel/vMax/
     vFloor are always positive now; jerk/omegaMax default to 0 (their
     own "off"/"none" value, not a mode switch).
  2. Each setter validates and round-trips through its own getter,
     exactly as motion_limits.h documents (">0, else keep" for
     accel/decel/vMax/arriveDist/arriveYaw; ">=0, else keep" for
     jerk/omegaMax/vFloor/omegaFloor/stopDistance, since 0 is a valid
     value for those five).

Run with::

    uv run pytest tests/host/test_motion_engine_shaping_fields.py
"""

import ctypes
import pathlib

import pytest

from test_kernel_harness import compile_shared_lib

_TEST_DIR = pathlib.Path(__file__).resolve().parent
_SRC_DIR = _TEST_DIR.parent.parent / "src"

_SHIM_SOURCES = [
    _SRC_DIR / "core" / "diffdrive.cpp",
    _SRC_DIR / "motion" / "motion_engine.cpp",
    _SRC_DIR / "motion" / "velocity_shaper.cpp",
    _TEST_DIR / "motion_engine_shim.cpp",
]

_GETTERS = (
    "meLimitsAccel", "meLimitsDecel", "meLimitsJerk", "meLimitsVMax",
    "meLimitsOmegaMax", "meLimitsVFloor", "meLimitsOmegaFloor",
    "meLimitsStopDistance", "meLimitsArriveDist", "meLimitsArriveYaw",
)
_SETTERS = (
    "meLimitsSetAccel", "meLimitsSetDecel", "meLimitsSetJerk",
    "meLimitsSetVMax", "meLimitsSetOmegaMax", "meLimitsSetVFloor",
    "meLimitsSetOmegaFloor", "meLimitsSetStopDistance",
    "meLimitsSetArriveDist", "meLimitsSetArriveYaw",
)


def _bind(lib):
    lib.meCreate.argtypes = []
    lib.meCreate.restype = ctypes.c_void_p
    lib.meDestroy.argtypes = [ctypes.c_void_p]
    lib.meDestroy.restype = None

    for getter in _GETTERS:
        fn = getattr(lib, getter)
        fn.argtypes = [ctypes.c_void_p]
        fn.restype = ctypes.c_float

    for setter in _SETTERS:
        fn = getattr(lib, setter)
        fn.argtypes = [ctypes.c_void_p, ctypes.c_float]
        fn.restype = None

    return lib


@pytest.fixture(scope="session")
def motion_lib(tmp_path_factory):
    lib_path = compile_shared_lib(
        tmp_path_factory, sources=_SHIM_SOURCES,
        out_name="libmotion_engine_shaping_fields_shim.so",
    )
    return _bind(ctypes.CDLL(str(lib_path)))


class Limits:
    """Thin Pythonic wrapper around one meCreate()/meDestroy() handle's
    MotionLimits surface (limits())."""

    def __init__(self, lib):
        self._lib = lib
        self._handle = lib.meCreate()

    def close(self):
        self._lib.meDestroy(self._handle)
        self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    def accel(self):
        return self._lib.meLimitsAccel(self._handle)

    def set_accel(self, v):
        self._lib.meLimitsSetAccel(self._handle, v)

    def decel(self):
        return self._lib.meLimitsDecel(self._handle)

    def set_decel(self, v):
        self._lib.meLimitsSetDecel(self._handle, v)

    def jerk(self):
        return self._lib.meLimitsJerk(self._handle)

    def set_jerk(self, v):
        self._lib.meLimitsSetJerk(self._handle, v)

    def v_max(self):
        return self._lib.meLimitsVMax(self._handle)

    def set_v_max(self, v):
        self._lib.meLimitsSetVMax(self._handle, v)

    def omega_max(self):
        return self._lib.meLimitsOmegaMax(self._handle)

    def set_omega_max(self, v):
        self._lib.meLimitsSetOmegaMax(self._handle, v)

    def v_floor(self):
        return self._lib.meLimitsVFloor(self._handle)

    def set_v_floor(self, v):
        self._lib.meLimitsSetVFloor(self._handle, v)

    def omega_floor(self):
        return self._lib.meLimitsOmegaFloor(self._handle)

    def set_omega_floor(self, v):
        self._lib.meLimitsSetOmegaFloor(self._handle, v)

    def stop_distance(self):
        return self._lib.meLimitsStopDistance(self._handle)

    def set_stop_distance(self, v):
        self._lib.meLimitsSetStopDistance(self._handle, v)

    def arrive_dist(self):
        return self._lib.meLimitsArriveDist(self._handle)

    def set_arrive_dist(self, v):
        self._lib.meLimitsSetArriveDist(self._handle, v)

    def arrive_yaw(self):
        return self._lib.meLimitsArriveYaw(self._handle)

    def set_arrive_yaw(self, v):
        self._lib.meLimitsSetArriveYaw(self._handle, v)


# ---- defaults: no field is inert at any speed (design S4.1) -------------


def test_defaults_are_the_fleet_bake_and_no_field_selects_legacy_mode(
        motion_lib):
    """motion_limits.h's own documented defaults. accel/decel/vMax/
    vFloor are ALWAYS positive -- there is no more "0 disables shaping"
    escape hatch (design S8: "now always active, no legacy mode").
    jerk/omegaMax default to 0, but that 0 is each field's own
    documented off/none value (design S4.1), not a global mode switch."""
    with Limits(motion_lib) as lim:
        assert lim.accel() == pytest.approx(400.0)
        assert lim.decel() == pytest.approx(400.0)
        assert lim.jerk() == pytest.approx(0.0)       # 0 = no jerk rounding
        assert lim.v_max() == pytest.approx(250.0)
        assert lim.omega_max() == pytest.approx(0.0)  # 0 = no cap
        assert lim.v_floor() == pytest.approx(70.0)
        assert lim.omega_floor() == pytest.approx(20.0)
        assert lim.stop_distance() == pytest.approx(0.0)
        assert lim.arrive_dist() == pytest.approx(1.0)
        assert lim.arrive_yaw() == pytest.approx(0.3)


# ---- setters: valid SET round-trips, invalid SET keeps prior value ------


def test_set_accel_rejects_non_positive(motion_lib):
    with Limits(motion_lib) as lim:
        lim.set_accel(500.0)
        assert lim.accel() == pytest.approx(500.0)
        lim.set_accel(0.0)
        assert lim.accel() == pytest.approx(500.0)  # unchanged
        lim.set_accel(-100.0)
        assert lim.accel() == pytest.approx(500.0)  # unchanged


def test_set_decel_rejects_non_positive(motion_lib):
    with Limits(motion_lib) as lim:
        lim.set_decel(700.0)
        assert lim.decel() == pytest.approx(700.0)
        lim.set_decel(0.0)
        assert lim.decel() == pytest.approx(700.0)  # unchanged
        lim.set_decel(-1.0)
        assert lim.decel() == pytest.approx(700.0)  # unchanged


def test_set_v_max_rejects_non_positive(motion_lib):
    with Limits(motion_lib) as lim:
        lim.set_v_max(300.0)
        assert lim.v_max() == pytest.approx(300.0)
        lim.set_v_max(0.0)
        assert lim.v_max() == pytest.approx(300.0)  # unchanged
        lim.set_v_max(-50.0)
        assert lim.v_max() == pytest.approx(300.0)  # unchanged


def test_set_jerk_accepts_zero_rejects_negative(motion_lib):
    """jerk's own "off" value is 0 (design S4.1) -- unlike accel/decel/
    vMax, a SET of exactly 0 is a real, accepted value (motion_limits.h's
    setJerk(): `if (v >= 0.0f) jerk = v`), not silently rejected."""
    with Limits(motion_lib) as lim:
        lim.set_jerk(4000.0)
        assert lim.jerk() == pytest.approx(4000.0)
        lim.set_jerk(0.0)
        assert lim.jerk() == pytest.approx(0.0)  # accepted, not rejected
        lim.set_jerk(-1.0)
        assert lim.jerk() == pytest.approx(0.0)  # unchanged


def test_set_omega_max_accepts_zero_rejects_negative(motion_lib):
    with Limits(motion_lib) as lim:
        lim.set_omega_max(90.0)
        assert lim.omega_max() == pytest.approx(90.0)
        lim.set_omega_max(0.0)
        assert lim.omega_max() == pytest.approx(0.0)
        lim.set_omega_max(-5.0)
        assert lim.omega_max() == pytest.approx(0.0)  # unchanged


def test_set_v_floor_accepts_zero_rejects_negative(motion_lib):
    with Limits(motion_lib) as lim:
        lim.set_v_floor(50.0)
        assert lim.v_floor() == pytest.approx(50.0)
        lim.set_v_floor(0.0)
        assert lim.v_floor() == pytest.approx(0.0)
        lim.set_v_floor(-1.0)
        assert lim.v_floor() == pytest.approx(0.0)  # unchanged


def test_set_omega_floor_accepts_zero_rejects_negative(motion_lib):
    with Limits(motion_lib) as lim:
        lim.set_omega_floor(15.0)
        assert lim.omega_floor() == pytest.approx(15.0)
        lim.set_omega_floor(0.0)
        assert lim.omega_floor() == pytest.approx(0.0)
        lim.set_omega_floor(-2.0)
        assert lim.omega_floor() == pytest.approx(0.0)  # unchanged


def test_set_stop_distance_accepts_zero_rejects_negative(motion_lib):
    with Limits(motion_lib) as lim:
        lim.set_stop_distance(0.7)
        assert lim.stop_distance() == pytest.approx(0.7)
        lim.set_stop_distance(0.0)
        assert lim.stop_distance() == pytest.approx(0.0)
        lim.set_stop_distance(-0.3)
        assert lim.stop_distance() == pytest.approx(0.0)  # unchanged


def test_set_arrive_dist_rejects_non_positive(motion_lib):
    with Limits(motion_lib) as lim:
        lim.set_arrive_dist(2.0)
        assert lim.arrive_dist() == pytest.approx(2.0)
        lim.set_arrive_dist(0.0)
        assert lim.arrive_dist() == pytest.approx(2.0)  # unchanged
        lim.set_arrive_dist(-1.0)
        assert lim.arrive_dist() == pytest.approx(2.0)  # unchanged


def test_set_arrive_yaw_rejects_non_positive(motion_lib):
    with Limits(motion_lib) as lim:
        lim.set_arrive_yaw(0.5)
        assert lim.arrive_yaw() == pytest.approx(0.5)
        lim.set_arrive_yaw(0.0)
        assert lim.arrive_yaw() == pytest.approx(0.5)  # unchanged
        lim.set_arrive_yaw(-0.2)
        assert lim.arrive_yaw() == pytest.approx(0.5)  # unchanged
