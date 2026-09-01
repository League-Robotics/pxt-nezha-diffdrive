"""tests/host/test_motion_engine_shaping_fields.py -- sprint 025 ticket
001's own minimal smoke test (its Testing section: "a minimal smoke
test in this ticket confirming the four new fields have working,
validated setters/getters" -- the full constant-decel/constant-accel
BEHAVIORAL proof is ticket 004's job, sequenced after tickets 002/003
land the rest of the mechanism).

Covers:
  1. The four new fields (aAccelMmS2_, aDecelMmS2_, vMaxMmS_,
     brakeFrac_) default to LEGACY-selecting/sane values, round-trip a
     valid SET through their own getter, and silently keep the prior
     value on an invalid SET -- the same ">0, else keep prior" style
     `setPivotOverrunMm()`/`setRotationalSlip()` already use
     (test_motion_engine_primitives.py's own
     test_set_rotational_slip_updates_effective_track_width_and_rejects_non_positive
     is the precedent this mirrors).
  2. The five getters this ticket adds for previously setter-only
     fields (distTaper/yawTaper/distFloor/turnFloor/rampMs) read back
     exactly what their own setter wrote -- needed by ticket 003's
     getConfigValue read-back.

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
    _TEST_DIR / "motion_engine_shim.cpp",
]


def _bind(lib):
    lib.meCreate.argtypes = []
    lib.meCreate.restype = ctypes.c_void_p
    lib.meDestroy.argtypes = [ctypes.c_void_p]
    lib.meDestroy.restype = None

    for getter in ("meAAccelMmS2", "meADecelMmS2", "meVMaxMmS", "meBrakeFrac",
                  "meDistTaper", "meYawTaper", "meDistFloor", "meTurnFloor",
                  "meRampMs"):
        fn = getattr(lib, getter)
        fn.argtypes = [ctypes.c_void_p]
        fn.restype = ctypes.c_float

    for setter in ("meSetAAccelMmS2", "meSetADecelMmS2", "meSetVMaxMmS",
                  "meSetBrakeFrac", "meSetDistTaper", "meSetYawTaper",
                  "meSetDistFloor", "meSetTurnFloor", "meSetRampMs"):
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


class Engine:
    """Thin Pythonic wrapper around one meCreate()/meDestroy() handle,
    pared down to only this file's own getter/setter surface."""

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

    def a_accel_mm_s2(self):
        return self._lib.meAAccelMmS2(self._handle)

    def set_a_accel_mm_s2(self, v):
        self._lib.meSetAAccelMmS2(self._handle, v)

    def a_decel_mm_s2(self):
        return self._lib.meADecelMmS2(self._handle)

    def set_a_decel_mm_s2(self, v):
        self._lib.meSetADecelMmS2(self._handle, v)

    def v_max_mm_s(self):
        return self._lib.meVMaxMmS(self._handle)

    def set_v_max_mm_s(self, v):
        self._lib.meSetVMaxMmS(self._handle, v)

    def brake_frac(self):
        return self._lib.meBrakeFrac(self._handle)

    def set_brake_frac(self, v):
        self._lib.meSetBrakeFrac(self._handle, v)

    def dist_taper(self):
        return self._lib.meDistTaper(self._handle)

    def set_dist_taper(self, v):
        self._lib.meSetDistTaper(self._handle, v)

    def yaw_taper(self):
        return self._lib.meYawTaper(self._handle)

    def set_yaw_taper(self, v):
        self._lib.meSetYawTaper(self._handle, v)

    def dist_floor(self):
        return self._lib.meDistFloor(self._handle)

    def set_dist_floor(self, v):
        self._lib.meSetDistFloor(self._handle, v)

    def turn_floor(self):
        return self._lib.meTurnFloor(self._handle)

    def set_turn_floor(self, v):
        self._lib.meSetTurnFloor(self._handle, v)

    def ramp_ms(self):
        return self._lib.meRampMs(self._handle)

    def set_ramp_ms(self, v):
        self._lib.meSetRampMs(self._handle, v)


# ---- new fields: defaults select legacy mode / are sane -----------------


