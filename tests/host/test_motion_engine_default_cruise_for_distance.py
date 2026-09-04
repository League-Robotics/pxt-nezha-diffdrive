"""tests/host/test_motion_engine_default_cruise_for_distance.py --
resolver-level proof of design docs/design/motion-profile-unification.md
S8's `v_default(D) = min(vMax, sqrt(decel * D))`, exercised directly
against `MotionEngine::defaultCruiseForDistance()` (motion_engine.h/.cpp)
with no wire layer involved -- the wire-handler-level proof (onMoveX()/
onGoToR()/onGoToW() branching onto this resolver, and onWheelsX()
staying untouched) lives in test_wire_motion_verbs.py instead.

REWRITTEN this ticket (design S8): the old formula was
`min(vMaxMmS_, sqrt(2 * aDecelMmS2_ * brakeFrac_ * D))`, gated behind a
"shaped mode" toggle callers had to opt into. The unified engine has no
`brakeFrac_` (deleted -- MotionLimits carries no such field, see
motion_limits.h) and no legacy/shaped split: `defaultCruiseForDistance()`
now always resolves via `limits_.decel`/`limits_.vMax`
(motion_engine.cpp) -- "a triangle whose braking half fits in D", design
S8's own phrase. Every test below is adjusted for the new formula and
the renamed setters (`limits().setDecel()`/`limits().setVMax()`,
exposed here as `meLimitsSetDecel`/`meLimitsSetVMax`); the coverage
list is otherwise unchanged from before this ticket.

Covers:
  1. The resolved speed matches the formula within floating-point
     tolerance, for a D small enough that the `sqrt(...)` term stays
     under the vMax ceiling.
  2. Monotonic non-decreasing in D.
  3. The vMax ceiling is respected for a large D that would otherwise
     exceed it.
  4. D == 0 (or a negative D, clamped to 0 internally) resolves to
     0.0 -- the wire layer's own non-positive-cruise refusal is what
     turns this into a range error; this test only pins the resolver's
     own contribution to that outcome. (A MOVE_X pure pivot does not
     produce D == 0, since onMoveX() resolves D via
     dominantAxisTravel() below, not |distance| alone.)
  5. Passing 0.0 to `setDecel()` is a no-op ("positive, else keep",
     motion_limits.h) -- decel can never be driven to 0.0 through the
     public surface, so the resolver never divides its own default
     away to nothing.
  6. dominantAxisTravel(distanceMm, rotationRad) -- the input helper
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
    _SRC_DIR / "motion" / "velocity_shaper.cpp",
    _TEST_DIR / "motion_engine_shim.cpp",
]


def _bind(lib):
    lib.meCreate.argtypes = []
    lib.meCreate.restype = ctypes.c_void_p
    lib.meDestroy.argtypes = [ctypes.c_void_p]
    lib.meDestroy.restype = None

    lib.meLimitsSetDecel.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.meLimitsSetDecel.restype = None
    lib.meLimitsSetVMax.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.meLimitsSetVMax.restype = None
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

    def set_decel(self, v):
        self._lib.meLimitsSetDecel(self._handle, v)

    def set_v_max(self, v):
        self._lib.meLimitsSetVMax(self._handle, v)

    def default_cruise_for_distance(self, distance_mm):
        return self._lib.meDefaultCruiseForDistance(self._handle, distance_mm)

    def dominant_axis_travel_mm(self, distance_mm, rotation_rad):
        return self._lib.meDominantAxisTravelMm(
            self._handle, distance_mm, rotation_rad)

    def effective_track_width(self):
        return self._lib.meEffectiveTrackWidth(self._handle)


def test_matches_formula_below_the_v_max_ceiling(motion_lib):
    """decel/D chosen so sqrt(decel*D) sits well under v_max -- the
    resolved speed must match the formula directly, not just be
    bounded by it."""
    with Engine(motion_lib) as e:
        e.set_decel(700.0)
        e.set_v_max(1000.0)  # far above anything this D can reach

        for d in (50.0, 100.0, 250.0, 500.0):
            expected = math.sqrt(700.0 * d)
            assert e.default_cruise_for_distance(d) == pytest.approx(
                expected, rel=1e-5)


def test_monotonic_nondecreasing_in_distance(motion_lib):
    with Engine(motion_lib) as e:
        e.set_decel(500.0)
        e.set_v_max(250.0)

        distances = [0.0, 10.0, 50.0, 100.0, 200.0, 400.0, 800.0, 1600.0]
        speeds = [e.default_cruise_for_distance(d) for d in distances]
        for prev, nxt in zip(speeds, speeds[1:]):
            assert nxt >= prev - 1e-6


def test_v_max_ceiling_is_respected_for_large_distance(motion_lib):
    """A distance large enough that the raw sqrt() term would exceed
    vMax must clip AT the ceiling, not above it."""
    with Engine(motion_lib) as e:
        e.set_decel(700.0)
        e.set_v_max(200.0)

        # sqrt(700*5000) ~= 1871 mm/s, far above the 200 mm/s ceiling.
        assert e.default_cruise_for_distance(5000.0) == pytest.approx(200.0)

        # Well below the ceiling: the formula, not the clip, governs.
        small_d = 20.0
        expected = math.sqrt(700.0 * small_d)
        assert expected < 200.0
        assert e.default_cruise_for_distance(small_d) == pytest.approx(
            expected, rel=1e-5)


def test_zero_or_negative_distance_resolves_to_zero(motion_lib):
    """D == 0 (a goToR()/goToW() call already at its target, or a
    direct call with no wheel travel on either axis) and a negative D
    (clamped to 0 internally, guarding the sqrt()) both resolve to
    exactly 0.0 -- the wire layer's own non-positive-cruise refusal is
    what turns this into a range error at the call site, not this
    method itself. (A MOVE_X pure pivot does NOT reach D == 0 any
    more -- see dominantAxisTravel() below.)"""
    with Engine(motion_lib) as e:
        e.set_decel(700.0)
        e.set_v_max(250.0)

        assert e.default_cruise_for_distance(0.0) == pytest.approx(0.0)
        assert e.default_cruise_for_distance(-50.0) == pytest.approx(0.0)


def test_setting_decel_to_zero_is_a_no_op_default_stays_positive(motion_lib):
    """MotionLimits::setDecel() (motion_limits.h) is a "positive, else
    keep" setter -- decel can never be driven to 0.0 through the public
    surface, so this resolver's `sqrt(decel * D)` term can never divide
    the field's own compiled-in default (400.0) away to nothing. A
    caller passing 0.0 (or a negative value) leaves the prior decel in
    effect, not a broken resolver."""
    with Engine(motion_lib) as e:
        e.set_v_max(1000.0)  # far above anything these D values can reach
        e.set_decel(0.0)  # rejected -- decel stays at its 400.0 default

        for d in (10.0, 1000.0):
            expected = math.sqrt(400.0 * d)
            assert e.default_cruise_for_distance(d) == pytest.approx(
                expected, rel=1e-5)


# ---- dominantAxisTravel(): onMoveX()'s own D input, so a pure pivot
# does not resolve D == 0 ---------------------------------------------


def test_dominant_axis_travel_pure_pivot_is_wheel_travel_not_zero(motion_lib):
    """The defect this helper exists to fix: a pure-pivot MOVE_X call
    (distanceMm == 0) still moves each wheel |rotationRad| *
    effectiveTrackWidth() / 2 mm -- that must be D, not 0, or every
    default-speed pivot in a tour would resolve to a zero cruise."""
    with Engine(motion_lib) as e:
        b = e.effective_track_width()
        rotation_rad = 0.3
        expected = abs(rotation_rad) * b / 2.0
        assert expected > 0.0
        assert e.dominant_axis_travel_mm(0.0, rotation_rad) == pytest.approx(
            expected, rel=1e-5)


def test_dominant_axis_travel_pure_translation_is_distance(motion_lib):
    """rotationRad == 0: D is just |distanceMm|."""
    with Engine(motion_lib) as e:
        assert e.dominant_axis_travel_mm(200.0, 0.0) == pytest.approx(200.0)
        assert e.dominant_axis_travel_mm(-200.0, 0.0) == pytest.approx(200.0)


def test_dominant_axis_travel_picks_the_larger_axis(motion_lib):
    """A blended move: whichever axis's own travel is larger wins --
    matches max(|distanceMm|, |rotationRad|*b/2), the same `dominant`
    quantity beginSegment() itself reduces to."""
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
    pivot's dominantAxisTravel() straight into
    defaultCruiseForDistance() produces a real, positive default
    cruise -- every default-speed pivot in a tour resolves to a real
    speed, not a refusal."""
    with Engine(motion_lib) as e:
        e.set_decel(700.0)
        e.set_v_max(1000.0)

        rotation_rad = 0.3
        d = e.dominant_axis_travel_mm(0.0, rotation_rad)
        resolved = e.default_cruise_for_distance(d)
        assert resolved > 0.0
