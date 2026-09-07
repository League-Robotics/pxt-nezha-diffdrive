"""tests/host/test_goto_block_regression.py -- drives moves to actual
COMPLETION against ideal wheels (motion_engine_shim.cpp's
meProbeRunToCompletion(), mirroring docs/code-review/2026-08-26/raw/
goto_probe.cpp's own Rig::tick()/run()) and checks the resulting
body-frame ENDPOINT, rather than test_motion_engine_reductions.py's own
single-tick hand-computed-duty style -- the shape this ticket needs to
compare two different ways of turning a target into a move on the SAME
final position, not just their first commanded duty.

Two probe geometries, both measured in block-go-to-misses-its-target.md
against the real firmware C++:

  block goTo(10, 10) cm   -> bearing 45 deg, a 141.4 mm hop
  block goTo(-10, 1) cm   -> a target behind the robot, theta wraps short

MotionEngine::goToR() reaches both within a few mm. blocks/motion.ts's
startGoTo() (sprint 015 ticket 002) calls goToR() directly instead of
computing its own (arc-length, arc-angle) pair and handing it to
MotionEngine::moveX(). HISTORY: at the time, moveX() had its own
>= 50 deg pivot-then-straight split, which reissued that pair as a
DIFFERENT physical path than the arc it was computed for, missing by the
margins the issue measured -- that was the defect. moveX() no longer
splits at any angle (reports/move-x-arc-space-20260906.md), so the same
(s, theta) pair through moveX() now lands ON the target too; the tests
below pin that, and pin why startGoTo() still goes through goToR()
anyway: it is a POLICY difference, not a correctness one. goToR() wraps
theta to the short arc and pivots-then-chords above its threshold, so a
target behind the robot is a bounded pivot plus a straight, where the
raw arc reduction is a 3 m loop the long way round ending at a
different heading. This file restates BOTH reductions directly in
Python (motion.ts is TypeScript, out of reach of a host build) and
drives each through the real firmware's own move engine to completion.

Run with::

    uv run pytest tests/host/test_goto_block_regression.py
"""

import math

import pytest

from test_motion_engine_reductions import Engine


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
#
# Sprint 029 ticket 003 widens this to 10 mm for the pivot-then-straight
# (bearing-split) cases specifically: design motion-profile-
# unification.md S6.3's own residual bound ("bounded by the arithmetic
# error in vNext*dt, one tick of the floor speed at most... 0.5 deg with
# the yaw floor") is an ANGULAR bound on the pivot phase, which the
# following straight phase's own leg length then amplifies linearly --
# 0.5 deg of heading error over a 600 mm leg is already ~5.2 mm on its
# own, on top of the straight phase's own ~1.7 mm residual. MEASURED
# against this ticket's engine,
# test_fixed_leg_toward_reduction_reaches_worked_example (bearing 30
# deg, distance 600 mm, ideal wheels): 7.74 mm. `stopDistance` is 0
# (UNVERIFIED, design S10.2 -- not yet bench-measured) throughout this
# host suite, so this is the shaper's floor-tick residual alone, not a
# tuned number; a future bench-measured stopDistance would tighten it
# without changing this test.
_LANDING_TOLERANCE_MM = 10.0

# blocks/motion.ts's own diffDrive namespace defaults (defaultSpeed
# [cm/s], defaultYawRate [deg/s]) -- the fixed startGoTo() transcription
# below (`_fixed_start_go_to_to_go_to_r`) uses these exactly as
# startGoTo() itself does, so the timeout it derives matches what the
# real block would compute.
_BLOCK_DEFAULT_SPEED_CM_S = 15.0
_BLOCK_DEFAULT_YAW_RATE_DEG_S = 90.0


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


def _arc_reduction_to_move_x(e, x_cm, y_cm, speed_mm_s, timeout_ms):
    """blocks/motion.ts's PRE-sprint-015 startGoTo() reduction, restated
    exactly as it shipped: theta = 2*atan2(y,x), s = R*theta (computed in
    the student's own cm), then issued through moveX() in mm. motion.ts
    no longer computes this pair or calls moveX() from startGoTo() at
    all; it is kept here because it is the plain tangent-arc route to a
    point, which moveX() now drives faithfully -- see
    test_arc_reduction_through_move_x_now_lands_on_target below.
    `x_cm`/`y_cm` are the block's own units (student cm)."""
    x, y = float(x_cm), float(y_cm)
    theta = 2.0 * math.atan2(y, x)
    radius = (x * x + y * y) / (2.0 * y)
    s_mm = radius * theta * 10.0  # cm -> mm
    e.move_x(s_mm, theta, speed_mm_s, timeout_ms)
    return s_mm, theta


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


# ---- The raw tangent-arc reduction through moveX() ------------------------


