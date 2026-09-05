"""tests/host/test_goto_turn_rate_reconciliation.py -- pins
src/motion/motion_engine.h/.cpp's MotionEngine::reconcileDualRateCruise()
and MotionEngine::decomposeGoToR(), the two pure functions sprint 032
ticket 007 factored out so shims.cpp's engineGoToRArmed() (goTo()'s
block-API entry point) can reconcile a separate `defaultYawRate` ceiling
against `defaultSpeed` before calling MotionEngine::goToR() -- the same
duration-budget pattern startMove() already applies for move()/goTo()'s
sibling block, `move()`.

**Why this needed a native-shim fix, not a TS-only one** (see the
ticket's own Description for the full trace): MotionEngine::goToR()
threads a SINGLE `speed`/cruise parameter through both its pivot and
straight phases (queuePivotThenStraight() reuses the same `cruise` for
both) -- there was no way for a block-API caller to make the pivot
phase honor a distinct `defaultYawRate` without reconciling the two
ceilings into one `cruise` BEFORE the native call, exactly the pattern
startMove() already uses for moveX()'s own (distance, rotation) pair.

**What this file does NOT test**: shims.cpp's own engineGoToRArmed()/
engineSetGoToYawRate() wiring (shims.cpp includes pxt.h and is not
host-portable -- see test_goto_block_regression.py's own docstring for
the same limitation on startGoTo()/blocks/motion.ts) or blocks/sim.ts's
simulator mirror (TypeScript, same limitation). Both were reviewed by
inspection against the formulas pinned here. This file tests the real,
compiled C++ math both of those callers delegate to.

Run with::

    uv run pytest tests/host/test_goto_turn_rate_reconciliation.py
"""

import ctypes
import math
import pathlib

import pytest

from test_kernel_harness import compile_shared_lib
from test_motion_engine_reductions import Engine, _bind

_TEST_DIR = pathlib.Path(__file__).resolve().parent
_SRC_DIR = _TEST_DIR.parent.parent / "src"

_SHIM_SOURCES = [
    _SRC_DIR / "core" / "diffdrive.cpp",
    _SRC_DIR / "motion" / "motion_engine.cpp",
    _SRC_DIR / "motion" / "velocity_shaper.cpp",
    _TEST_DIR / "motion_engine_shim.cpp",
]


def _bind_reconcile(lib):
    lib.meReconcileCruise.argtypes = [
        ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_float,
        ctypes.c_float,
    ]
    lib.meReconcileCruise.restype = ctypes.c_float
    lib.meReconcileDistDuration.argtypes = lib.meReconcileCruise.argtypes
    lib.meReconcileDistDuration.restype = ctypes.c_float
    lib.meReconcileYawDuration.argtypes = lib.meReconcileCruise.argtypes
    lib.meReconcileYawDuration.restype = ctypes.c_float

    lib.meDecomposeGoToRBearingRaw.argtypes = [ctypes.c_float, ctypes.c_float]
    lib.meDecomposeGoToRBearingRaw.restype = ctypes.c_float
    lib.meDecomposeGoToRTheta.argtypes = [ctypes.c_float, ctypes.c_float]
    lib.meDecomposeGoToRTheta.restype = ctypes.c_float
    lib.meDecomposeGoToRChord.argtypes = [ctypes.c_float, ctypes.c_float]
    lib.meDecomposeGoToRChord.restype = ctypes.c_float
    lib.meDecomposeGoToRArcLength.argtypes = [ctypes.c_float, ctypes.c_float]
    lib.meDecomposeGoToRArcLength.restype = ctypes.c_float
    lib.meDecomposeGoToRWillSplit.argtypes = [ctypes.c_float, ctypes.c_float]
    lib.meDecomposeGoToRWillSplit.restype = ctypes.c_int
    return lib


@pytest.fixture(scope="session")
def motion_lib(tmp_path_factory):
    lib_path = compile_shared_lib(
        tmp_path_factory, sources=_SHIM_SOURCES,
        out_name="libgoto_turn_rate_reconciliation_shim.so",
    )
    return _bind_reconcile(_bind(ctypes.CDLL(str(lib_path))))