def test_new_field_defaults_select_legacy_mode_and_are_sane(motion_lib):
    """aAccelMmS2_/aDecelMmS2_ default to 0.0 (legacy mode, the shipped
    default per this sprint's own mandate); vMaxMmS_/brakeFrac_ default
    to real, positive placeholder values -- vMaxMmS_ must never be 0
    (ticket 002's v_default() takes min() against it unconditionally)
    and brakeFrac_ must sit in (0, 1] (it is a fraction of a leg's own
    length)."""
    with Engine(motion_lib) as e:
        assert e.a_accel_mm_s2() == pytest.approx(0.0)
        assert e.a_decel_mm_s2() == pytest.approx(0.0)
        assert e.v_max_mm_s() > 0.0
        assert 0.0 < e.brake_frac() <= 1.0


# ---- new fields: valid SET round-trips, invalid SET keeps prior value ---


def test_set_a_accel_mm_s2_rejects_non_positive(motion_lib):
    with Engine(motion_lib) as e:
        e.set_a_accel_mm_s2(500.0)
        assert e.a_accel_mm_s2() == pytest.approx(500.0)

        e.set_a_accel_mm_s2(0.0)
        assert e.a_accel_mm_s2() == pytest.approx(500.0)  # unchanged
        e.set_a_accel_mm_s2(-100.0)
        assert e.a_accel_mm_s2() == pytest.approx(500.0)  # unchanged


def test_set_a_decel_mm_s2_rejects_non_positive(motion_lib):
    with Engine(motion_lib) as e:
        e.set_a_decel_mm_s2(700.0)
        assert e.a_decel_mm_s2() == pytest.approx(700.0)

        e.set_a_decel_mm_s2(0.0)
        assert e.a_decel_mm_s2() == pytest.approx(700.0)  # unchanged
        e.set_a_decel_mm_s2(-1.0)
        assert e.a_decel_mm_s2() == pytest.approx(700.0)  # unchanged


def test_set_v_max_mm_s_rejects_non_positive(motion_lib):
    with Engine(motion_lib) as e:
        e.set_v_max_mm_s(300.0)
        assert e.v_max_mm_s() == pytest.approx(300.0)

        e.set_v_max_mm_s(0.0)
        assert e.v_max_mm_s() == pytest.approx(300.0)  # unchanged
        e.set_v_max_mm_s(-50.0)
        assert e.v_max_mm_s() == pytest.approx(300.0)  # unchanged


def test_set_brake_frac_rejects_outside_zero_to_one(motion_lib):
    with Engine(motion_lib) as e:
        e.set_brake_frac(0.4)
        assert e.brake_frac() == pytest.approx(0.4)

        e.set_brake_frac(0.0)
        assert e.brake_frac() == pytest.approx(0.4)  # unchanged (must be >0)
        e.set_brake_frac(-0.1)
        assert e.brake_frac() == pytest.approx(0.4)  # unchanged
        e.set_brake_frac(1.5)
        assert e.brake_frac() == pytest.approx(0.4)  # unchanged (must be <=1)

        # The boundary itself (exactly 1.0) is valid -- the field comment
        # specifies (0, 1], inclusive of 1.
        e.set_brake_frac(1.0)
        assert e.brake_frac() == pytest.approx(1.0)


# ---- getters for the five pre-existing setter-only fields ---------------


def test_getters_for_five_existing_shaping_fields_read_back_their_setter(
        motion_lib):
    """These five fields already had working setters; this ticket adds
    only the getters (needed by ticket 003's getConfigValue read-back).
    Each getter must read back exactly what its own setter wrote,
    distinct from the class's own compiled-in defaults (motion_engine.h:
    distTaper_ 400.0, yawTaper_ 180.0, distFloor_ 0.25, turnFloor_ 0.12,
    rampMs_ 400.0)."""
    with Engine(motion_lib) as e:
        assert e.dist_taper() == pytest.approx(400.0)
        assert e.yaw_taper() == pytest.approx(180.0)
        assert e.dist_floor() == pytest.approx(0.25)
        assert e.turn_floor() == pytest.approx(0.12)
        assert e.ramp_ms() == pytest.approx(400.0)

        e.set_dist_taper(500.0)
        assert e.dist_taper() == pytest.approx(500.0)
        e.set_yaw_taper(200.0)
        assert e.yaw_taper() == pytest.approx(200.0)
        e.set_dist_floor(0.3)
        assert e.dist_floor() == pytest.approx(0.3)
        e.set_turn_floor(0.15)
        assert e.turn_floor() == pytest.approx(0.15)
        e.set_ramp_ms(600.0)
        assert e.ramp_ms() == pytest.approx(600.0)