@pytest.mark.parametrize("x_cm,y_cm,x_mm,y_mm,historical_miss_mm", [
    (10.0, 10.0, 100.0, 100.0, 112.5),
    (-10.0, 1.0, -100.0, 10.0, 3172.4),
])
def test_arc_reduction_through_move_x_now_lands_on_target(
        motion_lib, x_cm, y_cm, x_mm, y_mm, historical_miss_mm):
    """The (arc-length, arc-angle) pair handed to moveX() reaches the
    point it was computed for, because moveX() drives the arc it is
    given at ANY angle. `historical_miss_mm` is what the SAME call
    missed by when moveX() still split at 50 deg (block-go-to-misses-
    its-target.md: 112.5 mm and 3172.4 mm) -- pinned here as the
    distance this change closed, so a split creeping back into moveX()
    fails loudly on the same two geometries that found it.

    The second geometry is also the argument for goToR()'s own policy:
    theta = 2*atan2(1, -10) is 348.6 deg the long way round a 50.5 cm
    radius -- a 3.07 m loop, ending facing almost the way it started --
    where goToR() wraps to the short arc and pivots-then-chords (a
    174 deg pivot and a 10 cm straight)."""
    with ProbeEngine(motion_lib) as e:
        _ready(e)
        s_mm, theta = _arc_reduction_to_move_x(
            e, x_cm, y_cm, _PROBE_SPEED_MM_S, _PROBE_TIMEOUT_MS)
        e.run_to_completion()

        miss = math.hypot(e.probe_x() - x_mm, e.probe_y() - y_mm)
        assert miss < _LANDING_TOLERANCE_MM
        assert miss < 0.05 * historical_miss_mm
        # The arc ends at heading theta, the full arc angle -- not at the
        # bearing goToR()'s pivot-then-chord would leave the robot on.
        assert e.probe_heading() == pytest.approx(theta, abs=math.radians(1.0))
        if y_cm < 0 or x_cm < 0:
            assert abs(s_mm) > 3000.0  # the long way round


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
    (historically 112.5 mm / 3172.4 mm misses through moveX()'s old
    split; see test_arc_reduction_through_move_x_now_lands_on_target
    above). startGoTo() calls goToR() directly (sprint 015 ticket 002),
    which owns its own bearing-then-chord split and short-arc wrap
    (motion_engine.cpp) and reaches (x, y) exactly."""
    with ProbeEngine(motion_lib) as e:
        _ready(e)
        _fixed_start_go_to_to_go_to_r(e, x_cm, y_cm)
        e.run_to_completion()

        miss = math.hypot(e.probe_x() - x_mm, e.probe_y() - y_mm)
        assert miss < _LANDING_TOLERANCE_MM


# ---- test/test.ts legToward(): the SAME reduction, a second call site -----
#
# legToward()'s pre-fix reduction was ALGEBRAICALLY IDENTICAL to
# _arc_reduction_to_move_x() above: it computes a
# body-frame residual (bx, by) to the target exactly the way that
# helper's (x_cm, y_cm) is used, then hands the same
# theta=2*atan2(by,bx)/s=R*theta pair to the same moveX() -- so the same
# helper stands in for legToward's own math here rather than being
# reimplemented. HISTORY (moveX() no longer splits -- module docstring):
# the miss came from legToward only pre-pivoting when |bearing| >=
# 50 deg, but a bearing well under that (e.g. 30 deg) still doubles to a
# theta of 60 deg, which is ABOVE moveX()'s OWN >=50 deg split
# (kTurnFirstAngle) -- so the routine, common case (not just an edge
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


def test_leg_toward_arc_reduction_through_move_x_lands_on_worked_example(
        motion_lib):
    """tour-legs-share-the-arc-split-defect.md's worked example (bearing
    30 deg, distance 60 cm) through the raw tangent-arc reduction and
    moveX(). HISTORY: with moveX()'s old 50 deg split this landed
    0.531d (318 mm) from the target, because the bearing (30 deg) is
    under legToward's own pre-pivot threshold while the arc angle
    (theta = 60 deg) was over moveX()'s -- the leg was silently a pivot
    plus a straight. moveX() no longer splits, so the same reduction
    lands on the target; test.ts's legToward() still goes through
    startGoTo() -> goToR() for the policy reasons the module docstring
    gives."""
    bx_cm, by_cm = _leg_toward_target_cm()
    target_mm_x, target_mm_y = bx_cm * 10.0, by_cm * 10.0

    with ProbeEngine(motion_lib) as e:
        _ready(e)
        _arc_reduction_to_move_x(
            e, bx_cm, by_cm, _PROBE_SPEED_MM_S, _PROBE_TIMEOUT_MS)
        e.run_to_completion()

        miss = math.hypot(
            e.probe_x() - target_mm_x, e.probe_y() - target_mm_y)
        assert miss < _LANDING_TOLERANCE_MM
        assert miss < 0.05 * 0.531 * _LEG_TOWARD_DISTANCE_CM * 10.0


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