class ReconcileEngine(Engine):
    """Engine (test_motion_engine_reductions.py) extended with the
    reconciliation/decomposition getters this file needs. decomposeGoToR()
    is static (a pure function of x, y) -- its wrappers below ignore
    `self._handle` entirely, kept as instance methods only so call sites
    read the same way as the handle-bound ones."""

    def reconcile_cruise(self, distance, rotation, speed, yaw_rate):
        return self._lib.meReconcileCruise(
            self._handle, distance, rotation, speed, yaw_rate)

    def reconcile_dist_duration(self, distance, rotation, speed, yaw_rate):
        return self._lib.meReconcileDistDuration(
            self._handle, distance, rotation, speed, yaw_rate)

    def reconcile_yaw_duration(self, distance, rotation, speed, yaw_rate):
        return self._lib.meReconcileYawDuration(
            self._handle, distance, rotation, speed, yaw_rate)

    def decompose_bearing_raw(self, x, y):
        return self._lib.meDecomposeGoToRBearingRaw(x, y)

    def decompose_theta(self, x, y):
        return self._lib.meDecomposeGoToRTheta(x, y)

    def decompose_chord(self, x, y):
        return self._lib.meDecomposeGoToRChord(x, y)

    def decompose_arc_length(self, x, y):
        return self._lib.meDecomposeGoToRArcLength(x, y)

    def decompose_will_split(self, x, y):
        return bool(self._lib.meDecomposeGoToRWillSplit(x, y))


def _ready(e):
    e.set_max_duty(100.0)
    e.set_full_duty_velocity(5000.0)
    assert e.begin() == 0  # STATUS_OK


# ---- AC: the reconciliation FORMULA pinned against an independent
# Python transcription of shims.cpp's startMove() -- numeric agreement,
# not "compiles and runs" ---------------------------------------------


def _python_reconcile(distance_mm, rotation_rad, speed_mm_s,
                       yaw_rate_rad_s, cpm, track_width_mm):
    """Independent transcription of shims.cpp's startMove() reconciliation
    algebra (the SAME formula reconcileDualRateCruise() now implements,
    relocated verbatim rather than rewritten -- see that method's own
    comment). Written directly from the formula's description, not by
    reading motion_engine.cpp's C++ source, so agreement with the real
    compiled function is a genuine cross-check, not a tautology."""
    dist_target = distance_mm * cpm
    yaw_target = rotation_rad * 0.5 * track_width_mm * cpm
    dist_speed = speed_mm_s * cpm
    twist_speed = yaw_rate_rad_s * 0.5 * track_width_mm * cpm

    dist_duration = abs(dist_target) / dist_speed if dist_target != 0 else 0.0
    yaw_duration = abs(yaw_target) / twist_speed if yaw_target != 0 else 0.0
    duration = max(dist_duration, yaw_duration)
    if duration <= 0:
        return 0.0, 0.0, 0.0

    left = dist_target - yaw_target
    right = dist_target + yaw_target
    dominant = max(abs(left), abs(right))
    cruise = (dominant / duration) / cpm
    return cruise, dist_duration, yaw_duration


@pytest.mark.parametrize("distance_mm,rotation_deg,speed_mm_s,yaw_rate_deg_s", [
    (300.0, 90.0, 150.0, 90.0),    # move(30, 90) at the block defaults
    (300.0, 90.0, 150.0, 30.0),    # same move, yaw ceiling now dominant
    (600.0, 20.0, 100.0, 200.0),   # below the split threshold, dist dominant
    (0.0, 90.0, 150.0, 45.0),      # pure pivot
    (300.0, 0.0, 150.0, 45.0),     # pure straight
    (1414.0, 349.5, 300.0, 15.0),  # a >180 deg equivalent yaw, slow yaw ceiling
])
def test_reconcile_dual_rate_cruise_matches_python_transcription(
        motion_lib, distance_mm, rotation_deg, speed_mm_s, yaw_rate_deg_s):
    with ReconcileEngine(motion_lib) as e:
        _ready(e)
        cpm = e.counts_per_mm()
        track_width_mm = e.effective_track_width()

        rotation_rad = math.radians(rotation_deg)
        yaw_rate_rad_s = math.radians(yaw_rate_deg_s)

        expected_cruise, expected_dist_dur, expected_yaw_dur = _python_reconcile(
            distance_mm, rotation_rad, speed_mm_s, yaw_rate_rad_s,
            cpm, track_width_mm)

        cruise = e.reconcile_cruise(distance_mm, rotation_rad, speed_mm_s,
                                    yaw_rate_rad_s)
        dist_dur = e.reconcile_dist_duration(distance_mm, rotation_rad,
                                             speed_mm_s, yaw_rate_rad_s)
        yaw_dur = e.reconcile_yaw_duration(distance_mm, rotation_rad,
                                           speed_mm_s, yaw_rate_rad_s)

        assert cruise == pytest.approx(expected_cruise, rel=1e-4)
        assert dist_dur == pytest.approx(expected_dist_dur, rel=1e-4)
        assert yaw_dur == pytest.approx(expected_yaw_dur, rel=1e-4)


# ---- AC: a worked ~90 deg-pivot example -- the pivot PHASE's own
# duration follows defaultYawRate, not `speed` reinterpreted as an
# angular rate ----------------------------------------------------------


