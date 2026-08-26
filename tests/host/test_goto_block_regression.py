"""tests/host/test_goto_block_regression.py -- drives moves to actual
COMPLETION against ideal wheels (motion_engine_shim.cpp's
meProbeRunToCompletion(), mirroring docs/code-review/2026-08-26/raw/
goto_probe.cpp's own Rig::tick()/run()) and checks the resulting
body-frame ENDPOINT, rather than test_motion_engine_reductions.py's own
single-tick hand-computed-duty style -- the shape this ticket needs to
compare two different ways of turning a target into a move on the SAME
final position, not just their first commanded duty.

Two probe geometries, both measured in block-go-to-misses-its-target.md
against the real firmware C++ and both ABOVE MotionEngine's own 50 deg
pivot-vs-blend split threshold (kTurnFirstAngleRad) when run through the
OLD, now-historical reduction below:

  block goTo(10, 10) cm   -> bearing 45 deg, a 141.4 mm hop
  block goTo(-10, 1) cm   -> a target behind the robot, theta wraps short

MotionEngine::goToR() (already correct) reaches both within a few mm.
blocks/motion.ts's startGoTo() (sprint 015 ticket 002) now calls goToR()
directly instead of computing its own (arc-length, arc-angle) pair and
handing it to MotionEngine::moveX() -- moveX()'s own >=50 deg
pivot-then-straight split used to reissue that pair as a DIFFERENT
physical path than the arc it was computed for, missing by the margins
the issue measured. This file restates BOTH reductions directly in
Python (motion.ts is TypeScript, out of reach of a host build) and
drives each through the real firmware's own move engine, on the SAME two
geometries, to prove the gap end-to-end rather than at a single tick:
the OLD reduction is kept as a frozen negative control (pinned to the
measured miss, so the historical defect stays documented and a
regression back to it would be caught), and the NEW reduction --
transcribing startGoTo()'s actual post-fix arithmetic -- is asserted to
land within tolerance.

Run with::

    uv run pytest tests/host/test_goto_block_regression.py
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
    _TEST_DIR / "motion_engine_shim.cpp",
]

# Arbitrary [counts/s] -- cancels out of the ideal-wheels kinematics
# entirely (duty = velocityCmd/fullDutyVelocity, position advances by
# duty*fullDutyVelocity*dt == velocityCmd*dt), as long as the SAME value
# configures the kernel (set_full_duty_velocity()) and drives the probe's
# own physics projection (run_to_completion()'s first argument) -- both
# below always pass this one constant to both. Chosen only to keep every
# commanded duty well under the 100% rail (matches
# test_motion_engine_reductions.py's own choice).
_FULL_DUTY_VELOCITY = 5000.0

# [ms] matches goto_probe.cpp's own kPeriodMs exactly -- the move-engine's
# end-of-move taper/ramp shaping (motion_engine.cpp's serviceMove()) is
# genuinely tick-discretized, so reproducing the probe's own measured miss
# distances (not just landing "close enough") means reproducing its own
# tick granularity too.
_PERIOD_MS = 24

# Generous: the longer of the two block-reduction cases below drives a
# ~349 deg pivot plus a ~3.07 m straight leg at 150 mm/s (~23 s simulated,
# ~960 ticks at 24 ms/tick) -- this leaves ~3x headroom. A probe that
# still hasn't gone inactive by this many ticks did not complete, and
# run_to_completion() asserts that rather than silently reading a
# truncated endpoint.
_MAX_TICKS = 3000

_PROBE_SPEED_MM_S = 150.0
_PROBE_TIMEOUT_MS = 60_000

# The ticket's own acceptance bar (block-go-to-misses-its-target.md):
# landing within 5 mm of the commanded target.
_LANDING_TOLERANCE_MM = 5.0

# blocks/motion.ts's own diffDrive namespace defaults (defaultSpeed
# [cm/s], defaultYawRate [deg/s]) -- the fixed startGoTo() transcription
# below (`_fixed_start_go_to_to_go_to_r`) uses these exactly as
# startGoTo() itself does, so the timeout it derives matches what the
# real block would compute.
_BLOCK_DEFAULT_SPEED_CM_S = 15.0
_BLOCK_DEFAULT_YAW_RATE_DEG_S = 90.0


def _bind_probe(lib):
    lib.meProbeRunToCompletion.argtypes = [
        ctypes.c_void_p, ctypes.c_float, ctypes.c_uint32, ctypes.c_uint32,
    ]
    lib.meProbeRunToCompletion.restype = ctypes.c_uint32
    lib.meProbeX.argtypes = [ctypes.c_void_p]
    lib.meProbeX.restype = ctypes.c_float
    lib.meProbeY.argtypes = [ctypes.c_void_p]
    lib.meProbeY.restype = ctypes.c_float
    lib.meProbeHeading.argtypes = [ctypes.c_void_p]
    lib.meProbeHeading.restype = ctypes.c_float
    return lib


@pytest.fixture(scope="session")
def motion_lib(tmp_path_factory):
    lib_path = compile_shared_lib(
        tmp_path_factory, sources=_SHIM_SOURCES,
        out_name="libgoto_block_regression_shim.so",
    )
    return _bind_probe(_bind(ctypes.CDLL(str(lib_path))))


class ProbeEngine(Engine):
    """Engine (test_motion_engine_reductions.py) extended with the
    ideal-wheels run-to-completion probe -- drives whatever moveX()/
    goToR() call the test already issued to completion, then reports the
    resulting body-frame endpoint. Assumes a FRESH handle (this class's
    own __init__, inherited unchanged, calls meCreate() every time): the
    probe's odometry accumulator starts at (0, 0, 0) and is never reset,
    so reusing one instance across two separate moves would silently sum
    their endpoints -- every test below opens a fresh `with ProbeEngine(
    motion_lib) as e:` block per move for exactly this reason."""

    def run_to_completion(self, full_duty_velocity=_FULL_DUTY_VELOCITY,
                          period_ms=_PERIOD_MS, max_ticks=_MAX_TICKS):
        ticks = self._lib.meProbeRunToCompletion(
            self._handle, full_duty_velocity, period_ms, max_ticks)
        assert ticks < max_ticks, (
            f"move did not complete within {max_ticks} ticks "
            f"({period_ms * max_ticks / 1000.0:.1f} s simulated) -- the "
            "probe's endpoint reading would be a mid-move snapshot, not "
            "a real landing")
        return ticks

    def probe_x(self):
        return self._lib.meProbeX(self._handle)

    def probe_y(self):
        return self._lib.meProbeY(self._handle)

    def probe_heading(self):
        return self._lib.meProbeHeading(self._handle)


def _ready(e):
    e.set_max_duty(100.0)
    e.set_full_duty_velocity(_FULL_DUTY_VELOCITY)
    assert e.begin() == 0  # STATUS_OK


def _old_broken_block_arc_reduction_to_move_x(e, x_cm, y_cm, speed_mm_s,
                                               timeout_ms):
    """HISTORICAL / negative control only -- restates blocks/motion.ts's
    PRE-fix startGoTo() reduction exactly as it shipped before sprint 015
    ticket 002: theta = 2*atan2(y,x), s = R*theta (computed in the
    student's own cm), then issued through moveX() in mm. This was the
    ONLY entry point reachable from a block before that ticket; motion.ts
    no longer computes this pair or calls moveX() from startGoTo() at
    all. Frozen here as a regression pin -- see
    test_old_broken_block_arc_reduction_misses_probe_targets_above_threshold
    below. `x_cm`/`y_cm` are the block's own units (student cm), matching
    what a `go to (x, y)` block used to pass into this reduction."""
    x, y = float(x_cm), float(y_cm)
    theta = 2.0 * math.atan2(y, x)
    radius = (x * x + y * y) / (2.0 * y)
    s_mm = radius * theta * 10.0  # cm -> mm
    e.move_x(s_mm, theta, speed_mm_s, timeout_ms)


def _fixed_start_go_to_to_go_to_r(e, x_cm, y_cm):
    """Restates blocks/motion.ts's REWRITTEN startGoTo() (sprint 015
    ticket 002) exactly: round(x*10)/round(y*10) cm->mm conversion,
    defaultSpeed (cm/s) -> mm/s, a 1 mm `arrive` gate, and the
    pivot-then-straight timeout backstop (summed pivot/straight
    durations at defaultYawRate/defaultSpeed, +1500 ms taper margin) --
    issued directly through goToR(), the ONLY entry point startGoTo()
    reaches now. `x_cm`/`y_cm` are the block's own units (student cm),
    matching what a `go to (x, y)` block passes."""
    x, y = float(x_cm), float(y_cm)
    x_mm = round(x * 10)
    y_mm = round(y * 10)
    speed_mm_s = round(_BLOCK_DEFAULT_SPEED_CM_S * 10)
    arrive_mm = 1
    chord_cm = math.hypot(x, y)
    pivot_s = 180.0 / _BLOCK_DEFAULT_YAW_RATE_DEG_S
    straight_s = chord_cm / _BLOCK_DEFAULT_SPEED_CM_S
    timeout_ms = round((pivot_s + straight_s) * 1000.0) + 1500
    e.go_to_r(x_mm, y_mm, speed_mm_s, arrive_mm, timeout_ms)


# ---- AC2: the corrected, now-`//%`-exposed entry point --------------------


@pytest.mark.parametrize("x_mm,y_mm", [
    (100.0, 100.0),   # block goTo(10, 10) cm -- bearing 45 deg, above split
    (-100.0, 10.0),   # block goTo(-10, 1) cm -- behind the robot, wraps short
])
def test_go_to_r_reaches_probe_targets_above_threshold(motion_lib, x_mm, y_mm):
    """goToR() (already correct: its own bearing-pivot-then-chord split
    and short-arc wrap) lands within 5 mm on both probe geometries
    block-go-to-misses-its-target.md measured against the real firmware
    -- reachable from the block layer only once this ticket's `//%`
    annotation ships, but already correct at the engine level today."""
    with ProbeEngine(motion_lib) as e:
        _ready(e)
        e.go_to_r(x_mm, y_mm, _PROBE_SPEED_MM_S, 1.0, _PROBE_TIMEOUT_MS)
        e.run_to_completion()

        miss = math.hypot(e.probe_x() - x_mm, e.probe_y() - y_mm)
        assert miss < _LANDING_TOLERANCE_MM


# ---- Negative control: the OLD, now-historical block reduction ------------


@pytest.mark.parametrize("x_cm,y_cm,x_mm,y_mm,measured_miss_mm", [
    (10.0, 10.0, 100.0, 100.0, 112.5),
    (-10.0, 1.0, -100.0, 10.0, 3172.4),
])
def test_old_broken_block_arc_reduction_misses_probe_targets_above_threshold(
        motion_lib, x_cm, y_cm, x_mm, y_mm, measured_miss_mm):
    """THIS IS WHAT THE BUG LOOKED LIKE -- a frozen regression pin, not a
    live code path. Before sprint 015 ticket 002, startGoTo()'s
    theta=2*atan2(y,x)/s=R*theta pair, handed to moveX(), was the ONLY
    entry point reachable from a block: moveX()'s own >=50 deg split
    reissued that pair as pivot-then-straight, which lands at a
    different point than the arc it was computed for (arc length !=
    chord length except in the limit). motion.ts no longer computes this
    reduction or calls moveX() from startGoTo() at all (see
    test_fixed_start_go_to_reaches_probe_targets_above_threshold below,
    which exercises what startGoTo() actually does now) -- this test
    exists only to pin the OLD reduction's measured miss on the SAME two
    geometries, so the historical defect stays documented and a
    regression back to this shape of bug would be caught.

    Existing goTo host tests deliberately stay below 50 deg
    (test_motion_engine_reductions.py's own test_go_to_r_arc_hand_computed
    asserts exactly that), which is why this defect could ship for six
    sprints undetected."""
    with ProbeEngine(motion_lib) as e:
        _ready(e)
        _old_broken_block_arc_reduction_to_move_x(
            e, x_cm, y_cm, _PROBE_SPEED_MM_S, _PROBE_TIMEOUT_MS)
        e.run_to_completion()

        miss = math.hypot(e.probe_x() - x_mm, e.probe_y() - y_mm)

        # Pin: this reduction reproduces the issue's own measured miss,
        # not merely "some" large number -- proves this is the SAME
        # defect the issue measured, not a different bug.
        assert miss == pytest.approx(measured_miss_mm, rel=0.2)


# ---- AC1/AC2/AC7 (SUC-001): startGoTo() after the fix ----------------------


@pytest.mark.parametrize("x_cm,y_cm,x_mm,y_mm", [
    (10.0, 10.0, 100.0, 100.0),   # block goTo(10, 10) cm -- above split
    (-10.0, 1.0, -100.0, 10.0),   # block goTo(-10, 1) cm -- behind robot
])
def test_fixed_start_go_to_reaches_probe_targets_above_threshold(
        motion_lib, x_cm, y_cm, x_mm, y_mm):
    """The acceptance bar this ticket's own test requirement names: at
    least one host test must exercise the block layer's OWN input shape
    (student cm, through startGoTo()'s actual post-fix arithmetic, not
    just goToR() in isolation -- see
    _fixed_start_go_to_to_go_to_r()'s docstring) and land within 5 mm on
    both probe geometries block-go-to-misses-its-target.md measured,
    above the 50 deg split threshold where the old reduction (see
    test_old_broken_block_arc_reduction_misses_probe_targets_above_threshold
    above) used to miss by 112.5 mm / 3172.4 mm. startGoTo() now calls
    goToR() directly (sprint 015 ticket 002), which owns its own
    bearing-then-chord split and short-arc wrap (motion_engine.cpp) and
    reaches (x, y) exactly."""
    with ProbeEngine(motion_lib) as e:
        _ready(e)
        _fixed_start_go_to_to_go_to_r(e, x_cm, y_cm)
        e.run_to_completion()

        miss = math.hypot(e.probe_x() - x_mm, e.probe_y() - y_mm)
        assert miss < _LANDING_TOLERANCE_MM


# ---- test/test.ts legToward(): the SAME defect, a second call site --------
#
# legToward()'s pre-fix reduction was ALGEBRAICALLY IDENTICAL to
# _old_broken_block_arc_reduction_to_move_x() above: it computes a
# body-frame residual (bx, by) to the target exactly the way that
# helper's (x_cm, y_cm) is used, then hands the same
# theta=2*atan2(by,bx)/s=R*theta pair to the same moveX() -- so the same
# helper stands in for legToward's own math here rather than being
# reimplemented. The difference from the two geometries above is where
# the miss comes from: legToward only pre-pivoted when |bearing| >=
# 50 deg, but a bearing well under that (e.g. 30 deg) still doubles to a
# theta of 60 deg, which is ABOVE moveX()'s OWN >=50 deg split
# (kTurnFirstAngleRad) -- so the routine, common case (not just an edge
# case near the pre-pivot threshold) tripped this defect.
#
# tour-legs-share-the-arc-split-defect.md's worked example: bearing
# 30 deg, distance d = 60 cm. Intended endpoint is (bx, by) itself
# (0.866d, 0.500d) by construction; pure pivot-then-straight kinematics
# for this geometry pivots to theta=60 deg then drives arc-length
# s = radius*theta with radius = d/(2*sin(bearing)) = d (30 deg exactly
# halves 60 deg), landing at (s*cos(theta), s*sin(theta)) =
# (0.524d, 0.907d) -- a ~0.531d miss, matching the issue's own
# measurement (~32 cm on this 60 cm leg).

_LEG_TOWARD_BEARING_DEG = 30.0
_LEG_TOWARD_DISTANCE_CM = 60.0


def _leg_toward_target_cm():
    """The body-frame target (bx, by), in cm, for the worked-example
    bearing/distance above -- what legToward() would compute as its own
    residual to a target sitting exactly there."""
    bearing_rad = _LEG_TOWARD_BEARING_DEG * math.pi / 180.0
    bx = _LEG_TOWARD_DISTANCE_CM * math.cos(bearing_rad)
    by = _LEG_TOWARD_DISTANCE_CM * math.sin(bearing_rad)
    return bx, by


def _ideal_pivot_then_straight_endpoint_mm(bx_cm, by_cm):
    """Pure kinematic prediction (no taper/ramp/tick shaping -- those
    change the TIME profile, not the resting position) for where the
    OLD moveX()-based reduction lands: pivot in place to theta =
    2*atan2(by,bx), then drive s = radius*theta straight along the new
    heading. Used only to derive this test's expected miss distance from
    the geometry itself, rather than hand-typing a magic number."""
    bearing = math.atan2(by_cm, bx_cm)
    theta = 2.0 * bearing
    radius = (bx_cm * bx_cm + by_cm * by_cm) / (2.0 * by_cm)
    s_cm = radius * theta
    return s_cm * math.cos(theta) * 10.0, s_cm * math.sin(theta) * 10.0


def test_old_leg_toward_reduction_misses_worked_example(motion_lib):
    """THIS IS WHAT THE BUG LOOKED LIKE at legToward()'s call site -- a
    frozen regression pin, not a live code path (test/test.ts's
    legToward() no longer computes this reduction). Reproduces
    tour-legs-share-the-arc-split-defect.md's own worked example
    (bearing 30 deg, distance 60 cm) through the real firmware's move
    engine, on the SAME moveX()-based reduction
    test_old_broken_block_arc_reduction_misses_probe_targets_above_threshold
    above already pins for two other geometries -- this is the case
    where the bearing itself (30 deg) is comfortably under legToward's
    own 50 deg pre-pivot threshold, so the miss is not an edge case."""
    bx_cm, by_cm = _leg_toward_target_cm()
    target_mm_x, target_mm_y = bx_cm * 10.0, by_cm * 10.0
    expected_x_mm, expected_y_mm = _ideal_pivot_then_straight_endpoint_mm(
        bx_cm, by_cm)
    expected_miss_mm = math.hypot(
        expected_x_mm - target_mm_x, expected_y_mm - target_mm_y)

    with ProbeEngine(motion_lib) as e:
        _ready(e)
        _old_broken_block_arc_reduction_to_move_x(
            e, bx_cm, by_cm, _PROBE_SPEED_MM_S, _PROBE_TIMEOUT_MS)
        e.run_to_completion()

        miss = math.hypot(
            e.probe_x() - target_mm_x, e.probe_y() - target_mm_y)

        # Pin: matches the ideal pivot-then-straight geometry (a few mm
        # of headroom for tick discretization against the ideal-wheels
        # probe, same tolerance style as the file's other geometry
        # pins), and separately confirms it is approximately the
        # issue's own 0.531d ratio -- not merely "some" large miss.
        assert miss == pytest.approx(expected_miss_mm, abs=5.0)
        assert miss == pytest.approx(
            0.531 * _LEG_TOWARD_DISTANCE_CM * 10.0, rel=0.05)


def test_fixed_leg_toward_reduction_reaches_worked_example(motion_lib):
    """legToward()'s FIXED reduction: the same body-frame (bx, by)
    target, driven through startGoTo() -> goToR() directly (the same
    entry point startGoTo() itself now uses) instead of moveX() --
    lands within a few mm, same bar as
    test_fixed_start_go_to_reaches_probe_targets_above_threshold above."""
    bx_cm, by_cm = _leg_toward_target_cm()
    target_mm_x, target_mm_y = bx_cm * 10.0, by_cm * 10.0

    with ProbeEngine(motion_lib) as e:
        _ready(e)
        _fixed_start_go_to_to_go_to_r(e, bx_cm, by_cm)
        e.run_to_completion()

        miss = math.hypot(
            e.probe_x() - target_mm_x, e.probe_y() - target_mm_y)
        assert miss < _LANDING_TOLERANCE_MM
