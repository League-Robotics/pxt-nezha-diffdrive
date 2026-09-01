"""tests/host/test_motion_engine_default_cruise_for_distance.py --
resolver-level proof of SUC-003's `v_default(D) = min(vMaxMmS_,
sqrt(2 * aDecelMmS2_ * brakeFrac_ * D))`, exercised directly against
`MotionEngine::defaultCruiseForDistance()` (motion_engine.h/.cpp) with
no wire layer involved -- the wire-handler-level proof (onMoveX()/
onGoToR()/onGoToW() branching onto this resolver, and onWheelsX()
staying untouched) lives in test_wire_motion_verbs.py instead.

Covers:
  1. The resolved speed matches the formula within floating-point
     tolerance, for a D small enough that the `sqrt(...)` term stays
     under the vMaxMmS_ ceiling.
  2. Monotonic non-decreasing in D.
  3. The vMaxMmS_ ceiling is respected for a large D that would
     otherwise exceed it.
  4. D == 0 (or a negative D, clamped to 0 internally) resolves to
     0.0 -- the wire layer's existing non-positive-cruise refusal is
     what turns this into a range error; this test only pins the
     resolver's own contribution to that outcome. (At the wire layer
     this is now the genuinely degenerate case only -- a MOVE_X pure
     pivot no longer produces D == 0, since onMoveX() resolves D via
     dominantAxisTravelMm() below, not |distance| alone.)
  5. aDecelMmS2_ == 0.0 (the shipped legacy default) resolves to 0.0
     for any D -- callers gate on aDecelMmS2_ > 0 before ever calling
     this method (wire_adapter.cpp's onMoveX()/onGoToR()/onGoToW()),
     so this is this method's own honest answer when asked anyway,
     not a behavior any wire caller reaches in legacy mode.
  6. dominantAxisTravelMm(distanceMm, rotationRad) -- the input helper
     onMoveX() uses to build D -- matches
     max(|distanceMm|, |rotationRad|*effectiveTrackWidth()/2), and in
     particular is nonzero for a pure pivot (distanceMm == 0).

Run with::

    uv run pytest tests/host/test_motion_engine_default_cruise_for_distance.py
"""

import ctypes
import math
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

    lib.meSetADecelMmS2.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.meSetADecelMmS2.restype = None
    lib.meSetVMaxMmS.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.meSetVMaxMmS.restype = None
    lib.meSetBrakeFrac.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.meSetBrakeFrac.restype = None
    lib.meDefaultCruiseForDistance.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.meDefaultCruiseForDistance.restype = ctypes.c_float
    lib.meDominantAxisTravelMm.argtypes = [
        ctypes.c_void_p, ctypes.c_float, ctypes.c_float,
    ]
    lib.meDominantAxisTravelMm.restype = ctypes.c_float
    lib.meEffectiveTrackWidth.argtypes = [ctypes.c_void_p]
    lib.meEffectiveTrackWidth.restype = ctypes.c_float

    return lib


@pytest.fixture(scope="session")
def motion_lib(tmp_path_factory):
    lib_path = compile_shared_lib(
        tmp_path_factory, sources=_SHIM_SOURCES,
        out_name="libmotion_engine_default_cruise_shim.so",
    )
    return _bind(ctypes.CDLL(str(lib_path)))


class Engine:
    """Thin Pythonic wrapper, pared down to this file's own surface."""

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

    def set_a_decel_mm_s2(self, v):
        self._lib.meSetADecelMmS2(self._handle, v)

    def set_v_max_mm_s(self, v):
        self._lib.meSetVMaxMmS(self._handle, v)

    def set_brake_frac(self, v):
        self._lib.meSetBrakeFrac(self._handle, v)

    def default_cruise_for_distance(self, distance_mm):
        return self._lib.meDefaultCruiseForDistance(self._handle, distance_mm)

    def dominant_axis_travel_mm(self, distance_mm, rotation_rad):
        return self._lib.meDominantAxisTravelMm(
            self._handle, distance_mm, rotation_rad)

    def effective_track_width(self):
        return self._lib.meEffectiveTrackWidth(self._handle)


def test_matches_formula_below_the_v_max_ceiling(motion_lib):
    """A_decel/brake_frac/D chosen so sqrt(2*a*frac*D) sits well under
    v_max -- the resolved speed must match the formula directly, not
    just be bounded by it."""
    with Engine(motion_lib) as e:
        e.set_a_decel_mm_s2(700.0)
        e.set_brake_frac(0.375)
        e.set_v_max_mm_s(1000.0)  # far above anything this D can reach

        for d in (50.0, 100.0, 250.0, 500.0):
            expected = math.sqrt(2.0 * 700.0 * 0.375 * d)
            assert e.default_cruise_for_distance(d) == pytest.approx(
                expected, rel=1e-5)


def test_monotonic_nondecreasing_in_distance(motion_lib):
    with Engine(motion_lib) as e:
        e.set_a_decel_mm_s2(500.0)
        e.set_brake_frac(0.4)
        e.set_v_max_mm_s(250.0)

        distances = [0.0, 10.0, 50.0, 100.0, 200.0, 400.0, 800.0, 1600.0]
        speeds = [e.default_cruise_for_distance(d) for d in distances]
        for prev, nxt in zip(speeds, speeds[1:]):
            assert nxt >= prev - 1e-6