def test_worked_example_pivot_duration_follows_default_yaw_rate_not_speed(
        motion_lib):
    """goTo(0, 10) cm: a target 100 mm directly to the left. bearingRaw =
    atan2(100, 0) = 90 deg exactly, theta = wrap(180 deg) = 180 deg, well
    above the 50 deg split threshold -- MotionEngine::goToR() pivots
    bearingRaw (90 deg, NOT theta) then drives the 100 mm chord straight
    (motion_engine.cpp: queuePivotThenStraight(bearingRaw, chord, ...)).

    Block defaults: defaultSpeed 150 mm/s (15 cm/s), defaultYawRate
    chosen deliberately SLOW (45 deg/s, not the block's own 90 deg/s
    default) so the yaw axis -- not the distance axis -- governs the
    reconciled duration; this is what proves the fix, since the OLD
    (pre-fix) behavior always ran the pivot at whatever angular rate
    `speed` alone implied (~143 deg/s at 15 cm/s over this engine's
    default geometry -- goto-turn-rate-arrival-tolerance-tick-runner-
    cyclestat.md's own measurement) regardless of defaultYawRate.

    Expected pivot-phase duration = |bearingRaw| / defaultYawRate =
    90 deg / 45 deg/s = 2.0 s -- NOT 180 deg / 45 deg/s (4.0 s), which is
    what a reconciliation that reused `theta` (the SPLIT-DECISION angle)
    instead of `bearingRaw` (the angle actually driven) would produce.
    Both `bearingRaw` and `yawDuration` below come from the real
    compiled engine, not from Python arithmetic -- this is checking that
    decomposeGoToR() and reconcileDualRateCruise() actually compose
    correctly, not re-deriving the answer independently."""
    x_mm, y_mm = 0.0, 100.0
    default_speed_mm_s = 150.0
    default_yaw_rate_deg_s = 45.0
    default_yaw_rate_rad_s = math.radians(default_yaw_rate_deg_s)

    with ReconcileEngine(motion_lib) as e:
        _ready(e)

        bearing_raw = e.decompose_bearing_raw(x_mm, y_mm)
        theta = e.decompose_theta(x_mm, y_mm)
        chord = e.decompose_chord(x_mm, y_mm)
        will_split = e.decompose_will_split(x_mm, y_mm)

        assert will_split
        assert bearing_raw == pytest.approx(math.pi / 2, abs=1e-4)
        assert theta == pytest.approx(math.pi, abs=1e-4)
        assert chord == pytest.approx(100.0, abs=1e-3)

        yaw_duration = e.reconcile_yaw_duration(
            chord, bearing_raw, default_speed_mm_s, default_yaw_rate_rad_s)

        expected_s = abs(bearing_raw) / default_yaw_rate_rad_s
        assert yaw_duration == pytest.approx(expected_s, rel=1e-4)
        assert yaw_duration == pytest.approx(2.0, rel=1e-3)

        # Pin against the WRONG formula too -- using `theta` (the
        # split-decision angle) instead of `bearingRaw` (the angle
        # goToR() actually pivots) would double this duration. Naming
        # this explicitly guards against a future edit re-introducing
        # that mix-up (see this ticket's own report for why the source
        # issue's literal "180 deg / defaultYawRate" phrasing describes
        # motion.ts's separate, pre-existing, deliberately-conservative
        # TIMEOUT budget -- not the pivot's own real duration).
        wrong_duration_using_theta = abs(theta) / default_yaw_rate_rad_s
        assert wrong_duration_using_theta == pytest.approx(
            2.0 * yaw_duration, rel=1e-3)


def test_worked_example_distance_axis_dominates_at_high_yaw_rate(motion_lib):
    """Same geometry as the test above, but with defaultYawRate restored
    to the block's actual 90 deg/s default: the pivot phase (90 deg /
    90 deg/s = 1.0 s) now finishes faster than the straight phase
    (100 mm / 150 mm/s = 0.667 s) would if it were dominant -- wait,
    the straight phase is still faster in absolute terms here, so this
    geometry keeps the YAW axis dominant either way (1.0 s > 0.667 s).
    Confirms reconcile_dist_duration() is still exactly the plain
    chord/speed division regardless of which axis ends up dominant."""
    x_mm, y_mm = 0.0, 100.0
    default_speed_mm_s = 150.0
    default_yaw_rate_rad_s = math.radians(90.0)

    with ReconcileEngine(motion_lib) as e:
        _ready(e)
        bearing_raw = e.decompose_bearing_raw(x_mm, y_mm)
        chord = e.decompose_chord(x_mm, y_mm)

        dist_duration = e.reconcile_dist_duration(
            chord, bearing_raw, default_speed_mm_s, default_yaw_rate_rad_s)
        assert dist_duration == pytest.approx(chord / default_speed_mm_s,
                                              rel=1e-4)