def test_v_max_ceiling_is_respected_for_large_distance(motion_lib):
    """A distance large enough that the raw sqrt() term would exceed
    vMaxMmS_ must clip AT the ceiling, not above it."""
    with Engine(motion_lib) as e:
        e.set_a_decel_mm_s2(700.0)
        e.set_brake_frac(0.4)
        e.set_v_max_mm_s(200.0)

        # sqrt(2*700*0.4*5000) ~= 1673 mm/s, far above the 200 mm/s ceiling.
        assert e.default_cruise_for_distance(5000.0) == pytest.approx(200.0)

        # Well below the ceiling: the formula, not the clip, governs.
        small_d = 20.0
        expected = math.sqrt(2.0 * 700.0 * 0.4 * small_d)
        assert expected < 200.0
        assert e.default_cruise_for_distance(small_d) == pytest.approx(
            expected, rel=1e-5)


def test_zero_or_negative_distance_resolves_to_zero(motion_lib):
    """D == 0 (a goToR()/goToW() call already at its target, or a
    direct call with no wheel travel on either axis) and a negative D
    (clamped to 0 internally, guarding the sqrt()) both resolve to
    exactly 0.0 -- the wire layer's existing non-positive-cruise
    refusal is what turns this into a range error at the call site, not
    this method itself. (A MOVE_X pure pivot does NOT reach D == 0 any
    more -- see dominantAxisTravelMm() below.)"""
    with Engine(motion_lib) as e:
        e.set_a_decel_mm_s2(700.0)
        e.set_brake_frac(0.4)
        e.set_v_max_mm_s(250.0)

        assert e.default_cruise_for_distance(0.0) == pytest.approx(0.0)
        assert e.default_cruise_for_distance(-50.0) == pytest.approx(0.0)


def test_legacy_a_decel_zero_resolves_to_zero_for_any_distance(motion_lib):
    """aDecelMmS2_ == 0.0 is the shipped legacy default; a wire caller
    never reaches this resolver in that mode (it gates on aDecelMmS2_ >
    0 first, wire_adapter.cpp), but the resolver's own contract must
    still be well-defined and NaN-free if called anyway."""
    with Engine(motion_lib) as e:
        e.set_v_max_mm_s(250.0)
        e.set_brake_frac(0.4)
        # aDecelMmS2_ left at its compiled-in default, 0.0.

        for d in (0.0, 10.0, 1000.0):
            assert e.default_cruise_for_distance(d) == pytest.approx(0.0)


# ---- dominantAxisTravelMm(): onMoveX()'s own D input, so a pure pivot
# does not resolve D == 0 ---------------------------------------------


def test_dominant_axis_travel_pure_pivot_is_wheel_travel_not_zero(motion_lib):
    """The defect this helper exists to fix: a pure-pivot MOVE_X call
    (distanceMm == 0) still moves each wheel |rotationRad| *
    effectiveTrackWidth() / 2 mm -- that must be D, not 0, or every
    default-speed pivot in a tour is refused the moment shaped mode is
    on."""
    with Engine(motion_lib) as e:
        b = e.effective_track_width()
        rotation_rad = 0.3
        expected = abs(rotation_rad) * b / 2.0
        assert expected > 0.0
        assert e.dominant_axis_travel_mm(0.0, rotation_rad) == pytest.approx(
            expected, rel=1e-5)


def test_dominant_axis_travel_pure_translation_is_distance(motion_lib):
    """rotationRad == 0: D is just |distanceMm|, same as this ticket's
    original (pre-fix) behavior for a straight leg."""
    with Engine(motion_lib) as e:
        assert e.dominant_axis_travel_mm(200.0, 0.0) == pytest.approx(200.0)
        assert e.dominant_axis_travel_mm(-200.0, 0.0) == pytest.approx(200.0)


def test_dominant_axis_travel_picks_the_larger_axis(motion_lib):
    """A blended move: whichever axis's own travel is larger wins --
    matches max(|distanceMm|, |rotationRad|*b/2), the same `dominant`
    quantity startSegment() itself reduces to."""
    with Engine(motion_lib) as e:
        b = e.effective_track_width()

        small_rotation = 0.05  # yaw travel well under 200 mm
        assert e.dominant_axis_travel_mm(
            200.0, small_rotation) == pytest.approx(200.0)

        large_rotation = 2.0  # yaw travel well over 50 mm
        yaw_travel = abs(large_rotation) * b / 2.0
        assert yaw_travel > 50.0
        assert e.dominant_axis_travel_mm(
            50.0, large_rotation) == pytest.approx(yaw_travel, rel=1e-5)


def test_dominant_axis_travel_both_zero_is_zero(motion_lib):
    """The one genuinely degenerate case: no travel on either axis."""
    with Engine(motion_lib) as e:
        assert e.dominant_axis_travel_mm(0.0, 0.0) == pytest.approx(0.0)


def test_pure_pivot_resolves_a_real_nonzero_default_cruise(motion_lib):
    """End-to-end at the engine level (no wire layer): feeding a pure
    pivot's dominantAxisTravelMm() straight into
    defaultCruiseForDistance() produces a real, positive default cruise
    -- the fix for the field-breaking defect this ticket's coordinator
    flagged (every tour pivot would otherwise be refused once shaped
    mode is on)."""
    with Engine(motion_lib) as e:
        e.set_a_decel_mm_s2(700.0)
        e.set_brake_frac(0.375)
        e.set_v_max_mm_s(1000.0)

        rotation_rad = 0.3
        d = e.dominant_axis_travel_mm(0.0, rotation_rad)
        resolved = e.default_cruise_for_distance(d)
        assert resolved > 0.0
